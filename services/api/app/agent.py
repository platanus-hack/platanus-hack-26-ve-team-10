import asyncio
import logging
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from google.adk.agents.run_config import RunConfig
from google.adk.apps.app import App, EventsCompactionConfig
from google.adk.apps.llm_event_summarizer import LlmEventSummarizer
from google.adk.events import Event, EventActions
from google.adk.models import Gemini
from google.adk.runners import Runner
from google.genai import types

from app.agents.listing import (
    ONLY_NEW,
    ONLY_USED,
    cards_from_offers,
    has_published_price,
    listings_from_tool_response,
    mixed_condition,
    narrowed,
    says_condition,
)
from app.agents.open_web_trust import review_offers
from app.agents.orchestrator import root_agent
from app.lib import dialog
from app.lib.sources.firecrawl import product_name_at, search_open_web
from app.lib.trust import close_listings
from app.runtime import session_service

RETRY = "Reintentar"
FALLBACK_REPLY = "Algo falló de mi lado. Inténtalo otra vez en un momento."
log = logging.getLogger("prais.agent")

# Lo llama el canal para decir, en una línea, qué se está buscando. La web no lo usa.
OnSearch = Callable[[str], Awaitable[None]]

@dataclass
class PraisAnswer:
    text: str
    listings: list[dict] = field(default_factory=list)
    # El producto con el que se buscó de verdad, para que la persona pueda corregirlo.
    product: str = ""
    # Botones que van después del resultado: afinar si hubo precios, salir si no hubo.
    buttons: list[str] = field(default_factory=list)
    priced: bool = False
    # Si alguna fuente llegó a contestar. Sin esto no se distingue "no encontré"
    # de "ni siquiera busqué", y un saludo terminaría con botones de búsqueda.
    searched: bool = False
    failed: bool = False


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
    """Nombre concreto que este mensaje confirma. None no borra el anterior.

    "El último" no es un producto. No se inventa una frase para buscar.
    """
    match = _MODEL.search(message)
    if match:
        return " ".join(match.group(1).split())
    words = re.findall(r"[a-z0-9]+", message.lower())
    if _LATEST.search(message) or (previous and len(words) <= 3):
        return previous
    return None


async def _session(user_id: str):
    service = runner.session_service
    session = await service.get_session(app_name=_APP, user_id=user_id, session_id=user_id)
    if session is None:
        session = await service.create_session(app_name=_APP, user_id=user_id, session_id=user_id)
    return session


async def _store_product(user_id: str, product: str) -> None:
    """El apunte vive en session.state. Solo se escribe por un evento, como pide ADK."""
    session = await _session(user_id)
    previous = session.state.get("product")
    if product == previous:
        return
    await runner.session_service.append_event(
        session,
        Event(
            invocation_id="product",
            author="system",
            actions=EventActions(state_delta={"product": product}),
        ),
    )


async def _remember(user_id: str, message: str) -> str | None:
    """Guarda un nombre concreto. Un mensaje que no lo trae no borra el anterior."""
    session = await _session(user_id)
    previous = session.state.get("product")
    previous = previous if isinstance(previous, str) and previous else None
    product = track_product(previous, message)
    if product:
        await _store_product(user_id, product)
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


async def _search_instead(product: str) -> list[dict]:
    found = await search_open_web(product)
    offers = found.get("offers") or []
    await review_offers(product, offers)
    return close_listings(cards_from_offers(offers))


def _event_parts(event: object) -> list[object]:
    content = getattr(event, "content", None)
    return list(getattr(content, "parts", None) or [])


def _event_listings(event: object) -> list[dict]:
    found = []
    for part in _event_parts(event):
        response = getattr(getattr(part, "function_response", None), "response", None)
        found.extend(listings_from_tool_response(response))
    return found


