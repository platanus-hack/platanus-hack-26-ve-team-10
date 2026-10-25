import hashlib
import json
import os
from typing import Any

from google.api_core.exceptions import AlreadyExists
from google.cloud import tasks_v2

# Cola de Cloud Tasks para los mensajes de WhatsApp: el webhook valida la firma, encola y responde
# 200; la cola llama a /internal/whatsapp-task (esta misma API) con reintentos. Si TASKS_QUEUE no
# está definida (desarrollo local), no se usa la cola y el webhook procesa en segundo plano.

TASK_PATH = "/internal/whatsapp-task"

_client: tasks_v2.CloudTasksAsyncClient | None = None


def queue_enabled() -> bool:
    return bool(os.environ.get("TASKS_QUEUE"))


def _get_client() -> tasks_v2.CloudTasksAsyncClient:
    global _client
    if _client is None:
        _client = tasks_v2.CloudTasksAsyncClient()
    return _client


async def enqueue_whatsapp_event(event: dict[str, Any]) -> None:
    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    location = os.environ["TASKS_LOCATION"]
    queue = os.environ["TASKS_QUEUE"]
    self_url = os.environ["SELF_URL"]  # URL de este mismo servicio: destino de la tarea y audiencia del token
    client = _get_client()

    task = tasks_v2.Task(
        http_request=tasks_v2.HttpRequest(
            http_method=tasks_v2.HttpMethod.POST,
            url=f"{self_url}{TASK_PATH}",
            headers={"Content-Type": "application/json"},
            body=json.dumps(event).encode(),
            oidc_token=tasks_v2.OidcToken(service_account_email=os.environ["TASKS_OIDC_SA"], audience=self_url),
        )
    )
    # El id del mensaje es el nombre de la tarea: si Kapso reintenta la entrega, Cloud Tasks la
    # rechaza como duplicada y el usuario no recibe dos respuestas.
    message_id = (event.get("message") or {}).get("id")
    if message_id:
        task.name = client.task_path(project, location, queue, hashlib.sha256(message_id.encode()).hexdigest())

    try:
        await client.create_task(parent=client.queue_path(project, location, queue), task=task)
    except AlreadyExists:
        pass
