ARG PYTHON_IMAGE=python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e

FROM ${PYTHON_IMAGE} AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir uv==0.12.11

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN /opt/venv/bin/uv sync --frozen --no-dev

FROM ${PYTHON_IMAGE} AS runtime

ARG APP_UID=10001
ARG APP_GID=10001

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH \
    APP_ENV=production

RUN groupadd --gid "${APP_GID}" shopmate \
    && useradd --uid "${APP_UID}" --gid shopmate --create-home --shell /usr/sbin/nologin shopmate

WORKDIR /app

COPY --from=builder --chown=shopmate:shopmate /opt/venv /opt/venv
COPY --chown=shopmate:shopmate alembic.ini ./
COPY --chown=shopmate:shopmate alembic ./alembic
COPY --chown=shopmate:shopmate src ./src

USER 10001:10001

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read()"]

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn shopmate_ecommerce_assistant.main:app --host 0.0.0.0 --port 8000 --no-access-log"]
