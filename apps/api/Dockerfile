# API image: FastAPI + SQLite, no build toolchain required at runtime.
FROM python:3.12-slim AS base

# uv is the project's single Python runner (ADR-0001 implementation notes).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Dependencies first so a source change does not invalidate the install layer.
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-install-project --no-dev 2>/dev/null \
    || uv sync --no-install-project --no-dev

COPY app ./app
COPY README.md ./
RUN uv sync --no-dev 2>/dev/null || true

# knowledge/ and fixtures/ are bind-mounted by docker-compose so the corpus can
# be edited without a rebuild. DATA lives on a named volume.
ENV PATH="/app/.venv/bin:$PATH" \
    DATABASE_URL="sqlite+aiosqlite:////data/eoc.db" \
    KNOWLEDGE_DIR="/app/knowledge" \
    FIXTURES_DIR="/app/fixtures"

RUN mkdir -p /data

EXPOSE 8080

# Seed on first boot only: the seeder is a no-op when an incident already
# exists, so a container restart never wipes a reviewer's demo state.
CMD ["sh", "-c", "python -m app.seed || true; exec uvicorn app.main:app --host 0.0.0.0 --port 8080"]
