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
_LOCAL_PREFIXES = ("http://localhost:", "http://127.0.0.1:")

# Only plain HTTP is installed, so file://, ftp:// and custom schemes cannot be
# opened even if a URL were ever built from untrusted input.
_LOCAL_OPENER = urllib.request.OpenerDirector()
for _handler in (urllib.request.HTTPHandler(), urllib.request.HTTPErrorProcessor()):
    _LOCAL_OPENER.add_handler(_handler)


def _open(request: urllib.request.Request, timeout: float):
    return _LOCAL_OPENER.open(request, timeout=timeout)


def post_local_json(url: str, payload: dict, timeout: float) -> dict:
    """POST JSON to a local model server (localhost HTTP only) and return the JSON reply."""
    if not url.startswith(_LOCAL_PREFIXES):
        raise ValueError(f"refusing non-local model URL: {url!r}")
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with _open(request, timeout) as response:
        return json.loads(response.read().decode("utf-8"))


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
        payload = post_local_json(EMBED_URL, {"model": model, "prompt": text[:4000]}, timeout=30)
        vector = [float(x) for x in payload["embedding"]]
        if not vector:
            return None
    except Exception:
        return None
    _cache[key] = vector
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)
    return list(vector)
