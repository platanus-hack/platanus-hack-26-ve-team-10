from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agents.orchestrator import root_agent

FALLBACK_REPLY = "Algo falló de mi lado. Inténtalo otra vez en un momento."

# Las sesiones viven en memoria: se pierden si Cloud Run reinicia la instancia. Suficiente para la demo.
runner = Runner(
    app_name="prais",
    agent=root_agent,
    session_service=InMemorySessionService(),
    auto_create_session=True,
)


async def ask_prais(user_id: str, message: str) -> str:
    """Corre el agente y devuelve el texto de su respuesta. Cada user_id tiene su conversación."""
    reply = ""
    async for event in runner.run_async(
        user_id=user_id,
        session_id=user_id,
        new_message=types.Content(role="user", parts=[types.Part(text=message)]),
    ):
        if event.is_final_response() and event.content and event.content.parts:
            reply += "".join(part.text or "" for part in event.content.parts)
    return reply.strip() or FALLBACK_REPLY
