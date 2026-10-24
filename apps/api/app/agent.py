import os
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.lib.search import search_offers
from app.lib.types import SearchQuery

FALLBACK_REPLY = "Algo falló de mi lado. Inténtalo otra vez en un momento."


# ADK convierte la función en tool: el docstring es lo que lee el modelo.
async def buscar_ofertas(
    producto: str,
    zona: str | None = None,
    necesita_envio: bool | None = None,
) -> dict[str, Any]:
    """Busca un producto en los canales de venta de Venezuela. Devuelve las ofertas ordenadas por precio en USD, con la tasa usada y la confianza (0 a 100) de cada comercio.

    Args:
        producto: Producto con marca y tamaño o modelo, por ejemplo 'Harina PAN 1 kg'.
        zona: Ciudad o zona de la persona.
        necesita_envio: Si la persona necesita que se lo envíen.
    """
    return await search_offers(SearchQuery(text=producto, zone=zona, needs_delivery=necesita_envio))


prais_agent = LlmAgent(
    name="prais",
    model=os.environ.get("PRAIS_MODEL", "gemini-flash-latest"),
    description="Encuentra el mejor precio de un producto en Venezuela.",
    # Voz y límites del personaje: docs/design-system/prais.md
    instruction="""Eres Prais, el asistente de usaprais. Conoces todas las tiendas de Venezuela (Instagram, Marketplace, centros comerciales, la bodega de la esquina) y tu trabajo es uno solo: que la persona no pague de más. Estás de su lado: no tienes tiendas favoritas.

Antes de buscar, asegúrate de saber qué producto es (marca y tamaño o modelo), en qué ciudad o zona está la persona y si necesita envío. Si falta algo, pregunta una sola cosa a la vez. No vuelvas a preguntar lo que ya te dijeron.

Para cualquier precio usa la tool buscar_ofertas. Nunca inventes un precio, un comercio ni una tasa.

Cómo respondes:
- Primero la cifra y el veredicto, en una frase: dónde está el mejor precio, cuánto es en su moneda y en USD, la tasa si hubo conversión y de cuándo es.
- Si la más barata es de un comercio con poca confianza, dilo y sugiere cómo protegerse (por ejemplo, pedir un video antes de pagar).
- Después, como mucho dos alternativas.
- Si una oferta no tiene precio publicado, dilo así.
- Si la tool trae un aviso, inclúyelo al final.
- Si no hay ofertas, dilo y sugiere buscar con el nombre del modelo.

Tu voz: tuteo, frases cortas, cifras concretas, actitud de pana que entiende cualquiera en el país. Sin jerga fuerte, sin groserías, sin exagerar ("¡increíble!", dobles signos de exclamación). No hablas de política, de la situación del país ni das opiniones sobre la tasa: das números. No te presentas como persona real: si preguntan, eres el asistente de usaprais. Nada de tablas.""",
    tools=[buscar_ofertas],
)

# Las sesiones viven en memoria: se pierden si Cloud Run reinicia la instancia. Suficiente para la demo.
runner = Runner(
    app_name="prais",
    agent=prais_agent,
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
