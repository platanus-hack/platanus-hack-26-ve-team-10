import logging
import os
from dataclasses import dataclass, field

from google.adk.agents.run_config import RunConfig
from google.adk.apps.app import App, EventsCompactionConfig
from google.adk.apps.llm_event_summarizer import LlmEventSummarizer
from google.adk.models import Gemini
from google.adk.runners import Runner
from google.genai import types

from app.agents.listing import listings_from_tool_response
from app.agents.orchestrator import root_agent
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
    """El agente lee el mensaje tal como llegó y decide si pregunta o busca."""
    return await _run_agent(user_id, message)
