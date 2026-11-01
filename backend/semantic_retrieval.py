"""Semantic index for portal knowledge, backed by PostgreSQL pgvector.

The index contains text from the public portal knowledge corpus (listings, schemes,
cities, projects and guidance). Embeddings are created only when an administrator
requests a rebuild; query embeddings are created when hybrid search is used.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List

import httpx

import openai_facade
import storage


class SemanticUnavailable(RuntimeError):
    pass


def status() -> Dict[str, Any]:
    db = storage.instance()
    store = db.semantic_storage_status() if db else {"backend": "memory", "vector_store": False, "table": None}
    return {**store, "embedding_provider": openai_facade.UPSTREAM_PROVIDER,
            "embedding_model": openai_facade.EMBEDDING_MODEL,
            "ready": bool(db and store.get("vector_store") and openai_facade.UPSTREAM_BASE_URL)}


def _embed(texts: List[str]) -> List[List[float]]:
    if not openai_facade.UPSTREAM_BASE_URL:
        raise SemanticUnavailable("Configure an embedding-capable provider using OPENAI_API_KEY or LLM_BASE_URL.")
    if not texts or len(texts) > 128 or sum(len(s) for s in texts) > 180_000:
        raise SemanticUnavailable("Embedding batch is empty or exceeds the configured safety limit.")
    headers = {"Content-Type": "application/json"}
    if openai_facade.UPSTREAM_API_KEY:
        headers["Authorization"] = f"Bearer {openai_facade.UPSTREAM_API_KEY}"
    try:
        response = httpx.post(f"{openai_facade.UPSTREAM_BASE_URL}/embeddings", headers=headers,
                              json={"model": openai_facade.EMBEDDING_MODEL, "input": texts}, timeout=90)
        response.raise_for_status()
        data = response.json().get("data", [])
        if not isinstance(data, list):
            raise SemanticUnavailable("Embedding provider returned an invalid response.")
        vectors = [row["embedding"] for row in sorted(data, key=lambda row: row.get("index", 0))]
        if len(vectors) != len(texts) or any(len(vector) != 1536 for vector in vectors):
            raise SemanticUnavailable("The provider must return 1536-dimensional embeddings (text-embedding-3-small).")
        return vectors
    except SemanticUnavailable:
        raise
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise SemanticUnavailable(f"Embedding provider request failed: {type(exc).__name__}") from exc


def _chunks(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    text = str(doc.get("text") or "").strip()
    chunks: List[Dict[str, Any]] = []
    offset = 0
    while offset < len(text):
        end = min(offset + 900, len(text))
        if end < len(text):
            boundary = text.rfind(" ", offset + 500, end)
            if boundary > offset:
                end = boundary
        body = text[offset:end].strip()
        if body:
            source_type, source_id = str(doc.get("type") or "knowledge"), str(doc.get("id") or "")
            chunk_id = hashlib.sha256(f"{source_type}:{source_id}:{offset}".encode()).hexdigest()
            chunks.append({"chunk_id": chunk_id, "source_id": source_id, "source_type": source_type,
                           "title": str(doc.get("title") or "Portal knowledge"), "content": body,
                           "metadata": {"url": doc.get("url"), "tier": doc.get("tier"), "offset": offset}})
        if end >= len(text):
            break
        offset = max(offset + 1, end - 120)
    return chunks


def rebuild() -> Dict[str, Any]:
    db = storage.instance()
    if not db or not db.semantic_storage_status().get("vector_store"):
        raise SemanticUnavailable("PostgreSQL pgvector is unavailable; enable the vector extension and restart.")
    from knowledge import index
    documents = index().docs
    chunks = [chunk for doc in documents for chunk in _chunks(doc)]
    if not chunks:
        raise SemanticUnavailable("The portal knowledge corpus is empty.")
    # Build every vector before replacing the live index, so provider failures leave the
    # previous usable index intact. Database replacement itself is one transaction.
    for offset in range(0, len(chunks), 64):
        batch = chunks[offset:offset + 64]
        vectors = _embed([item["content"] for item in batch])
        for item, vector in zip(batch, vectors):
            item["embedding"] = vector
    inserted = db.semantic_replace(chunks)
    return {"indexed_documents": len(documents), "indexed_chunks": inserted, "status": status()}


def search(query: str, limit: int = 12) -> List[Dict[str, Any]]:
    db = storage.instance()
    if not db or not db.semantic_storage_status().get("vector_store"):
        return []
    if not db.semantic_storage_status().get("indexed_chunks"):
        return []
    vectors = _embed([query])
    return db.semantic_search(vectors[0], limit)
