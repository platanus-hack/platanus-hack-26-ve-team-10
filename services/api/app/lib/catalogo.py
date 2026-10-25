import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any

from app.lib.rate import get_rate
from app.lib.search import search_offers
from app.lib.types import SearchQuery

# Motor de las páginas públicas del catálogo (docs/ficha-producto.md, docs/categoria.md, docs/marca.md).
# El catálogo (categorías, marcas, modelos y facetas) sale de catalogo.json. Los precios NO están
# aquí: cada modelo pide sus ofertas a search_offers, igual que el agente. Hoy responde la fuente de
# ejemplo; cuando se conecten fuentes reales, las páginas pasan a datos reales sin tocar este archivo.
#
# Una página solo es indexable con ofertas de fuentes reales. Con datos de ejemplo sale noindex,
# fuera del sitemap y con aviso: Google nunca ve precios inventados como si fueran reales.

PAIS = "ve"
FUENTES_DE_EJEMPLO = {"ejemplo"}
MIN_MODELOS_MARCA = 5  # categoría + marca: modelos con ofertas reales para indexar
MIN_MODELOS_FACETA = 5
MIN_CATEGORIAS_MARCA = 2  # con menos, la página de marca redirige a su categoría + marca
CACHE_S = 15 * 60

_DATA = json.loads((Path(__file__).resolve().parent / "catalogo.json").read_text(encoding="utf-8"))
CATEGORIAS = {c["slug"]: c for c in _DATA["categorias"]}
MARCAS = {m["slug"]: m for m in _DATA["marcas"]}
FACETAS = {(f["categoria"], f["slug"]): f for f in _DATA["facetas"]}
PRODUCTOS = sorted(_DATA["productos"], key=lambda p: -p["volumen"])
POR_ID = {p["id"]: p for p in PRODUCTOS}

_cache: dict[str, tuple[float, dict[str, Any]]] = {}


# ── URLs ─────────────────────────────────────────────────────────────────────────────────────


def url_producto(p: dict) -> str:
    return f"/{PAIS}/p/{p['slug']}-{p['id']}"


def url_categoria(cat: str, sub: str | None = None) -> str:
    return f"/{PAIS}/{cat}/{sub}" if sub else f"/{PAIS}/{cat}"


def url_marca(marca: str) -> str:
    cats = categorias_de_marca(marca)
    # Marca de una sola categoría: su página es la de categoría + marca (docs/marca.md).
    if len(cats) < MIN_CATEGORIAS_MARCA and cats:
        return url_categoria(cats[0], marca)
    return f"/{PAIS}/marca/{marca}"


def categorias_de_marca(marca: str) -> list[str]:
    return list(dict.fromkeys(p["categoria"] for p in PRODUCTOS if p["marca"] == marca))


# ── Ofertas de un modelo ─────────────────────────────────────────────────────────────────────

_USADO = re.compile(r"\b(usad[oa]s?|segunda mano)\b", re.IGNORECASE)
_REACONDICIONADO = re.compile(r"\b(reacondicionad[oa]s?|refurbished)\b", re.IGNORECASE)
_CAPACIDAD = re.compile(r"\b(\d+)\s?(GB|TB)\b", re.IGNORECASE)


def _condicion(titulo: str) -> str:
    if _REACONDICIONADO.search(titulo):
        return "reacondicionado"
    if _USADO.search(titulo):
        return "usado"
    return "nuevo"


def _confianza_texto(trust: int) -> str:
    if trust >= 70:
        return "Vendedor confiable"
    if trust >= 50:
        return "Buenas referencias"
    return "Pocas referencias"


