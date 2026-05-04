from __future__ import annotations

from typing import Any


def derive_impact_tags(impact_map: dict[str, Any]) -> set[str]:
    tags: set[str] = set()
    for file_path in impact_map.keys():
        norm = str(file_path).replace("\\", "/").lower()
        if "core/" in norm:
            tags.add("core")
        if "infra/" in norm or "ops/" in norm:
            tags.add("infra")
        if "ui/" in norm or "frontend/" in norm:
            tags.add("ui")
        if "auth" in norm:
            tags.add("auth")
        if "billing" in norm:
            tags.add("billing")
        if "router" in norm:
            tags.add("router")
    return tags


def should_keep_policy(policy: dict[str, Any], impact_tags: set[str]) -> bool:
    scope = str(policy.get("scope", "")).upper()
    if scope == "GLOBAL":
        return True
    tags = {str(t).strip().lower() for t in (policy.get("tags") or []) if str(t).strip()}
    if not impact_tags:
        return True
    if not tags:
        # Keep untagged policies for backward compatibility.
        return True
    return not tags.isdisjoint({t.lower() for t in impact_tags})

