import json
import os


def load_environment() -> None:
    # En Cloud Run los secretos llegan como UN secreto JSON montado en APP_SECRETS
    # ({"KAPSO_API_KEY": "...", ...}). Se vuelcan al entorno para que el resto del código
    # lea cada clave como variable normal, igual que en local con services/api/.env.
    raw = os.environ.get("APP_SECRETS")
    if raw:
        for key, value in json.loads(raw).items():
            os.environ.setdefault(key, str(value))

    # services/api/.env.example usa GOOGLE_GENAI_API_KEY; la librería de Gemini lee GOOGLE_API_KEY.
    if os.environ.get("GOOGLE_GENAI_API_KEY"):
        os.environ.setdefault("GOOGLE_API_KEY", os.environ["GOOGLE_GENAI_API_KEY"])
