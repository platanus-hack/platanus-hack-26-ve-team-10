# Plan del equipo

Frentes de trabajo que pueden avanzar en paralelo gracias a los [contratos](../docs/contracts.md). Cada frente tiene un dueño, toca sus archivos y entra por su propio PR.

| # | Frente | Archivos | Necesita | Listo cuando | Dueño |
|---|---|---|---|---|---|
| 1 | **Fuente: Firecrawl** (webs de tiendas) | `apps/api/app/lib/sources/firecrawl.py` | `FIRECRAWL_API_KEY` | `search_prices` devuelve ofertas reales de al menos 2 tiendas web, con los datos de [Tiendas web](../docs/sources.md#tiendas-web) que pide el puntaje de confianza | |
| 2 | **Fuente: Apify** (Instagram, TikTok, Facebook Marketplace) | `apps/api/app/lib/sources/apify_*.py` | `APIFY_TOKEN` | Ofertas reales con los datos del comercio que pide el puntaje de confianza ([Datos que el puntaje necesita](../docs/sources.md#datos-que-el-puntaje-necesita)). Como Apify tarda, el adapter lee el último resultado de un actor que corre antes, no lo dispara en cada consulta | |
| 3 | **Fuente: Mercado Libre** | `apps/api/app/lib/sources/mercadolibre.py` | App registrada en Mercado Libre (la API responde 403 sin token) | Ofertas reales de MLV con la reputación del vendedor ([Mercado Libre](../docs/sources.md#mercado-libre)), o un actor de Apify como plan B | |
| 4 | **Tasa** | `apps/api/app/lib/rate.py` | Decidir BCV, paralela o ambas | `get_rate()` devuelve la tasa del día con su fuente | |
| 5 | **WhatsApp** | `apps/api/app/routes/whatsapp.py` | Cuenta de Kapso, número, `KAPSO_API_KEY`, `KAPSO_WEBHOOK_SECRET` | Le escribes al número y Prais responde | |
| 6 | **Agente** | `apps/api/app/agent.py`, `resources/queries.md` | `GOOGLE_GENAI_API_KEY` | Las consultas de ejemplo de `resources/queries.md` dan respuestas correctas | |
| 7 | **Web** | `apps/web/` | Design system (`docs/design-system/`) | Chat con la marca de usaprais, usable en el celular | Genaro (sugerido) |
| 8 | **Deploy GCP** | `infra/`, `cloudbuild.*.yaml` y los `Dockerfile` de cada app | Proyecto con facturación | usaprais.com responde con la web y el backend: ver [gcp.md](../docs/gcp.md) | Dev de GCP |
| 9 | **Entrega** | `project-description.md`, `README.md`, `platanus-hack-project.jsonc` | Todo lo anterior | Validación de Platanus en verde y demo ensayada | |

## Orden

- **Sin bloqueos, arrancan ya:** 1, 2, 3, 4, 6 y 7. Trabajan contra los contratos, con la fuente de ejemplo mientras tanto.
- **Necesitan cuentas:** 5 (Kapso) y 8 (GCP). Conviene pedirlas primero.
- **Al final:** 9, cuando la demo funcione de punta a punta.

## Reglas para no pisarse

- Una rama y un PR por frente. Toca solo tus archivos. La excepción es la línea de registro en `sources/__init__.py`.
- Antes del PR: `git pull origin main`, `pnpm build && pnpm lint`. Después del merge: `pnpm sync`.
- Si necesitas cambiar un contrato (`types.py`, la forma de `/chat` o de `search_offers`), avisa en el canal del equipo antes de mergear.
- Las API keys no se suben al repo ni se pegan en el chat del equipo: cada uno las pone en su `apps/api/.env`. Para producción van a Secret Manager.
