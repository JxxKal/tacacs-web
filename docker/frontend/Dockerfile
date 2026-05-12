# Frontend build stage; the artifact is COPYed into the nginx image.
# Stub for M1; M4+ fills in the real build.

FROM node:22-alpine AS build
WORKDIR /app
# COPY frontend/package.json frontend/package-lock.json ./
# RUN npm ci
# COPY frontend/ ./
# RUN npm run build

# The frontend image is build-only; nginx's Dockerfile COPYs --from this stage.
CMD ["true"]
