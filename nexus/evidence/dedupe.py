"""
Dedupe Rule: canonical instance id / alias dedupe handling.

Handles astropy-14096 vs astropy__astropy-14096 style aliases.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class DedupeEntry:
    """A single dedupe entry mapping a canonical ID to its aliases."""
    canonical_instance_id: str
    alias_instance_ids: List[str] = field(default_factory=list)
    dedupe_group_id: str = ""
    dedupe_reason: str = ""

    def __post_init__(self):
        if not self.dedupe_group_id:
            self.dedupe_group_id = hashlib.sha256(
                self.canonical_instance_id.encode()
            ).hexdigest()[:16]


@dataclass
class DedupeManifest:
    """Manifest of all dedupe rules."""
    schema: str = "nexus.evidence.dedupe_manifest.v1"
    version: str = "v1"
    entries: List[DedupeEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "version": self.version,
            "entries": [
                {
                    "canonical_instance_id": e.canonical_instance_id,
                    "alias_instance_ids": e.alias_instance_ids,
                    "dedupe_group_id": e.dedupe_group_id,
                    "dedupe_reason": e.dedupe_reason,
                }
                for e in self.entries
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


def normalize_instance_id(instance_id: str) -> str:
    """
    Normalize instance_id to canonical form.
    astropy__astropy-14096 -> astropy-14096
    astropy-14096 -> astropy-14096
    django__django-11099 -> django-11099
    """
    if "__" in instance_id:
        parts = instance_id.split("__", 1)
        suffix = parts[1]
        if suffix.startswith(parts[0] + "-"):
            return suffix
        return f"{parts[0]}-{suffix}"
    return instance_id


def build_dedupe_group(instance_ids: List[str]) -> DedupeEntry:
    """Build a dedupe entry from a list of alias instance IDs."""
    canonical = min(instance_ids)
    aliases = [i for i in instance_ids if i != canonical]
    reason = "alias_normalization" if aliases else "single_instance"
    return DedupeEntry(
        canonical_instance_id=canonical,
        alias_instance_ids=sorted(aliases),
        dedupe_reason=reason,
    )


def write_dedupe_manifest(
    entries: List[DedupeEntry],
    output_path: Path,
) -> Path:
    """Write dedupe manifest to disk."""
    manifest = DedupeManifest(entries=entries)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(manifest.to_json(), encoding="utf-8")
    return output_path


def load_dedupe_manifest(path: Path) -> DedupeManifest:
    """Load dedupe manifest from disk."""
    if not path.exists():
        return DedupeManifest()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = [
            DedupeEntry(**e) for e in data.get("entries", [])
        ]
        return DedupeManifest(
            schema=data.get("schema", "nexus.evidence.dedupe_manifest.v1"),
            version=data.get("version", "v1"),
            entries=entries,
        )
    except Exception:
        return DedupeManifest()


def find_canonical(
    instance_id: str,
    manifest: DedupeManifest,
) -> str:
    """Find canonical ID for a given instance_id using the manifest."""
    normalized = normalize_instance_id(instance_id)
    for entry in manifest.entries:
        if normalized == entry.canonical_instance_id:
            return entry.canonical_instance_id
        if normalized in entry.alias_instance_ids:
            return entry.canonical_instance_id
    return normalized
