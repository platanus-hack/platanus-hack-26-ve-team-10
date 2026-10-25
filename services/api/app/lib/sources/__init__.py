from app.lib.sources.mock import mock_source
from app.lib.types import Source

# Registro de fuentes. Para sumar una: crea sources/<fuente>.py con un objeto que cumpla Source
# (copia mock.py como modelo) y agrégalo a esta lista.
sources: list[Source] = [mock_source]
