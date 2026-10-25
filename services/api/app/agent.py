import logging
import os
import re
from dataclasses import dataclass, field

from google.adk.agents.run_config import RunConfig
from google.adk.apps.app import App, EventsCompactionConfig
from google.adk.apps.llm_event_summarizer import LlmEventSummarizer
from google.adk.events import Event, EventActions
from google.adk.models import Gemini
from google.adk.runners import Runner
from google.genai import types

from app.agents.listing import cards_from_offers, listings_from_tool_response
from app.agents.open_web_trust import review_listings
from app.agents.orchestrator import root_agent
from app.lib.sources.firecrawl import product_name_at, search_open_web
from app.lib.trust import close_listings
from app.runtime import session_service

FALLBACK_REPLY = "Algo falló de mi lado. Inténtalo otra vez en un momento."
log = logging.getLogger("prais.agent")

@dataclass
class PraisAnswer:
    text: str
    listings: list[dict] = field(default_factory=list)


# El resumen sustituye los turnos viejos. Tiene que conservar las cifras: sin ellas
# el siguiente mensaje ("el de 128 GB") no tiene de qué hablar.
_SUMMARY = (
    "Resume esta conversación de Prais en español. Conserva el producto o servicio "
    "que se compara, el vendedor, el precio, la moneda, si la oferta es de ejemplo "
    "y cuál opción se recomendó abrir primero. No inventes cifras ni tiendas que no "
    "estén escritas abajo.\n\n{conversation_history}"
)


def build_app() -> App:
    model = os.environ.get("PRAIS_MODEL", "gemini-flash-latest")
    return App(
        name="prais",
        root_agent=root_agent,
        events_compaction_config=EventsCompactionConfig(
            compaction_interval=4,
            overlap_size=1,
            token_threshold=4000,
            event_retention_size=8,
            summarizer=LlmEventSummarizer(llm=Gemini(model=model), prompt_template=_SUMMARY),
        ),
    )


# Un mensaje sano pide el modelo dos veces: decidir la búsqueda y escribir el veredicto.
# El tope de la librería es 500 por mensaje. Si el modelo no da una respuesta que
# la librería acepte, ella vuelve a preguntar hasta ese tope.
_RUN = RunConfig(max_llm_calls=4)

runner = Runner(app=build_app(), session_service=session_service(), auto_create_session=True)

_URL = re.compile(r"https?://[^\s<>]+")
_MODEL = re.compile(r"\b(iphone\s*\d+\s*(?:pro\s*max|pro|plus|mini|e)?)\b", re.IGNORECASE)
_LATEST = re.compile(
    r"\b((?:el\s+)?[uú]ltim[oa]s?|m[aá]s nuev[oa]s?|acaba de salir|que sali[oó])\b",
    re.IGNORECASE,
)
_WHICH_MODEL = re.compile(r"cu[aá]l modelo|qu[eé] modelo", re.IGNORECASE)
_APP = "prais"
_last_question: dict[str, str] = {}


def track_product(previous: str | None, message: str) -> str | None:
    """Lo que esta conversación ya sabe que hay que buscar. Vive en la sesión."""
    match = _MODEL.search(message)
    if match:
        return " ".join(match.group(1).split())
    if _LATEST.search(message):
        if previous:
            return previous
        if re.search(r"iphone", message, re.IGNORECASE):
            return "el último iPhone"
        return previous
    words = re.findall(r"[a-z0-9]+", message.lower())
    if previous and len(words) <= 3:
        return previous
    return None


async def _session(user_id: str):
    service = runner.session_service
    session = await service.get_session(app_name=_APP, user_id=user_id, session_id=user_id)
    if session is None:
        session = await service.create_session(app_name=_APP, user_id=user_id, session_id=user_id)
    return session


async def _remember(user_id: str, message: str) -> str | None:
    """Guarda el producto en session.state, que es el cuaderno de este hilo."""
    session = await _session(user_id)
    previous = session.state.get("product")
    previous = previous if isinstance(previous, str) and previous else None
    product = track_product(previous, message)
    stored = product or ""
    if stored != (previous or ""):
        await runner.session_service.append_event(
            session,
            Event(
                invocation_id="product",
                author="system",
                actions=EventActions(state_delta={"product": stored}),
            ),
        )
    return product


