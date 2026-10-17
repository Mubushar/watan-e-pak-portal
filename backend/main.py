"""
Run the combined Real Estate Portal server.

Starts the FastAPI app (REST docs at /docs) and mounts the MCP server at /mcp
(Streamable HTTP) — both sharing one in-memory data store.

    uv run python main.py
    # REST : http://127.0.0.1:8000/docs
    # MCP  : http://127.0.0.1:8000/mcp
"""

from __future__ import annotations

import os

import uvicorn

from api import MCP_STATELESS, app

# PORTAL_HOST=0.0.0.0 lets phones / other PCs on your network reach the API
# (e.g. the Android or iOS app pointed at http://<this-pc-ip>:8000).
HOST = os.getenv("PORTAL_HOST", "127.0.0.1")
PORT = int(os.getenv("PORTAL_PORT", "8000"))

if __name__ == "__main__":
    shown = "127.0.0.1" if HOST in ("0.0.0.0", "::") else HOST
    print("Real Estate Portal")
    print(f"  REST  -> http://{shown}:{PORT}/docs")
    print(f"  MCP   -> http://{shown}:{PORT}/mcp  (Streamable HTTP, "
          f"{'stateless' if MCP_STATELESS else 'stateful'})")
    print(f"  OpenAI-> http://{shown}:{PORT}/v1   (/models, /chat/completions, /embeddings)")
    if HOST in ("0.0.0.0", "::"):
        print("  Listening on all network interfaces (PORTAL_HOST) — reachable from your LAN.")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
