"""Tests for dedupe rule."""
from __future__ import annotations

import json

from nexus.evidence.dedupe import (
    DedupeEntry,
    DedupeManifest,
    normalize_instance_id,
    build_dedupe_group,
    write_dedupe_manifest,
    load_dedupe_manifest,
    find_canonical,
)


def test_normalize_instance_id_removes_double_underscore():
    """astropy__astropy-14096 normalizes to astropy-14096."""
    assert normalize_instance_id("astropy__astropy-14096") == "astropy-14096"


def test_normalize_instance_id_preserves_single_dash():
    """astropy-14096 stays as astropy-14096."""
    assert normalize_instance_id("astropy-14096") == "astropy-14096"


def test_build_dedupe_group_with_alias():
    """Multiple aliases produce a group with canonical and aliases."""
    entry = build_dedupe_group([
        "astropy__astropy-14096",
        "astropy-14096",
    ])
    assert entry.canonical_instance_id == "astropy-14096"
    assert "astropy__astropy-14096" in entry.alias_instance_ids
    assert entry.dedupe_group_id != ""
    assert entry.dedupe_reason == "alias_normalization"


def test_build_dedupe_group_single_instance():
    """Single instance gets single_instance reason."""
    entry = build_dedupe_group(["django__django-11099"])
    assert entry.canonical_instance_id == "django__django-11099"
    assert entry.alias_instance_ids == []
    assert entry.dedupe_reason == "single_instance"


def test_write_and_load_dedupe_manifest(tmp_path):
    """Write and load roundtrip for dedupe manifest."""
    entries = [
        build_dedupe_group(["astropy__astropy-14096", "astropy-14096"]),
        build_dedupe_group(["django__django-11099"]),
    ]
    path = tmp_path / "dedupe.json"
    write_dedupe_manifest(entries, path)

    loaded = load_dedupe_manifest(path)
    assert len(loaded.entries) == 2
    assert loaded.entries[0].canonical_instance_id == "astropy-14096"


def test_find_canonical_with_manifest(tmp_path):
    """find_canonical resolves alias to canonical via manifest."""
    entries = [
        build_dedupe_group(["astropy__astropy-14096", "astropy-14096"]),
    ]
    path = tmp_path / "dedupe.json"
    manifest = write_dedupe_manifest(entries, path)
    loaded = load_dedupe_manifest(path)

    assert find_canonical("astropy__astropy-14096", loaded) == "astropy-14096"
    assert find_canonical("astropy-14096", loaded) == "astropy-14096"
    assert find_canonical("unknown-99999", loaded) == "unknown-99999"


def test_dedupe_manifest_schema_version(tmp_path):
    """Manifest has correct schema and version."""
    entries = [build_dedupe_group(["astropy-14096"])]
    path = tmp_path / "dedupe.json"
    write_dedupe_manifest(entries, path)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema"] == "nexus.evidence.dedupe_manifest.v1"
    assert data["version"] == "v1"
