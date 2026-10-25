from app.lib.sources.apify import instagram_source, tiktok_source
from app.lib.sources.facebook import facebook_source
from app.lib.sources.mercadolibre import mercadolibre_source
from app.lib.sources.mock import mock_source
from app.lib.types import Source

# Registro de fuentes. Para sumar una: crea sources/<fuente>.py con un objeto que cumpla Source
# (copia mock.py como modelo) y agrégalo a esta lista.
sources: list[Source] = [mock_source, instagram_source, tiktok_source, mercadolibre_source, facebook_source]
