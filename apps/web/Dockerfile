# Contexto: la raíz del repo (workspace de pnpm). docker build -f apps/web/Dockerfile .
FROM node:22-alpine AS build
RUN corepack enable
WORKDIR /repo
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
COPY apps/api/package.json apps/api/
# --ignore-scripts: el `prepare` de la raíz configura git y aquí no hay git.
RUN pnpm install --frozen-lockfile --ignore-scripts --filter @prais/web...
COPY apps/web apps/web
# Next fija el destino del rewrite /api/* al CONSTRUIR: API_URL tiene que llegar como build-arg.
ARG API_URL
ENV API_URL=$API_URL \
    NEXT_TELEMETRY_DISABLED=1
RUN test -n "$API_URL" || (echo "falta --build-arg API_URL" >&2; exit 1)
RUN pnpm --filter @prais/web build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=8080
# En un monorepo el standalone conserva la ruta del workspace: el servidor queda en apps/web/server.js.
COPY --from=build --chown=node:node /repo/apps/web/.next/standalone ./
COPY --from=build --chown=node:node /repo/apps/web/.next/static ./apps/web/.next/static
COPY --from=build --chown=node:node /repo/apps/web/public ./apps/web/public
USER node
EXPOSE 8080
CMD ["node", "apps/web/server.js"]
