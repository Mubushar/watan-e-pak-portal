"""
OpenAI-compatible facade for the Real Estate Portal
===================================================

Many tools/apps expect an OpenAI-style API (`/v1/models`, `/v1/chat/completions`).
This module makes the portal answer on those routes.

Two modes
---------
1. **OpenAI mode** (real LLM answers): with `OPENAI_API_KEY` set, every request is
   forwarded to OpenAI (model `gpt-6-luna` — the low-cost tier — unless `OPENAI_MODEL`
   says otherwise). Streaming is passed through. Replies are capped at
   `OPENAI_MAX_OUTPUT_TOKENS` (default 800) unless the client asks for a limit.

2. **Local fallback mode** (default, no config): `/v1/chat/completions` answers
   directly from the portal's own data using `rag_search`, so the endpoint still
   returns a useful completion without any external service. `/v1/embeddings`
   returns a deterministic hash embedding.

Environment variables (or backend/.env)
---------------------------------------
    OPENAI_API_KEY        enables OpenAI for chat (and voice — see openai_voice.py)
    OPENAI_MODEL          chat model, default gpt-6-luna
    OPENAI_MAX_OUTPUT_TOKENS  reply cap for chat (default 800; keeps costs predictable)
    OPENAI_BASE_URL       optional, e.g. an Azure OpenAI / proxy URL (default https://api.openai.com/v1)

Testing with a free / local model (chat only — voice is unaffected)::

    LLM_BASE_URL=http://localhost:1234/v1     # any OpenAI-compatible server, e.g. LM Studio
    LLM_MODEL=qwen3-4b-instruct-2507          # the model id that server lists at /models
    LLM_API_KEY=                              # optional (LM Studio needs none)

When ``LLM_BASE_URL`` is set, chat goes there instead of OpenAI. Remove those lines and
restart to go back to OpenAI.

The portal's *tool* interface remains MCP at `/mcp`; this facade is only an
LLM-compatible shim.
"""

import hashlib
import json
import math
import os
import re
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

import ai_guard
import envfile  # noqa: F401  (loads backend/.env)
import server as core

router = APIRouter(prefix="/v1", tags=["openai-compatible"])

# OpenAI by default (chat here, voice in openai_voice.py); LLM_* points chat alone at
# another OpenAI-compatible server (LM Studio, Ollama, …) for testing.
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "").strip().rstrip("/")

if LLM_BASE_URL:
    UPSTREAM_BASE_URL = LLM_BASE_URL
    UPSTREAM_API_KEY = os.getenv("LLM_API_KEY", "").strip()
    UPSTREAM_MODEL = os.getenv("LLM_MODEL", "").strip() or "local-model"
    UPSTREAM_PROVIDER: Optional[str] = "lmstudio" if ":1234" in LLM_BASE_URL else "openai-compatible"
else:
    UPSTREAM_BASE_URL = OPENAI_BASE_URL if OPENAI_API_KEY else ""
    UPSTREAM_API_KEY = OPENAI_API_KEY
    UPSTREAM_MODEL = os.getenv("OPENAI_MODEL", "gpt-6-luna")
    UPSTREAM_PROVIDER = "openai" if OPENAI_API_KEY else None

# Default reply cap for OpenAI chat (a client can still ask for less or more).
MAX_OUTPUT_TOKENS = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "800") or 0)
# Models a caller may pick explicitly (comma-separated); everything else becomes UPSTREAM_MODEL.
ALLOWED_MODELS = {UPSTREAM_MODEL, *[m.strip() for m in os.getenv("AI_ALLOWED_MODELS", "").split(",") if m.strip()]}
EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

# OpenAI-only request fields that other servers may reject.
_OPENAI_ONLY_FIELDS = ("reasoning_effort", "verbosity", "store", "safety_identifier", "prompt_cache_key")


_LOCAL_MODEL = "portal-realestate-rag"
_CREATED = int(time.time())

