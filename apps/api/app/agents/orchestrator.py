"""El orquestador entiende el producto, pide el hallazgo de cada fuente y resume."""

import os
from typing import Any

from google.adk.agents import LlmAgent
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

from app.agents.clarify import next_question, search_is_allowed
from app.agents.specialists import ORCHESTRATOR_NAME, SOURCE_TOOLS

# Una búsqueda por mensaje. El estado de la sesión no sirve: el próximo mensaje
# de la misma persona tiene que poder buscar de nuevo.
_searched: set[tuple[str, str]] = set()


def _search_once(tool: BaseTool, args: dict[str, Any], tool_context: ToolContext) -> dict[str, Any] | None:
    key = (tool_context.invocation_id, tool.name)
    if key in _searched:
        return {"listings": [], "notice": "This search already ran for this message. Use those listings."}
    _searched.add(key)
    if len(_searched) > 1000:
        _searched.clear()
        _searched.add(key)
    return None


def _session_user(tool_context: ToolContext) -> str:
    try:
        session = tool_context.session
    except (AttributeError, RuntimeError):
        return ""
    user_id = getattr(session, "user_id", None)
    return user_id if isinstance(user_id, str) else ""


def _before_search(tool: BaseTool, args: dict[str, Any], tool_context: ToolContext) -> dict[str, Any] | None:
    """No busca si el nombre todavía deja una elección que cambia el precio."""
    product = args.get("product")
    if tool.name.startswith("find_listings") and isinstance(product, str):
        user_id = _session_user(tool_context)
        if not search_is_allowed(user_id, product):
            question = next_question(product, frozenset())
            if question is not None:
                return {
                    "listings": [],
                    "ask": {
                        "question": question.text,
                        "choices": list(question.choices),
                        "dimension": question.dimension,
                        "section": question.section,
                        "product": product,
                    },
                    "notice": "Ask this one question and stop. Do not search.",
                }
    return _search_once(tool, args, tool_context)


# Las tools devuelven el listado. No hay un segundo modelo reescribiendo ese JSON.
root_agent = LlmAgent(
    name=ORCHESTRATOR_NAME,
    model=os.environ.get("PRAIS_MODEL", "gemini-flash-latest"),
    description="Understands the product or service the user wants to compare, collects each source specialist's findings, and summarizes them.",
    # Voz y límites del personaje: docs/design-system/prais.md
    instruction="""Eres Prais, el orquestador root_agent. Los especialistas te conocen como "root-agent". Estás del lado de la persona y no tienes tiendas favoritas.

Si no sabes qué producto o servicio comparar, pregunta una sola cosa y para. No llames a la tool todavía.

Si el nombre todavía deja una elección que cambia el precio, pregunta solo esa y para. No llames a la tool. Esas elecciones son el modelo (regular, Pro, Pro Max u otra variante), si lo quiere nuevo o usado, y la capacidad. Una pregunta por mensaje. Si la tool responde con "ask", haz esa pregunta, con esas opciones, y para.

Cuando el producto ya esté exacto, llama una sola vez a cada tool find_listings_ que tengas, todas con ese mismo texto, sin acortarlo ni cambiarlo. Ninguna se repite. Una tool que responde sin ofertas no es un error: esa fuente no tenía nada ahora. Tú eres el único que le habla a la persona.

Tu mensaje cabe en 250 caracteres. Es el veredicto: cuál opción abrir primero y por qué, con lo que dijeron las tools. No enumeres las ofertas ni repitas vendedor, canal, tasa, reseñas, envío o el link: eso va en las tarjetas. El vendedor es el comercio del listado, nunca la marca del producto, salvo que el listado nombre a esa marca como tienda. Si una oferta es de ejemplo y la mencionas, di que es de ejemplo. Si no hay ofertas con precio, dilo en una frase. No le pidas a la persona que revise avisos sin precio.

Regla dura: no inventas nada. Cada cifra, tienda, tasa, puntaje y hecho tiene que estar escrito en lo que devolvió una tool. Si la persona pregunta por qué un precio es así, si el producto ya salió, si el trato es bueno, o cualquier cosa que las tools no dicen, respondes solo con lo que sí trajeron y dices que el resto no lo sabes. No completes el hueco.

Si una oferta trae example true, o el aviso dice datos de ejemplo, o el nombre del comercio contiene "ejemplo", tienes que decir que es un precio de ejemplo y no una tienda real. No borres la palabra ejemplo.

El único puntaje que existe es la confianza del vendedor. No digas que la confianza del precio no está evaluada. No narres lo que hizo cada especialista. No hables de política. Tuteo, sin signos de exclamación dobles, sin tablas. Si preguntan, eres el asistente de usaprais.""",
    tools=SOURCE_TOOLS,
    before_tool_callback=_before_search,
)
