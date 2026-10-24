import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.agent import FALLBACK_REPLY, ask_prais

router = APIRouter()
log = logging.getLogger("prais.chat")


class ChatBody(BaseModel):
    sessionId: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=1000)


# Chat de la web: la página llama a /api/chat y Next lo reenvía aquí.
@router.post("/chat")
async def chat(body: ChatBody):
    try:
        return {"reply": await ask_prais(f"web:{body.sessionId}", body.message)}
    except Exception:
        log.exception("chat failed")
        return JSONResponse({"reply": FALLBACK_REPLY}, status_code=502)