def _question_key(text: str) -> str:
    folded = "".join(char for char in text.lower() if char.isalnum() or char.isspace())
    return " ".join(folded.split())


def _is_question(text: str) -> bool:
    return "?" in text


def _same_question(one: str, other: str) -> bool:
    if not one or not other:
        return False
    return one == other or one in other or other in one


def _link(message: str) -> str | None:
    match = _URL.search(message)
    if not match:
        return None
    return match.group(0).rstrip(").,]>\"'")


async def _for_the_agent(message: str) -> tuple[str, str | None]:
    """El texto que lee el modelo, y el nombre del producto si el mensaje era un link."""
    url = _link(message)
    if url is None:
        return message, None
    name = await product_name_at(url)
    if not name:
        note = (
            "La persona mandó un link y no se pudo leer el nombre del producto. "
            "Pregunta una sola vez qué es, en una frase. No armes un menú."
        )
        return f"{message}\n\n{note}", None
    note = (
        f"La persona mandó un link para comparar. En la página el producto se llama «{name}». "
        "Busca ese nombre en las fuentes. No preguntes cuál modelo es."
    )
    return f"{message}\n\n{note}", name


def _search_text(message: str, named: str | None) -> str:
    if named:
        return named
    without_link = _URL.sub(" ", message)
    text = " ".join(without_link.split())
    return text or message


async def _search_instead(product: str) -> list[dict]:
    found = await search_open_web(product)
    listings = cards_from_offers(found.get("offers") or [])
    review_listings(product, listings)
    return close_listings(listings)


def _event_parts(event: object) -> list[object]:
    content = getattr(event, "content", None)
    return list(getattr(content, "parts", None) or [])


def _event_listings(event: object) -> list[dict]:
    found = []
    for part in _event_parts(event):
        response = getattr(getattr(part, "function_response", None), "response", None)
        found.extend(listings_from_tool_response(response))
    return found


async def _run_agent(user_id: str, message: str) -> PraisAnswer:
    """Corre el modelo. El texto es la guía; listings sale del JSON de cada especialista."""
    reply = ""
    listings: list[dict] = []
    seen: set[str] = set()
    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=user_id,
            new_message=types.Content(role="user", parts=[types.Part(text=message)]),
            run_config=_RUN,
        ):
            for card in _event_listings(event):
                url = card.get("url")
                if isinstance(url, str) and url not in seen:
                    seen.add(url)
                    listings.append(card)
            if event.is_final_response() and event.content and event.content.parts:
                reply += "".join(part.text or "" for part in event.content.parts if not part.function_call)
    except Exception:
        log.exception("agent run failed")
        return PraisAnswer(text=reply.strip() or FALLBACK_REPLY, listings=close_listings(listings))
    return PraisAnswer(text=reply.strip() or FALLBACK_REPLY, listings=close_listings(listings))


async def ask_prais(user_id: str, message: str) -> PraisAnswer:
    """El agente lee el mensaje. El producto queda en la sesión. Una pregunta ya hecha no se repite."""
    product = await _remember(user_id, message)
    brief, named = await _for_the_agent(message)
    if product:
        brief = f"{brief}\n\nProducto ya fijado en la sesión: {product}. Búscalo. No preguntes cuál modelo."
    answer = await _run_agent(user_id, brief)
    if product and _WHICH_MODEL.search(answer.text):
        if not answer.listings:
            try:
                answer.listings = await _search_instead(product)
            except Exception:
                log.exception("known product fell back to search")
        answer.text = f"Busco {product}."
        return answer
    key = _question_key(answer.text)
    previous = _last_question.get(user_id)
    if _is_question(answer.text) and _same_question(key, previous or ""):
        product = _search_text(message, named)
        if not answer.listings and product:
            try:
                answer.listings = await _search_instead(product)
            except Exception:
                log.exception("repeat question fell back to search")
        answer.text = "Sigo con lo que ya me dijiste."
        return answer
    if _is_question(answer.text) and key:
        _last_question[user_id] = key
        if len(_last_question) > 500:
            _last_question.pop(next(iter(_last_question)))
    return answer
