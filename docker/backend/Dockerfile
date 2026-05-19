# Backend container: FastAPI app, AD-sync worker, SAML SP, accounting-ingestor.

FROM python:3.13-slim-bookworm AS build
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Native build deps: xmlsec / lxml require libxmlsec1, libxml2, and a C
# toolchain. Runtime deps are in the final stage.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libxml2-dev \
        libxmlsec1-dev \
        libxmlsec1-openssl \
        pkg-config \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

WORKDIR /app
COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
RUN uv pip install --system --no-cache .

FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        libldap-2.5-0 \
        libxml2 \
        libxmlsec1 \
        libxmlsec1-openssl \
        xmlsec1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1000 app \
    && useradd -u 1000 -g 1000 -d /app -m -s /usr/sbin/nologin app \
    && mkdir -p /var/lib/tacacs-web/tls /var/lib/tacacs-web/tac_plus-ng \
    && chown -R 1000:1000 /var/lib/tacacs-web

WORKDIR /app
COPY --from=build /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=build /usr/local/bin /usr/local/bin
COPY --from=build /app /app

USER 1000:1000
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
