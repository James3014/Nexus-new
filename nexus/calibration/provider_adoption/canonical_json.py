"""Canonical JSON serialization and hashing helpers for provider adoption experiments.

Ensures deterministic hashing across all platforms and execution environments,
relying on the canonical hashing style established in nexus.evidence.receipt_base.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json_dumps(value: Any) -> str:
    """Serialize value to deterministic JSON string.

    Rules:
    - Sort keys lexicographically
    - Compact separators (no whitespace after ':' or ',')
    - Disallow NaN / Infinity
    - Disallow non-JSON safe types
    """
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise TypeError(f"canonical_json_dumps_failed: {type(value)!r}: {exc}") from exc


def canonical_json_hash(value: Any) -> str:
    """Compute deterministic SHA-256 hash of a JSON-serializable structure."""
    encoded = canonical_json_dumps(value).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def compute_sha256(text: str) -> str:
    """Compute SHA-256 hash of a UTF-8 string."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
