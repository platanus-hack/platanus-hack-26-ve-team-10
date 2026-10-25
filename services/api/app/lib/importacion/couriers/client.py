"""Lo que un courier necesita para cotizar, y cómo se le pide una página."""

from dataclasses import dataclass
from typing import Protocol


class PageClient(Protocol):
    async def get_text(self, url: str) -> str: ...

    async def post_json(self, url: str, body: dict) -> dict: ...


@dataclass(frozen=True)
class Shipment:
    billable_lb: float
    product_usd: float
