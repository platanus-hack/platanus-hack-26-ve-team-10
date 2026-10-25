import logging
from dataclasses import dataclass, field

from google.adk.agents.run_config import RunConfig
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.sessions.base_session_service import GetSessionConfig
from google.genai import types

from app.agents.clarify import (
    PendingProduct,
    Question,
    allow_search,
    clear_allowed_searches,
    family_of,
    forget_search,
    spoken_question,
    step,
)
from app.agents.listing import listings_from_tool_response
from app.agents.orchestrator import root_agent

FALLBACK_REPLY = "Algo falló de mi lado. Inténtalo otra vez en un momento."
log = logging.getLogger("prais.agent")

_pending: dict[str, PendingProduct] = {}
_MAX_PENDING = 500


@dataclass
class PraisAnswer:
    text: str
    listings: list[dict] = field(default_factory=list)
    choices: list[str] = field(default_factory=list)
    list_body: str = ""
    list_section: str = ""


# Un mensaje sano pide el modelo dos veces: decidir la búsqueda y escribir el veredicto.
# El tope de la librería es 500 por mensaje. Si el modelo no da una respuesta que
# la librería acepte, ella vuelve a preguntar hasta ese tope.
_RUN = RunConfig(max_llm_calls=4, get_session_config=GetSessionConfig(num_recent_events=12))

# Las sesiones viven en memoria: se pierden si Cloud Run reinicia la instancia. Suficiente para la demo.
runner = Runner(
    app_name="prais",
    agent=root_agent,
    session_service=InMemorySessionService(),
    auto_create_session=True,
)


def _event_parts(event: object) -> list[object]:
    content = getattr(event, "content", None)
    return list(getattr(content, "parts", None) or [])


def _event_listings(event: object) -> list[dict]:
    found = []
    for part in _event_parts(event):
        response = getattr(getattr(part, "function_response", None), "response", None)
        found.extend(listings_from_tool_response(response))
    return found


def _event_ask(event: object) -> dict | None:
    for part in _event_parts(event):
        response = getattr(getattr(part, "function_response", None), "response", None)
        if not isinstance(response, dict):
            continue
        ask = response.get("ask")
        if isinstance(ask, dict) and isinstance(ask.get("question"), str) and isinstance(ask.get("choices"), list):
            return ask
    return None


def _remember(user_id: str, pending: PendingProduct) -> None:
    if len(_pending) > _MAX_PENDING:
        _pending.clear()
    _pending[user_id] = pending


def drop_product_dialog(user_id: str) -> None:
    _pending.pop(user_id, None)
    forget_search(user_id)


def clear_product_dialog() -> None:
    _pending.clear()
    clear_allowed_searches()


def _question_answer(user_id: str, question: Question, product: str, closed: frozenset[str], family: str) -> PraisAnswer:
    _remember(user_id, PendingProduct(product, closed, family))
    forget_search(user_id)
    return PraisAnswer(
        text=spoken_question(question),
        choices=list(question.choices),
        list_body=question.text,
        list_section=question.section,
    )


def _answer_from_ask(user_id: str, ask: dict) -> PraisAnswer:
    choices = [choice for choice in ask["choices"] if isinstance(choice, str)]
    question = Question(
        text=ask["question"],
        choices=tuple(choices),
        dimension=str(ask.get("dimension") or "model"),
        section=str(ask.get("section") or "Opciones"),
    )
    product = ask.get("product") if isinstance(ask.get("product"), str) else ""
    return _question_answer(user_id, question, product, frozenset(), family_of(product) or "")


async def _run_agent(user_id: str, message: str) -> PraisAnswer:
    """Corre el modelo. El texto es la guía; listings sale del JSON de cada especialista."""
    reply = ""
    listings: list[dict] = []
    seen: set[str] = set()
    asked: dict | None = None
    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=user_id,
            new_message=types.Content(role="user", parts=[types.Part(text=message)]),
            run_config=_RUN,
        ):
            ask = _event_ask(event)
            if ask is not None:
                asked = ask
            if asked is None:
                for card in _event_listings(event):
                    url = card.get("url")
                    if isinstance(url, str) and url not in seen:
                        seen.add(url)
                        listings.append(card)
            if event.is_final_response() and event.content and event.content.parts:
                reply += "".join(part.text or "" for part in event.content.parts if not part.function_call)
    except Exception:
        log.exception("agent run failed")
        return PraisAnswer(text=reply.strip() or FALLBACK_REPLY, listings=listings)
    if asked is not None:
        return _answer_from_ask(user_id, asked)
    return PraisAnswer(text=reply.strip() or FALLBACK_REPLY, listings=listings)


async def ask_prais(user_id: str, message: str) -> PraisAnswer:
    """Pregunta una sola elección abierta y, si ya no queda ninguna, busca ese producto."""
    decided = step(_pending.get(user_id), message)
    if decided.question is not None:
        return _question_answer(user_id, decided.question, decided.product, decided.closed, decided.family)
    _pending.pop(user_id, None)
    allow_search(user_id, decided.product)
    return await _run_agent(user_id, decided.product)