MODELS: List[Dict[str, Any]] = [
    {"id": _LOCAL_MODEL, "object": "model", "created": _CREATED, "owned_by": "real-estate-portal"},
]
if UPSTREAM_BASE_URL:
    MODELS.append({"id": UPSTREAM_MODEL, "object": "model", "created": _CREATED, "owned_by": "upstream"})


def _proxying() -> bool:
    return bool(UPSTREAM_BASE_URL)


def _upstream_headers(request: Request) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    auth = request.headers.get("authorization")
    if UPSTREAM_API_KEY:
        headers["Authorization"] = f"Bearer {UPSTREAM_API_KEY}"
    elif auth and not LLM_BASE_URL:  # never hand a portal session token to a test LLM server
        headers["Authorization"] = auth
    return headers


MAX_MESSAGES = 60
MAX_REQUEST_CHARS = 200_000


_CLIENT: Optional[httpx.AsyncClient] = None


def upstream_client() -> httpx.AsyncClient:
    """One pooled client for every upstream call: keep-alive saves a TLS handshake per request."""
    global _CLIENT
    if _CLIENT is None or _CLIENT.is_closed:
        _CLIENT = httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15),
                                    limits=httpx.Limits(max_connections=50, max_keepalive_connections=20))
    return _CLIENT


async def _forward(url: str, request: Request, body: Dict[str, Any]) -> JSONResponse:
    """POST to the upstream and return its JSON as-is. Network failures and non-JSON
    error pages (gateways, proxies) become OpenAI-style 502 errors."""
    try:
        upstream = await upstream_client().post(url, json=body, headers=_upstream_headers(request))
    except httpx.HTTPError as exc:
        return _error(f"Could not reach the AI service ({type(exc).__name__})", status=502, err_type="upstream_error")
    try:
        return JSONResponse(status_code=upstream.status_code, content=upstream.json())
    except ValueError:
        return _error(f"AI service error {upstream.status_code}", status=502, err_type="upstream_error")


def _error(message: str, status: int = 400, err_type: str = "invalid_request_error") -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"message": message, "type": err_type, "param": None, "code": None}},
    )


# ------------------------------------------------------------------
# /v1/models
# ------------------------------------------------------------------


@router.get("/models")
async def list_models() -> Dict[str, Any]:
    return {"object": "list", "data": MODELS}


@router.get("/models/{model_id}")
async def get_model(model_id: str) -> Any:
    match = next((m for m in MODELS if m["id"] == model_id), None)
    if not match:
        return _error(f"The model '{model_id}' does not exist", status=404)
    return match


# ------------------------------------------------------------------
# helpers for the local fallback
# ------------------------------------------------------------------