async def ofertas_de(p: dict) -> dict[str, Any]:
    hit = _cache.get(p["id"])
    if hit and time.monotonic() - hit[0] < CACHE_S:
        return hit[1]
    result, rate = await asyncio.gather(search_offers(SearchQuery(text=p["busqueda"])), get_rate())
    ofertas = []
    for o in result["offers"]:
        capacidad = _CAPACIDAD.search(o["title"])
        usd = o["priceUsd"]
        ofertas.append(
            {
                "titulo": o["title"],
                "url": o["url"],
                "comercio": o["merchant"]["name"],
                "canal": o["merchant"]["channel"],
                "zona": o["merchant"]["zone"],
                "envia": o["merchant"]["delivers"],
                "confianza": o["merchant"]["trust"],
                "confianzaTexto": _confianza_texto(o["merchant"]["trust"]),
                "condicion": _condicion(o["title"]),
                "variante": f"{capacidad.group(1)} {capacidad.group(2).upper()}" if capacidad else None,
                "usd": usd,
                "bs": round(usd * rate.usd_to_ves, 2) if usd is not None else None,
                "precioPublicado": o["price"],
                "tasaUsada": o["rate"],
                "visto": o["seenAt"],
                "fuente": o["source"],
                "deEjemplo": o["source"] in FUENTES_DE_EJEMPLO,
            }
        )
    con_precio = [o for o in ofertas if o["usd"] is not None]
    nuevas = [o["usd"] for o in con_precio if o["condicion"] == "nuevo"]
    usadas = [o["usd"] for o in con_precio if o["condicion"] == "usado"]
    reacond = [o["usd"] for o in con_precio if o["condicion"] == "reacondicionado"]
    mas_barata = min((o for o in con_precio if o["condicion"] == "nuevo"), key=lambda o: o["usd"], default=None)
    data = {
        "ofertas": ofertas,
        "nuevoDesdeComercio": mas_barata["comercio"] if mas_barata else None,
        "nuevoDesde": min(nuevas, default=None),
        "nuevoHasta": max(nuevas, default=None),
        "usadoDesde": min(usadas, default=None),
        "reacondicionadoDesde": min(reacond, default=None),
        "comercios": len({o["comercio"] for o in ofertas}),
        "actualizado": max((o["visto"] for o in ofertas), default=None),
        "reales": sum(1 for o in con_precio if not o["deEjemplo"]),
        "deEjemplo": any(o["deEjemplo"] for o in ofertas),
    }
    _cache[p["id"]] = (time.monotonic(), data)
    return data


async def _tasa() -> dict[str, Any]:
    rate = await get_rate()
    return {"fuente": rate.source, "usdToVes": rate.usd_to_ves, "fecha": rate.observed_at}


def _desde(o: dict) -> tuple[float | None, str]:
    if o["nuevoDesde"] is not None:
        return o["nuevoDesde"], "nuevo"
    if o["usadoDesde"] is not None:
        return o["usadoDesde"], "usado"
    return o["reacondicionadoDesde"], "reacondicionado"


def _tarjeta(p: dict, o: dict, tasa: dict) -> dict[str, Any]:
    usd, condicion = _desde(o)
    return {
        "id": p["id"],
        "nombre": p["nombre"],
        "url": url_producto(p),
        "usd": usd,
        "bs": round(usd * tasa["usdToVes"], 2) if usd is not None else None,
        "condicion": condicion,
        "comercios": o["comercios"],
        "volumen": p["volumen"],
    }


async def _listado(productos: list[dict]) -> list[tuple[dict, dict]]:
    ofertas = await asyncio.gather(*(ofertas_de(p) for p in productos))
    pares = [(p, o) for p, o in zip(productos, ofertas) if o["ofertas"]]
    # Popularidad: volumen de búsqueda del modelo y, a igual volumen, más comercios.
    pares.sort(key=lambda par: (-par[0]["volumen"], -par[1]["comercios"]))
    return pares


def _resumen(pares: list[tuple[dict, dict]], tasa: dict) -> dict[str, Any]:
    if not pares:
        return {"modelos": 0}
    con_precio = [(p, o, _desde(o)[0]) for p, o in pares if _desde(o)[0] is not None]
    barato = min(con_precio, key=lambda t: t[2]) if con_precio else None
    comercios = {of["comercio"] for _, o in pares for of in o["ofertas"]}
    return {
        "modelos": len(pares),
        "comercios": len(comercios),
        "desde": barato[2] if barato else None,
        "desdeBs": round(barato[2] * tasa["usdToVes"], 2) if barato else None,
        "masBuscado": {"nombre": pares[0][0]["nombre"], "url": url_producto(pares[0][0])},
        "masBarato": {"nombre": barato[0]["nombre"], "url": url_producto(barato[0]), "usd": barato[2]} if barato else None,
        "actualizado": max((o["actualizado"] for _, o in pares if o["actualizado"]), default=None),
    }


def _datos_de_ejemplo(pares: list[tuple[dict, dict]]) -> bool:
    return any(o["deEjemplo"] for _, o in pares)


def _marca(slug: str) -> dict[str, str]:
    m = MARCAS[slug]
    return {"slug": slug, "nombre": m["nombre"], "url": url_marca(slug)}


def _categoria(slug: str) -> dict[str, Any]:
    c = CATEGORIAS[slug]
    return {k: c[k] for k in ("slug", "nombre", "singular", "sinonimos")} | {"url": url_categoria(slug)}


# ── Páginas ──────────────────────────────────────────────────────────────────────────────────


