FROM python:3.15-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app/backend

RUN apt-get update \
    && apt-get install -y --no-install-recommends gdal-bin \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/
COPY backend/ ./
RUN uv sync --frozen --no-dev --extra postgres

EXPOSE 8000

CMD ["uv", "run", "--frozen", "--no-sync", "python", "main.py"]