def _last_user_message(messages: List[Dict[str, Any]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, list):  # OpenAI multi-part content
                content = " ".join(part.get("text", "") for part in content if isinstance(part, dict))
            return str(content)
    return ""


def _tokens(text: str) -> int:
    return max(1, len(text.split()))


def _local_answer(user_text: str) -> str:
    """Answer from the portal's own catalogue using RAG."""
    if not user_text.strip():
        return "Ask me about properties, cities, schemes or big projects (e.g. '5 bedroom house in Lahore')."

    result = json.loads(core.rag_search(user_text, top_k=3))
    lines: List[str] = []
    if result.get("count"):
        lines.append("Here are the closest matches in the portal:")
        for hit in result["results"]:
            if hit.get("type") == "property":
                price = hit.get("price") or 0
                lines.append(
                    f"- {hit.get('title')} — {price:,.0f} PKR ({hit.get('city')}, "
                    f"{hit.get('category')}, use: {hit.get('use_type')})"
                )
            else:
                kind = str(hit.get("type") or "").replace("_", " ")
                where = ", ".join(x for x in (kind, hit.get("city")) if x)
                lines.append(f"- {hit.get('name') or hit.get('title')}" + (f" ({where})" if where else ""))
        lines.append(
            "\nYou can refine by city, price range, bedrooms or category, "
            "e.g. 'apartments in Karachi under 50,000,000'."
        )
    else:
        lines.append(
            "I couldn't find a matching listing in the portal catalogue. "
            "Try a city (Lahore, Karachi, Islamabad, Rawalpindi), a type "
            "(house, plot, apartment, shop, office) or a budget."
        )
    lines.append(
        "\n(Node: this reply came from the portal's built-in RAG fallback. "
        "Set PORTAL_LLM_BASE_URL + PORTAL_LLM_API_KEY to proxy a real LLM.)"
    )
    if result.get("context"):
        lines.append("\nMatched records:\n" + result["context"])
    return "\n".join(lines)


def _chat_completion_object(model: str, content: str, prompt_tokens: int) -> Dict[str, Any]:
    completion_tokens = _tokens(content)
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


async def _stream_local(model: str, content: str) -> AsyncIterator[bytes]:
    cid = f"chatcmpl-{uuid.uuid4().hex}"
    created = int(time.time())

    def frame(delta: Dict[str, Any], finish: Optional[str] = None) -> bytes:
        payload = {
            "id": cid,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        return f"data: {json.dumps(payload)}\n\n".encode("utf-8")

    yield frame({"role": "assistant"})
    for word in content.split(" "):
        yield frame({"content": word + " "})
    yield frame({}, finish="stop")
    yield b"data: [DONE]\n\n"


# ------------------------------------------------------------------
# /v1/chat/completions
# ------------------------------------------------------------------


@router.post("/chat/completions")
async def chat_completions(request: Request) -> Any:
    try:
        body = await request.json()
    except Exception:
        return _error("Request body must be valid JSON")

    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        return _error("'messages' is required and must be a non-empty array")
    model = body.get("model") or (UPSTREAM_MODEL if _proxying() else _LOCAL_MODEL)
    stream = bool(body.get("stream"))

    # ----- proxy mode -----
    if _proxying():
        # The upstream spends the server's OpenAI credit: rate-limit and cap request size.
        ai_guard.check(request, "chat")
        if len(messages) > MAX_MESSAGES or len(json.dumps(messages)) > MAX_REQUEST_CHARS:
            return _error("Conversation too long — start a new conversation.", status=413)
        # The server pays, so the server decides: always the configured model (plus any extra
        # models allowed in AI_ALLOWED_MODELS), one completion, and output capped.
        if body.get("model") not in ALLOWED_MODELS:
            body["model"] = UPSTREAM_MODEL
        body.pop("n", None)
        if LLM_BASE_URL:
            for field in _OPENAI_ONLY_FIELDS:
                body.pop(field, None)
        elif MAX_OUTPUT_TOKENS > 0:
            asked = body.pop("max_tokens", None) or body.get("max_completion_tokens")
            cap = MAX_OUTPUT_TOKENS * 2
            body["max_completion_tokens"] = min(int(asked), cap) if isinstance(asked, (int, float)) and asked > 0 else MAX_OUTPUT_TOKENS
        url = f"{UPSTREAM_BASE_URL}/chat/completions"
        if stream:
            return StreamingResponse(
                _stream_upstream(url, _upstream_headers(request), body), media_type="text/event-stream"
            )
        return await _forward(url, request, body)

    # ----- local fallback mode -----
    user_text = _last_user_message(messages)
    content = _local_answer(user_text)
    prompt_tokens = sum(_tokens(str(m.get("content", ""))) for m in messages)

    if stream:
        return StreamingResponse(_stream_local(model, content), media_type="text/event-stream")
    return _chat_completion_object(model, content, prompt_tokens)


async def _stream_upstream(url: str, headers: Dict[str, str], body: Dict[str, Any]) -> AsyncIterator[bytes]:
    try:
        async with upstream_client().stream("POST", url, json=body, headers=headers) as resp:
            if resp.status_code >= 400:
                detail = (await resp.aread())[:500].decode("utf-8", "replace")
                yield _sse({"error": {"message": f"AI service error {resp.status_code}", "detail": detail}})
                return
            async for chunk in resp.aiter_raw():
                yield chunk
    except httpx.HTTPError as exc:
        yield _sse({"error": {"message": f"Could not reach the AI service ({type(exc).__name__})"}})


def _sse(payload: Dict[str, Any]) -> bytes:
    return ("data: " + json.dumps(payload) + "\n\n").encode()


# ------------------------------------------------------------------
# /v1/completions (legacy)
# ------------------------------------------------------------------


@router.post("/completions")
async def completions(request: Request) -> Any:
    try:
        body = await request.json()
    except Exception:
        return _error("Request body must be valid JSON")

    prompt = body.get("prompt", "")
    if isinstance(prompt, list):
        prompt = " ".join(str(p) for p in prompt)
    model = body.get("model") or (UPSTREAM_MODEL if _proxying() else _LOCAL_MODEL)

    if _proxying():
        ai_guard.check(request, "chat")
        if len(json.dumps(body)) > MAX_REQUEST_CHARS:
            return _error("Prompt too long", status=413)
        # Current models only speak chat: answer the legacy call through /chat/completions on
        # the server's model and hand it back in the text_completion shape.
        chat: Dict[str, Any] = {"model": UPSTREAM_MODEL, "messages": [{"role": "user", "content": str(prompt)}]}
        if MAX_OUTPUT_TOKENS > 0 and not LLM_BASE_URL:
            asked = body.get("max_tokens")
            chat["max_completion_tokens"] = min(int(asked), MAX_OUTPUT_TOKENS * 2) if isinstance(asked, (int, float)) and asked > 0 else MAX_OUTPUT_TOKENS
        upstream = await _forward(f"{UPSTREAM_BASE_URL}/chat/completions", request, chat)
        if upstream.status_code != 200:
            return upstream
        data = json.loads(upstream.body)
        choice = (data.get("choices") or [{}])[0]
        return {
            "id": data.get("id") or f"cmpl-{uuid.uuid4().hex}",
            "object": "text_completion",
            "created": data.get("created") or int(time.time()),
            "model": data.get("model") or UPSTREAM_MODEL,
            "choices": [{"index": 0, "text": (choice.get("message") or {}).get("content") or "",
                         "logprobs": None, "finish_reason": choice.get("finish_reason") or "stop"}],
            "usage": data.get("usage") or {},
        }

    content = _local_answer(str(prompt))
    return {
        "id": f"cmpl-{uuid.uuid4().hex}",
        "object": "text_completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "text": content, "logprobs": None, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": _tokens(str(prompt)),
            "completion_tokens": _tokens(content),
            "total_tokens": _tokens(str(prompt)) + _tokens(content),
        },
    }


# ------------------------------------------------------------------
# /v1/embeddings
# ------------------------------------------------------------------

_EMBED_DIM = 256


def _hash_embedding(text: str, dim: int = _EMBED_DIM) -> List[float]:
    vec = [0.0] * dim
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [round(v / norm, 6) for v in vec]


@router.post("/embeddings")
async def embeddings(request: Request) -> Any:
    try:
        body = await request.json()
    except Exception:
        return _error("Request body must be valid JSON")

    model = body.get("model") or (UPSTREAM_MODEL if _proxying() else _LOCAL_MODEL)

    if _proxying():
        ai_guard.check(request, "chat")
        raw = body.get("input")
        if raw is None or len(json.dumps(raw)) > MAX_REQUEST_CHARS or (isinstance(raw, list) and len(raw) > 256):
            return _error("'input' is required (at most 256 items / 200k characters)", status=413)
        body["model"] = EMBEDDING_MODEL
        return await _forward(f"{UPSTREAM_BASE_URL}/embeddings", request, body)

    raw_input = body.get("input")
    if raw_input is None:
        return _error("'input' is required")
    items = raw_input if isinstance(raw_input, list) else [raw_input]
    items = [item if isinstance(item, str) else json.dumps(item) for item in items]

    data = [
        {"object": "embedding", "index": i, "embedding": _hash_embedding(text)}
        for i, text in enumerate(items)
    ]
    total = sum(_tokens(text) for text in items)
    return {
        "object": "list",
        "data": data,
        "model": model,
        "usage": {"prompt_tokens": total, "total_tokens": total},
    }
