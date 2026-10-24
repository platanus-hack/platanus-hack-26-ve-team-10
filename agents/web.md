# Web: apps/web

Una sola app de Next.js (App Router) para todo lo que se ve en usaprais.com. Corre en Cloud Run como imagen `standalone`.

## Rutas

```
apps/web/app/
  (main)/                Pública, indexable
    page.tsx             Landing
    blog/                Posts en MDX
  (directorio)/          Pública, indexable
    comercios/           Directorio de comercios
    comercios/[slug]/    Perfil del comercio con su puntaje de confianza
    p/[slug]/            Producto: comparación de precios
  chat/                  Chat con el agente (noindex)
  dashboard/             Usuario con sesión: zona, búsquedas guardadas, alertas de precio
  admin/                 Solo el equipo
    revision/            Cola del human loop
    fuentes/             Estado de la ingesta
    tasas/               Tasas de cambio
  api/
    search/route.ts      Proxy a POST /search del agente
  sitemap.ts
  robots.ts
```

Las URLs públicas van en español (`/comercios`, `/p/...`, `/blog`), porque es lo que busca la gente en Venezuela. Los grupos con paréntesis no cambian la URL: solo comparten layout.

## Reglas

- **La web no importa `@google/adk`.** Llama al agente por HTTP desde `app/api/search`, así todos los canales usan el mismo cerebro.
- **Los precios se muestran como dice core.** Cada precio lleva su moneda, su fuente, la fecha y la tasa si hubo conversión. Usa el formateador de `packages/core`, no `toFixed` sueltos.
- **El puntaje de confianza siempre se ve** junto al comercio, con las señales que lo forman.
- **Dashboard y admin requieren sesión.** El admin además exige que el usuario sea del equipo.
- **Las páginas públicas siguen [seo-geo.md](seo-geo.md).**
- **El chat** muestra las preguntas del onboarding (`kind: "question"`) como mensajes normales, y las ofertas como tarjetas.
- **Las variables de entorno las declara `.env.example`.** Como mínimo, `AGENT_URL`.

## Desarrollo y deploy

```bash
pnpm --filter @prais/web dev
pnpm --filter @prais/web build    # con output: "standalone"
```

`next.config.ts` tiene que llevar `output: "standalone"`. El Dockerfile y el deploy están en [gcp.md](gcp.md).

## Por decidir

- La librería de UI. La sugerencia es Tailwind con shadcn/ui, y los tokens salen de `design/brand/`.
- La auth: ver [architecture.md](architecture.md).
