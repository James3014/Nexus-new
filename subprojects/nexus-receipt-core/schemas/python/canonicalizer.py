"""Receipt canonicalization in Python — mirrors Rust implementation."""

import json
from collections import OrderedDict


def canonicalize(obj):
    """Recursively canonicalize a JSON value.
    
    - Sort all dict keys lexicographically
    - Trim string values
    - Preserve array order
    """
    if isinstance(obj, dict):
        sorted_items = sorted(obj.items(), key=lambda x: x[0])
        return OrderedDict(
            (k, canonicalize(v)) for k, v in sorted_items
        )
    elif isinstance(obj, list):
        return [canonicalize(item) for item in obj]
    elif isinstance(obj, str):
        return obj.strip()
    else:
        return obj


def compute_canonical_json(obj):
    """Return the canonical JSON string of an object.
    
    Excludes 'claimed_hash' from canonicalization to mirror Rust verifier behavior
    (avoid circular dependency: claimed_hash is the hash of the canonical form
    without claimed_hash itself).
    """
    if isinstance(obj, dict):
        obj = {k: v for k, v in obj.items() if k != "claimed_hash"}
    canonical = canonicalize(obj)
    return json.dumps(canonical, separators=(",", ":"), ensure_ascii=True)