async def pagina_producto(slug_id: str) -> dict[str, Any] | None:
    p = POR_ID.get(slug_id.rsplit("-", 1)[-1])
    if not p:
        return None
    if slug_id != f"{p['slug']}-{p['id']}":
        return {"redirect": url_producto(p)}  # el slug cambió: el id resuelve y la URL vieja redirige
    o, tasa = await asyncio.gather(ofertas_de(p), _tasa())
    variantes: dict[str, float] = {}
    for of in o["ofertas"]:
        if of["variante"] and of["usd"] is not None and of["condicion"] == "nuevo":
            variantes[of["variante"]] = min(of["usd"], variantes.get(of["variante"], of["usd"]))
    # Alternativas: los 4 modelos de la misma categoría con el precio "desde" más cercano.
    precio = _desde(o)[0]
    hermanos = [x for x in PRODUCTOS if x["categoria"] == p["categoria"] and x["id"] != p["id"]]
    cercanos = [(x, ox) for x, ox in await _listado(hermanos) if _desde(ox)[0] is not None]
    if precio is not None:
        cercanos.sort(key=lambda par: abs(_desde(par[1])[0] - precio))
    alternativas = [_tarjeta(x, ox, tasa) for x, ox in cercanos[:4]]
    return {
        "producto": {
            "id": p["id"],
            "nombre": p["nombre"],
            "serie": p["serie"],
            "url": url_producto(p),
            "marca": _marca(p["marca"]),
            "categoria": _categoria(p["categoria"]),
            "volumen": p["volumen"],
        },
        "resumen": {
            k: o[k]
            for k in ("nuevoDesde", "nuevoDesdeComercio", "nuevoHasta", "usadoDesde", "reacondicionadoDesde", "comercios", "actualizado")
        }
        | {"nuevoDesdeBs": round(o["nuevoDesde"] * tasa["usdToVes"], 2) if o["nuevoDesde"] else None},
        "ofertas": o["ofertas"],
        "variantes": [{"nombre": k, "desde": v} for k, v in sorted(variantes.items(), key=lambda kv: kv[1])],
        "alternativas": alternativas,
        "tasa": tasa,
        "indexable": o["reales"] > 0,
        "datosDeEjemplo": o["deEjemplo"],
    }


async def pagina_categoria(cat: str, sub: str | None = None) -> dict[str, Any] | None:
    if cat not in CATEGORIAS:
        return None
    marca = sub if sub in MARCAS else None
    faceta = FACETAS.get((cat, sub)) if sub and not marca else None
    if sub and not (marca or faceta):
        return None
    productos = [p for p in PRODUCTOS if p["categoria"] == cat]
    if marca:
        productos = [p for p in productos if p["marca"] == marca]
    if faceta:
        productos = [p for p in productos if p["atributos"].get(faceta["atributo"]) == faceta["valor"]]
    if not productos:
        return None
    pares, tasa = await asyncio.gather(_listado(productos), _tasa())
    reales = sum(1 for _, o in pares if o["reales"])
    c = CATEGORIAS[cat]
    if marca:
        tipo, titulo = "marca", f"{c['nombre']} {MARCAS[marca]['nombre']}"
        indexable = reales >= MIN_MODELOS_MARCA
    elif faceta:
        tipo, titulo = "faceta", faceta["nombre"]
        indexable = faceta["volumen"] > 0 and reales >= MIN_MODELOS_FACETA
    else:
        tipo, titulo = "categoria", c["nombre"]
        indexable = reales > 0

    todos = [p for p in PRODUCTOS if p["categoria"] == cat]
    marcas = {}
    for p in todos:
        marcas.setdefault(p["marca"], 0)
        marcas[p["marca"]] += 1
    series: dict[str, int] = {}
    for p in productos:
        series[p["serie"]] = series.get(p["serie"], 0) + 1
    return {
        "tipo": tipo,
        "titulo": titulo,
        "url": url_categoria(cat, sub),
        "categoria": _categoria(cat),
        "marca": _marca(marca) if marca else None,
        "faceta": {"slug": faceta["slug"], "nombre": faceta["nombre"]} if faceta else None,
        "resumen": _resumen(pares, tasa),
        "productos": [_tarjeta(p, o, tasa) for p, o in pares],
        "marcas": [
            {"slug": m, "nombre": MARCAS[m]["nombre"], "url": url_categoria(cat, m), "modelos": n}
            for m, n in sorted(marcas.items(), key=lambda kv: -kv[1])
        ],
        "facetas": [{"nombre": f["nombre"], "url": url_categoria(cat, f["slug"])} for (fc, _), f in FACETAS.items() if fc == cat],
        "series": [{"nombre": s, "modelos": n} for s, n in sorted(series.items(), key=lambda kv: -kv[1])] if marca else [],
        "tasa": tasa,
        "indexable": indexable,
        "datosDeEjemplo": _datos_de_ejemplo(pares),
    }


