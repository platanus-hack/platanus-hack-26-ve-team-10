from fastapi import APIRouter, HTTPException

from app.lib import catalogo

router = APIRouter(prefix="/catalogo")


# Páginas públicas del catálogo. La web las pide al construir y al revalidar (services/web/src/lib/catalogo.ts).
# Cada respuesta trae "indexable" y "datosDeEjemplo": la web pone noindex y el aviso según eso.
def _o_404(pagina):
    if pagina is None:
        raise HTTPException(status_code=404, detail="No existe")
    return pagina


@router.get("/rutas")
async def rutas():
    return catalogo.rutas()


@router.get("/sitemap")
async def sitemap():
    return await catalogo.sitemap()


@router.get("/categorias")
async def categorias():
    return catalogo.categorias()


@router.get("/marcas")
async def marcas():
    return catalogo.indice_marcas()


@router.get("/producto/{slug_id}")
async def producto(slug_id: str):
    return _o_404(await catalogo.pagina_producto(slug_id))


@router.get("/categoria/{cat}")
async def categoria(cat: str):
    return _o_404(await catalogo.pagina_categoria(cat))


@router.get("/categoria/{cat}/{sub}")
async def subcategoria(cat: str, sub: str):
    return _o_404(await catalogo.pagina_categoria(cat, sub))


@router.get("/marca/{slug}")
async def marca(slug: str):
    return _o_404(await catalogo.pagina_marca(slug))
