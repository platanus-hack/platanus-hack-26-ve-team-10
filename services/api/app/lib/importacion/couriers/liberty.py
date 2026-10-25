"""Casillero aéreo Miami–Venezuela de Liberty, por el cotizador de su calculadora.

La calculadora pública (iqpack) arma el POST a `Cotizar`: el código de flete, los
países y el host salen del HTML, y el token sale del script que esa misma página
carga. Si la página cambia y no se puede leer, este courier no cotiza.
"""

import json
import re
from datetime import UTC, datetime
from urllib.parse import urljoin

from app.lib.importacion.couriers.client import PageClient, Shipment
from app.lib.importacion.landed import usd
from app.lib.types import CourierQuote

CALCULATOR_URL = "https://iqpack.libertyexpress.com/Calculator"
_ORIGIN = "https://iqpack.libertyexpress.com/"


async def quote_liberty(shipment: Shipment, client: PageClient) -> CourierQuote | None:
    page = await client.get_text(CALCULATOR_URL)
    config = liberty_config(page)
    if config is None:
        return None
    script = await client.get_text(urljoin(_ORIGIN, config["script"]))
    token = _token(script)
    if not token:
        return None
    body = _body(config, token, shipment)
    payload = await client.post_json(config["endpoint"], body)
    return liberty_from_payload(payload)


def liberty_config(page: str) -> dict | None:
    host = re.search(r"let localhost = '([^']+)'", page)
    script = re.search(r'src="(/js/calculadora/datos\.js[^"]*)"', page)
    countries = _array(page, "los_paises")
    freights = _array(page, "los_fletes")
    if not host or not script or countries is None or freights is None:
        return None
    origin = next((row for row in countries if row.get("isO2") == "US"), None)
    destination = next((row for row in countries if row.get("isO2") == "VE"), None)
    code = _casillero_code(freights)
    if not origin or not destination or not code:
        return None
    endpoint = host.group(1)
    if not endpoint.endswith("/"):
        endpoint += "/"
    return {
        "script": script.group(1),
        "endpoint": urljoin(endpoint, "Cotizar"),
        "route": f"{origin['iata_origen_por_defecto']}-{destination['iata_origen_por_defecto']}",
        "code": code,
        "origin_id": origin["id"],
        "destination_id": destination["id"],
    }


def liberty_from_payload(payload: dict, now: datetime | None = None) -> CourierQuote | None:
    valor = payload.get("valorCotizado")
    if not isinstance(valor, dict) or valor.get("neto") is None:
        results = payload.get("resultados")
        if isinstance(results, list) and results and isinstance(results[0], dict):
            valor = results[0].get("valorCotizado")
    if not isinstance(valor, dict):
        return None
    try:
        neto = float(valor["neto"])
        tax = float(valor.get("impuesto") or 0)
    except (TypeError, ValueError, KeyError):
        return None
    insurance = _insurance(payload)
    freight = usd(neto - insurance - tax)
    if freight < 0 or neto <= 0:
        return None
    moment = now or datetime.now(UTC)
    return CourierQuote(
        courier_id="cur:liberty",
        courier_name="Liberty Express",
        freight_usd=freight,
        tax_usd=usd(tax),
        insurance_usd=usd(insurance),
        includes_tax=False,
        quoted_at=moment.isoformat(),
        source="cotizador",
        tax_source="cotizado",
    )


def _body(config: dict, token: str, shipment: Shipment) -> dict:
    return {
        "token": token,
        "porCotizar": [
            {
                "ruta": config["route"],
                "codigo": config["code"],
                "guia": {
                    "PrepagoColectar": "C",
                    "idPaisOrigen": config["origin_id"],
                    "idPaisDestino": config["destination_id"],
                    "idDestino": 0,
                },
                "caja": {
                    "largo": "1.00",
                    "profundidad": "1.00",
                    "alto": "1.00",
                    "unidadMedidas": "IN",
                    "peso": f"{shipment.billable_lb:.2f}",
                    "unidadPeso": "LBS",
                    "fob": f"{shipment.product_usd:.2f}",
                    "iSO3_moneda": "USD",
                },
                "arancelArticulo": 0,
                "destino": None,
            }
        ],
    }


def _casillero_code(freights: list[dict]) -> str | None:
    for row in freights:
        if (
            row.get("pais_origen_ISO2") == "US"
            and row.get("pais_destino_ISO2") == "VE"
            and row.get("transporte") == "aereo"
            and row.get("termino") == "COL"
            and row.get("contenido") == "paquete"
            and row.get("especiales") in {"ninguno", ""}
            and not row.get("condicion")
        ):
            code = row.get("codigo_flete")
            return str(code) if code else None
    return None


def _insurance(payload: dict) -> float:
    total = 0.0
    results = payload.get("resultados")
    lines = []
    if isinstance(results, list) and results and isinstance(results[0], dict):
        quoted = results[0].get("productosCotizado")
        if isinstance(quoted, list):
            lines = quoted
    for line in lines:
        if not isinstance(line, dict) or "SEGURO" not in str(line.get("nombre") or "").upper():
            continue
        cotizado = line.get("cotizado")
        if isinstance(cotizado, dict) and cotizado.get("bruto") is not None:
            total += float(cotizado["bruto"])
    return total


def _token(script: str) -> str | None:
    match = re.search(r"token:\s*['\"]([0-9a-fA-F]{16,})['\"]", script)
    return match.group(1) if match else None


def _array(page: str, name: str) -> list[dict] | None:
    marker = f"let {name} = "
    start_at = page.find(marker)
    if start_at < 0:
        return None
    start = page.find("[", start_at)
    depth = 0
    for index, char in enumerate(page[start:], start):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(page[start : index + 1])
                except json.JSONDecodeError:
                    return None
                if isinstance(parsed, list) and all(isinstance(row, dict) for row in parsed):
                    return parsed
                return None
    return None
