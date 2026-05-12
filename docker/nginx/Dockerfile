# Reverse proxy with TLS termination. Serves the built React SPA + proxies /api and /saml.
# TLS cert + key are uploaded via the UI and persisted in the tls-state volume;
# nginx reloads on update. A self-signed bootstrap cert is generated on first start
# if no cert is present.
#
# Stub for M1; M5+ fills in the real config + reload mechanism.

FROM node:22-alpine AS frontend-build
WORKDIR /app
# COPY frontend/package.json frontend/package-lock.json ./
# RUN npm ci
# COPY frontend/ ./
# RUN npm run build

FROM nginx:1.27-alpine
RUN apk add --no-cache openssl curl

# COPY --from=frontend-build /app/dist /usr/share/nginx/html
# COPY docker/nginx/nginx.conf.template /etc/nginx/templates/default.conf.template
# COPY docker/nginx/entrypoint.sh /docker-entrypoint.d/30-tls-bootstrap.sh

EXPOSE 8080 8443
# CMD already inherited from upstream nginx image.
