from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.routes import catalogo, chat, images, whatsapp
from app.routes.mcp import mcp_app, mcp_server


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with mcp_server.session_manager.run():
        yield


# Sin /docs ni /openapi.json: el backend es público y no hace falta exponerlos.
app = FastAPI(title="prais-api", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.exception_handler(RequestValidationError)
async def invalid_body(_: Request, __: RequestValidationError):
    return JSONResponse({"error": "Body inválido"}, status_code=400)


@app.get("/health")
async def health():
    return {"ok": True}


app.include_router(chat.router)
app.include_router(whatsapp.router)
app.include_router(catalogo.router)
app.include_router(images.router)
app.mount("/", mcp_app)  # /mcp: va al final para que las rutas de arriba tengan prioridad
