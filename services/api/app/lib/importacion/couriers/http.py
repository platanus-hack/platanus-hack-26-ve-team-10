"""Cliente HTTP de las páginas públicas. No imita un navegador para saltar un bloqueo."""

import time

import httpx

_CACHE_S = 6 * 60 * 60
_HEADERS = {"accept": "text/html,application/json", "user-agent": "Prais/1.0 (+https://usaprais.com)"}


class HttpPages:
    def __init__(self) -> None:
        self._pages: dict[str, tuple[float, str]] = {}

    async def get_text(self, url: str) -> str:
        hit = self._pages.get(url)
        if hit and time.monotonic() < hit[0]:
            return hit[1]
        async with httpx.AsyncClient(timeout=8, follow_redirects=True, headers=_HEADERS) as client:
            response = await client.get(url)
            response.raise_for_status()
            text = response.text
        self._pages[url] = (time.monotonic() + _CACHE_S, text)
        return text

    async def post_json(self, url: str, body: dict) -> dict:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True, headers=_HEADERS) as client:
            response = await client.post(url, json=body)
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict):
            raise TypeError("la cotización no vino en un objeto")
        return data