# Lo que el modelo ya decidió: si llama a una tool de búsqueda, va a buscar, y el
# argumento es su lectura del producto. Sale en el primer turno, a uno o dos segundos,
# mucho antes de los 45 s de scraping. Es gratis y lee cualquier cosa, no solo iPhones.
ACK_GRACE_S = 1.5
# Arranques de intención: "comprar un iphone 17pro" se acusa como "iphone 17pro".
# Si no calza nada, se usa el texto tal cual. No es un catálogo de productos.
_INTENT = re.compile(
    r"^\s*(?:hola[,\s]+)?(?:me\s+)?(?:gustar[ií]a\s+)?"
    r"(?:quiero|busco|buscar|comprar|conseguir|necesito|ver|precio[s]?\s+de|cu[aá]nto\s+(?:vale|cuesta))\s+"
    r"(?:un[oa]?s?\s+|el\s+|la\s+|los\s+|las\s+)?",
    re.IGNORECASE,
)


def searched_name(product: str) -> str:
    """El nombre que se va a buscar, sin el arranque de intención."""
    return " ".join(_INTENT.sub("", product).split()) or " ".join(product.split())


def _event_search_call(event: object) -> str | None:
    """El producto con el que el modelo acaba de pedir una búsqueda, si la pidió."""
    for part in _event_parts(event):
        call = getattr(part, "function_call", None)
        name = getattr(call, "name", None)
        if not isinstance(name, str) or not name.startswith("find_listings"):
            continue
        args = getattr(call, "args", None) or {}
        product = args.get("product") if isinstance(args, dict) else None
        if isinstance(product, str) and product.strip():
            return searched_name(product)
    return None


async def _drop_ack(ack: asyncio.Task | None) -> None:
    if ack is None:
        return
    ack.cancel()
    try:
        await ack
    except asyncio.CancelledError:
        pass


async def _ack_after_grace(on_search: OnSearch, product: str) -> None:
    """Se cancela si la respuesta llega antes: una búsqueda cacheada no gasta un mensaje."""
    await asyncio.sleep(ACK_GRACE_S)
    try:
        await on_search(product)
    except Exception:
        # El acuse es cortesía: nunca tumba la respuesta que viene detrás.
        log.warning("acuse de búsqueda falló", exc_info=True)


def _event_searched(event: object) -> bool:
    """Si alguna fuente contestó, aunque haya traído cero. Distingue no encontrar de no buscar."""
    for part in _event_parts(event):
        response = getattr(getattr(part, "function_response", None), "response", None)
        while isinstance(response, dict):
            if "listings" in response:
                return True
            response = response.get("result")
    return False


async def _run_agent(user_id: str, message: str, on_search: OnSearch | None = None) -> PraisAnswer:
    """Corre el modelo. El texto es la guía; listings sale del JSON de cada especialista."""
    reply = ""
    listings: list[dict] = []
    seen: set[str] = set()
    searched = False
    ack: asyncio.Task | None = None
    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=user_id,
            new_message=types.Content(role="user", parts=[types.Part(text=message)]),
            run_config=_RUN,
        ):
            if on_search is not None and ack is None:
                asked = _event_search_call(event)
                if asked:
                    ack = asyncio.create_task(_ack_after_grace(on_search, asked))
            searched = searched or _event_searched(event)
            for card in _event_listings(event):
                url = card.get("url")
                if isinstance(url, str) and url not in seen:
                    seen.add(url)
                    listings.append(card)
            if event.is_final_response() and event.content and event.content.parts:
                reply += "".join(part.text or "" for part in event.content.parts if not part.function_call)
    except Exception:
        log.exception("agent run failed")
        text = reply.strip()
        if not text and listings:
            text = "Encontré opciones. El resumen no salió; abre la primera."
        return PraisAnswer(
            text=text or FALLBACK_REPLY,
            listings=close_listings(listings),
            searched=searched,
            failed=not listings,
        )
    finally:
        await _drop_ack(ack)
    return PraisAnswer(text=reply.strip() or FALLBACK_REPLY, listings=close_listings(listings), searched=searched)


