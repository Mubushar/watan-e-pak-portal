"""
Run the combined Real Estate Portal server.

Starts the FastAPI app (REST docs at /docs) and mounts the MCP server at /mcp
(Streamable HTTP) — both sharing one in-memory data store.

    uv run python main.py
    # REST : http://127.0.0.1:8000/docs
    # MCP  : http://127.0.0.1:8000/mcp
"""

from __future__ import annotations

import uvicorn

from api import MCP_STATELESS, app

if __name__ == "__main__":
    print("Real Estate Portal")
    print("  REST  -> http://127.0.0.1:8000/docs")
    print("  MCP   -> http://127.0.0.1:8000/mcp  (Streamable HTTP, "
          f"{'stateless' if MCP_STATELESS else 'stateful'})")
    print("  OpenAI-> http://127.0.0.1:8000/v1   (/models, /chat/completions, /embeddings)")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")
