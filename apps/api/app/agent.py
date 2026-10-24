import logging
from dataclasses import dataclass, field

from google.adk.agents.run_config import RunConfig
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.sessions.base_session_service import GetSessionConfig
from google.genai import types

from app.agents.listing import listings_from_tool_response
from app.agents.orchestrator import root_agent

FALLBACK_REPLY = "Algo falló de mi lado. Inténtalo otra vez en un momento."
log = logging.getLogger("prais.agent")


@dataclass
class PraisAnswer:
    text: str
    listings: list[dict] = field(default_factory=list)

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


def _event_listings(event: types.Content | object) -> list[dict]:
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) or []
    found = []
    for part in parts:
        response = getattr(getattr(part, "function_response", None), "response", None)
        found.extend(listings_from_tool_response(response))
    return found


async def ask_prais(user_id: str, message: str) -> PraisAnswer:
    """Corre el agente. El texto es la guía; listings sale del JSON de cada especialista."""
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
        return PraisAnswer(text=reply.strip() or FALLBACK_REPLY, listings=listings)
    return PraisAnswer(text=reply.strip() or FALLBACK_REPLY, listings=listings)