async def _answer(user_id: str, message: str, on_search: OnSearch | None = None) -> PraisAnswer:
    """El agente lee el mensaje tal cual. La sesión de ADK es el hilo. Una pregunta ya hecha no se repite."""
    product = await _remember(user_id, message)
    brief, named = await _for_the_agent(message)
    if named:
        product = named
        await _store_product(user_id, named)
    answer = await _run_agent(user_id, brief, on_search)
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
        if product:
            if not answer.listings:
                try:
                    answer.listings = await _search_instead(product)
                except Exception:
                    log.exception("repeat question fell back to search")
            answer.text = f"Busco {product}."
        else:
            # No se busca la duda ("el 17 o el 18", "el normal"). Eso no es un producto.
            answer.text = "Dime el nombre y lo busco."
        return answer
    if _is_question(answer.text) and key:
        _last_question[user_id] = key
        if len(_last_question) > 500:
            _last_question.pop(next(iter(_last_question)))
    return answer


async def _followups(user_id: str, product: str, answer: PraisAnswer) -> None:
    """Los botones que cierran el turno, guardados para cuando vuelva el toque.

    Un botón regresa solo con su título, sin el producto, y Cloud Run corre varias
    copias de prais-api: la respuesta sale de una y el toque entra por otra. En un
    dict del proceso, "Solo nuevos" se buscaría como si fuera un producto.
    """
    actions: dict[str, str | None] = {}
    if answer.failed and product:
        actions[RETRY] = product
    elif answer.priced and product and not says_condition(product) and mixed_condition(answer.listings):
        actions[ONLY_NEW] = f"{product} nuevo"
        actions[ONLY_USED] = f"{product} usado"
    elif answer.searched and not answer.priced and product:
        wider = narrowed(product)
        if wider:
            actions[wider[0]] = wider[1]
    answer.buttons = list(actions)
    await dialog.save(user_id, {"product": product, "actions": actions})


async def _searched_product(user_id: str, text: str, answer: PraisAnswer) -> str:
    """Lo que de verdad se buscó, para enseñarlo y para saber qué se puede soltar.

    La sesión guarda el modelo normalizado ("iPhone 15"), que es lo que sirve cuando
    el mensaje es un seguimiento ("el último"). Pero el mensaje entero es lo que lleva
    la capacidad o el estado, y es lo que hay que poder soltar si no hubo precios.
    """
    if not answer.searched and not answer.failed:
        return ""  # Un saludo no buscó nada: no hay producto que enseñar ni que soltar.
    session = await _session(user_id)
    saved = session.state.get("product")
    saved = saved if isinstance(saved, str) else ""
    asked = " ".join(_URL.sub(" ", text).split())
    if saved and saved.lower() not in asked.lower():
        return saved
    return asked or saved


def _tapped(saved: dict, message: str) -> str | None:
    """El producto a buscar si el mensaje es uno de los botones que se ofrecieron."""
    actions = saved.get("actions")
    if not isinstance(actions, dict):
        return None
    action = actions.get(message)
    return action if isinstance(action, str) and action else None


async def ask_prais(user_id: str, message: str, on_search: OnSearch | None = None) -> PraisAnswer:
    """Contesta, y deja a mano la salida: afinar si hubo precios, soltar algo si no."""
    text = " ".join(message.split())
    again = _tapped(await dialog.load(user_id), text)
    answer = await _answer(user_id, again or text, on_search)
    answer.product = again or await _searched_product(user_id, text, answer)
    answer.priced = any(has_published_price(card) for card in answer.listings)
    answer.searched = answer.searched or bool(answer.listings)
    # Solo cuando no volvió nada que mostrar. Si hay listados, el texto que ya
    # existe dice más: puede ser el veredicto, o el aviso de que el resumen falló.
    if answer.product and not answer.listings:
        if answer.failed:
            answer.text = f"Falló la búsqueda de {answer.product}."
        elif answer.searched:
            answer.text = f"No encontré ningún precio publicado para {answer.product}."
    await _followups(user_id, answer.product, answer)
    return answer