async def pagina_marca(slug: str) -> dict[str, Any] | None:
    if slug not in MARCAS:
        return None
    cats = categorias_de_marca(slug)
    if not cats:
        return None
    if len(cats) < MIN_CATEGORIAS_MARCA:
        return {"redirect": url_categoria(cats[0], slug)}
    productos = [p for p in PRODUCTOS if p["marca"] == slug]
    pares, tasa = await asyncio.gather(_listado(productos), _tasa())
    por_cat: dict[str, list[tuple[dict, dict]]] = {}
    for p, o in pares:
        por_cat.setdefault(p["categoria"], []).append((p, o))
    comercios: dict[str, dict[str, Any]] = {}
    for _, o in pares:
        for of in o["ofertas"]:
            c = comercios.setdefault(of["comercio"], {"nombre": of["comercio"], "canal": of["canal"], "ofertas": 0, "confianza": of["confianza"]})
            c["ofertas"] += 1
    m = MARCAS[slug]
    return {
        "marca": _marca(slug),
        "titulo": f"{m['nombre']} en Venezuela",
        "url": f"/{PAIS}/marca/{slug}",
        "resumen": _resumen(pares, tasa) | {"categorias": len(por_cat)},
        "categorias": [
            {
                "nombre": f"{CATEGORIAS[c]['nombre']} {m['nombre']}",
                "url": url_categoria(c, slug),
                "modelos": len(ps),
                "desde": min((d for d in (_desde(o)[0] for _, o in ps) if d is not None), default=None),
            }
            for c, ps in sorted(por_cat.items(), key=lambda kv: -len(kv[1]))
        ],
        "top": [_tarjeta(p, o, tasa) for p, o in pares[:8]],
        "comercios": [
            c | {"confianzaTexto": _confianza_texto(c["confianza"])}
            for c in sorted(comercios.values(), key=lambda c: -c["ofertas"])[:6]
        ],
        "tasa": tasa,
        "indexable": sum(1 for c, ps in por_cat.items() if any(o["reales"] for _, o in ps)) >= MIN_CATEGORIAS_MARCA,
        "datosDeEjemplo": _datos_de_ejemplo(pares),
    }


def indice_marcas() -> list[dict[str, Any]]:
    out = []
    for slug, m in sorted(MARCAS.items(), key=lambda kv: kv[1]["nombre"].lower()):
        cats = categorias_de_marca(slug)
        if not cats:
            continue
        destino = f"{CATEGORIAS[cats[0]]['nombre']} {m['nombre']}" if len(cats) < MIN_CATEGORIAS_MARCA else "Varias categorías"
        modelos = sum(1 for p in PRODUCTOS if p["marca"] == slug)
        out.append({"slug": slug, "nombre": m["nombre"], "url": url_marca(slug), "modelos": modelos, "destino": destino})
    return out


def categorias() -> list[dict[str, Any]]:
    return [_categoria(c) | {"grupo": CATEGORIAS[c]["grupo"]} for c in CATEGORIAS if any(p["categoria"] == c for p in PRODUCTOS)]


def rutas() -> dict[str, list[Any]]:
    # Todas las rutas que existen, indexables o no: la web las pre-renderiza.
    subs = {(p["categoria"], p["marca"]) for p in PRODUCTOS}
    subs |= {k for k in FACETAS if any(p["categoria"] == k[0] and p["atributos"].get(FACETAS[k]["atributo"]) == FACETAS[k]["valor"] for p in PRODUCTOS)}
    return {
        "productos": [f"{p['slug']}-{p['id']}" for p in PRODUCTOS],
        "categorias": [c["slug"] for c in categorias()],
        "subcategorias": [[c, s] for c, s in sorted(subs)],
        "marcas": [m for m in MARCAS if len(categorias_de_marca(m)) >= MIN_CATEGORIAS_MARCA],
    }


async def sitemap() -> list[dict[str, Any]]:
    # Solo las páginas indexables, es decir, con ofertas de fuentes reales.
    r = rutas()
    paginas = await asyncio.gather(
        *(pagina_producto(s) for s in r["productos"]),
        *(pagina_categoria(c) for c in r["categorias"]),
        *(pagina_categoria(c, s) for c, s in r["subcategorias"]),
        *(pagina_marca(m) for m in r["marcas"]),
    )
    out = []
    for pg in paginas:
        if not pg or not pg.get("indexable"):
            continue
        url = pg["producto"]["url"] if "producto" in pg else pg["url"]
        actualizado = pg["resumen"].get("actualizado")
        out.append({"url": url, "actualizado": actualizado})
    return out
