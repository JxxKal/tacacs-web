# Backend container: FastAPI app, AD-sync worker, SAML SP, accounting-ingestor.
# Stub for M1; M2+ fills in the real install + entrypoint.

FROM python:3.13-slim-bookworm AS build
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
# COPY backend/pyproject.toml backend/poetry.lock ./
# RUN pip install --no-cache-dir uv && uv pip install --system --requirements pyproject.toml

FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        libldap-2.5-0 \
        libxmlsec1-openssl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -g 1000 app \
    && useradd -u 1000 -g 1000 -d /app -m -s /usr/sbin/nologin app

WORKDIR /app
# COPY --from=build /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
# COPY backend/ /app/

USER 1000:1000
EXPOSE 8000
# ENTRYPOINT ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
CMD ["sleep", "infinity"]  # M1 placeholder
