"""Corre los actores de Apify una vez y muestra lo que trae cada fuente. Gasta créditos.

Sirve para comprobar que APIFY_TOKEN funciona y para ver los campos reales del actor antes de
tocar el adapter (docs/sources.md avisa que cambian entre versiones).

Uso (desde apps/api): .venv/bin/python scripts/apify_prueba.py "iPhone 15 128 GB" [instagram|tiktok]
"""

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.lib.sources import apify

product = sys.argv[1] if len(sys.argv) > 1 else "iPhone 15 128 GB"
which = sys.argv[2] if len(sys.argv) > 2 else "instagram"
source = apify.instagram_source if which == "instagram" else apify.tiktok_source


async def main() -> None:
    if not os.environ.get("APIFY_TOKEN"):
        sys.exit("Falta APIFY_TOKEN. Ponlo en apps/api/.env y corre: set -a; . .env; set +a")
    source.enabled = True
    run_input = source._run_input(product)
    print(f"actor {source.actor}\ninput {json.dumps(run_input, ensure_ascii=False)}\n")
    if not run_input:
        sys.exit("Sin hashtag para ese producto: Instagram no tiene por dónde entrar.")

    items = await apify.run_actor(source.actor, run_input)
    print(f"{len(items)} publicaciones. La primera, entera:\n{json.dumps(items[:1], ensure_ascii=False, indent=2)}\n")

    # Se leen las publicaciones que ya trajimos: volver a llamar a search() pagaría otra corrida.
    result = source._read(items, product, "")
    for offer in result.offers:
        merchant = next(m for m in result.merchants if m.id == offer.merchant_id)
        price = f"{offer.price.amount} {offer.price.currency}" if offer.price else "precio al DM"
        print(f"{price:>18}  {merchant.name:<24} {offer.title[:50]:<52} {offer.url}")
    print(f"\n{len(result.offers)} ofertas de {len(result.merchants)} comercios.")


asyncio.run(main())
