# Frontend build stage. The nginx image's Dockerfile already builds the SPA
# inline with COPY --from=frontend-build, so this image is rarely consumed
# on its own; it's primarily for `docker compose build frontend` smoke-runs
# and for CI artefact extraction.

FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Tiny "result" image: just the dist tree, no runtime needed.
FROM busybox:1.36
COPY --from=build /app/dist /dist
CMD ["true"]
