"""Local embedding helper for lesson retrieval (Ollama nomic-embed-text). Fail-open."""

from __future__ import annotations

import json
import os
import urllib.request
from collections import OrderedDict

EMBED_URL = "http://localhost:11434/api/embeddings"
EMBED_MODEL_ENV = "NEXUS_LEARNING_EMBED_MODEL"
DEFAULT_EMBED_MODEL = "nomic-embed-text"
_CACHE_MAX = 128
_cache: OrderedDict[tuple[str, str], list[float]] = OrderedDict()


def embed_model_name() -> str:
    return os.environ.get(EMBED_MODEL_ENV, DEFAULT_EMBED_MODEL).strip() or DEFAULT_EMBED_MODEL


def embed_text(text: str) -> list[float] | None:
    """Return an embedding vector, or None on any error / when disabled."""
    model = embed_model_name()
    if model.lower() == "none":
        return None
    key = (model, text)
    cached = _cache.get(key)
    if cached is not None:
        _cache.move_to_end(key)
        return list(cached)
    try:
        body = json.dumps({"model": model, "prompt": text[:4000]}).encode("utf-8")
        request = urllib.request.Request(
            EMBED_URL,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        vector = [float(x) for x in payload["embedding"]]
        if not vector:
            return None
    except Exception:
        return None
    _cache[key] = vector
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)
    return list(vector)
