# Reverse proxy with TLS termination. Serves the built React SPA + proxies the
# backend's `/api`, `/login`, `/logout`, `/me`, `/healthz` namespaces.
#
# TLS cert + key are persisted in the `tls-state` volume; an entrypoint hook
# generates a self-signed bootstrap cert on first start if no cert is present.
# M7 wires the UI-driven cert upload + nginx reload on top.

FROM node:22-alpine AS frontend-build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine
RUN apk add --no-cache openssl curl

COPY --from=frontend-build /app/dist /usr/share/nginx/html
COPY docker/nginx/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY docker/nginx/entrypoint.sh /docker-entrypoint.d/30-tls-bootstrap.sh
RUN chmod +x /docker-entrypoint.d/30-tls-bootstrap.sh

EXPOSE 8080 8443
# CMD inherited from upstream nginx image.
