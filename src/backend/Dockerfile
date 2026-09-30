# Cogito backend + MCP server builder — small, fast, single stage.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# Build context is ./src (so both the API package and the MCP server are bundled)
COPY backend/pyproject.toml ./
COPY backend/app ./app
COPY mcp_cogito ./mcp_cogito

RUN pip install --upgrade pip && pip install .

EXPOSE 8000

# MCP server reachable as:  python -m mcp_cogito.server   (module path added)
ENV PYTHONPATH=/app:/app/mcp_cogito

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]