from __future__ import annotations

import socket


MODEL_EMPTY_RESPONSE = "MODEL_EMPTY_RESPONSE"
MODEL_PROVIDER_ERROR = "MODEL_PROVIDER_ERROR"
MODEL_REFUSAL = "MODEL_REFUSAL"
MODEL_TIMEOUT = "MODEL_TIMEOUT"

_TIMEOUT_MARKERS = (
    "timed out",
    "timeout",
    "read timed out",
)

_REFUSAL_MARKERS = (
    "i apologize",
    "i'm sorry",
    "i am sorry",
    "i cannot",
    "i can't",
    "cannot provide",
    "can't provide",
)


def classify_model_exception(exc: BaseException) -> str:
    reason = getattr(exc, "reason", None)
    if isinstance(exc, (TimeoutError, socket.timeout)) or isinstance(reason, (TimeoutError, socket.timeout)):
        return MODEL_TIMEOUT

    text = f"{type(exc).__name__}: {exc}".lower()
    if any(marker in text for marker in _TIMEOUT_MARKERS):
        return MODEL_TIMEOUT
    return MODEL_PROVIDER_ERROR


def classify_model_text(response: str) -> str:
    text = (response or "").strip()
    if not text:
        return MODEL_EMPTY_RESPONSE

    prefix = text[:500].lower()
    has_patch_shape = "file:" in prefix and "search:" in prefix and "replace:" in prefix
    if not has_patch_shape and any(marker in prefix for marker in _REFUSAL_MARKERS):
        return MODEL_REFUSAL
    return ""
