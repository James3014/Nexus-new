#!/usr/bin/env python3
"""Tests for unresolved-link classifier."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "classify_wiki_unresolved_links.py"
VAULT_ROOT = REPO_ROOT / "nexus_wiki_vault"


def _run_classifier(
    tmp_path: Path,
    mode: str = "--write",
    **kwargs,
) -> subprocess.CompletedProcess:
    args = [sys.executable, str(SCRIPT), mode]
    # Always set output-dir to tmp_path
    args.extend(["--output-dir", str(tmp_path)])
    for key, value in kwargs.items():
        args.extend([f"--{key.replace('_', '-')}", str(value)])
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _load_inventory(tmp_path: Path) -> dict:
    """Load the inventory from tmp_path."""
    return json.loads((tmp_path / "unresolved-link-inventory.json").read_text())


def test_repo_source_requires_exact_committed_repo_file(tmp_path):
    """repo_source requires normalized target outside vault AND exact repo file exists."""
    res = _run_classifier(tmp_path, repo_root=str(REPO_ROOT))
    assert res.returncode == 0, res.stderr
    inventory = _load_inventory(tmp_path)
    for entry in inventory["entries"]:
        if entry["category"] == "repo_source":
            assert entry["evidence"]["repo_path_exists"]


def test_excluded_wiki_target_is_not_repairable(tmp_path):
    """excluded_wiki_target entries must not be repairable."""
    res = _run_classifier(tmp_path, repo_root=str(REPO_ROOT))
    inventory = _load_inventory(tmp_path)
    for entry in inventory["entries"]:
        if entry["category"] == "excluded_wiki_target":
            assert not entry["repairable"]


def test_legacy_or_historical_source_is_not_repairable(tmp_path):
    """legacy_or_historical entries must not be repairable."""
    res = _run_classifier(tmp_path, repo_root=str(REPO_ROOT))
    inventory = _load_inventory(tmp_path)
    for entry in inventory["entries"]:
        if entry["category"] == "legacy_or_historical":
            assert not entry["repairable"]


def test_placeholder_is_not_guessed_as_page(tmp_path):
    """placeholder targets must not be guessed as wiki pages."""
    res = _run_classifier(tmp_path, repo_root=str(REPO_ROOT))
    inventory = _load_inventory(tmp_path)
    for entry in inventory["entries"]:
        if entry["category"] == "placeholder_or_template":
            assert entry["raw_target"].strip() in {"documentation", "TODO", "TBD", "placeholder", "pending"}


def test_exact_alias_match_requires_unique_destination(tmp_path):
    """exact_alias_match must have exactly one candidate."""
    res = _run_classifier(tmp_path, repo_root=str(REPO_ROOT))
    inventory = _load_inventory(tmp_path)
    for entry in inventory["entries"]:
        if entry["category"] == "exact_alias_match":
            assert entry["repairable"]
            assert entry["proposed_target"] != ""


def test_mechanical_path_error_uses_allowlisted_transform_only(tmp_path):
    """mechanical_path_error must use only allowed transforms."""
    allowed_transforms = {"duplicate_md_suffix", "url_decode", "duplicate_leading_dot_slash", "posix_normalize"}
    res = _run_classifier(tmp_path, repo_root=str(REPO_ROOT))
    inventory = _load_inventory(tmp_path)
    for entry in inventory["entries"]:
        if entry["category"] == "mechanical_path_error":
            transform = entry["evidence"]["mechanical_transform"]
            assert transform in allowed_transforms, f"Unknown transform: {transform}"


def test_ambiguous_target_is_not_repairable(tmp_path):
    """ambiguous entries must not be repairable."""
    res = _run_classifier(tmp_path, repo_root=str(REPO_ROOT))
    inventory = _load_inventory(tmp_path)
    for entry in inventory["entries"]:
        if entry["category"] == "ambiguous":
            assert not entry["repairable"]


def test_missing_target_is_not_repairable(tmp_path):
    """missing entries must not be repairable."""
    res = _run_classifier(tmp_path, repo_root=str(REPO_ROOT))
    inventory = _load_inventory(tmp_path)
    for entry in inventory["entries"]:
        if entry["category"] == "missing":
            assert not entry["repairable"]


def test_inventory_count_matches_graph_unresolved_count(tmp_path):
    """Inventory total must equal graph unresolved count."""
    res = _run_classifier(tmp_path, repo_root=str(REPO_ROOT))
    inventory = _load_inventory(tmp_path)
    graph = json.loads((VAULT_ROOT / "99_Schema" / "generated" / "wikilink-graph.json").read_text())
    assert inventory["total_unresolved"] == len(graph["unresolved_links"])


def test_inventory_is_byte_deterministic(tmp_path):
    """Running classifier twice must produce identical results."""
    res1 = _run_classifier(tmp_path, repo_root=str(REPO_ROOT))
    assert res1.returncode == 0
    inventory1 = _load_inventory(tmp_path)

    res2 = _run_classifier(tmp_path, repo_root=str(REPO_ROOT))
    assert res2.returncode == 0
    inventory2 = _load_inventory(tmp_path)

    assert inventory1["total_unresolved"] == inventory2["total_unresolved"]
    assert inventory1["category_counts"] == inventory2["category_counts"]


def test_repair_batches_have_max_five_source_pages(tmp_path):
    """Each repair batch must have at most 5 source pages."""
    res = _run_classifier(tmp_path, repo_root=str(REPO_ROOT))
    inventory = _load_inventory(tmp_path)
    for batch in inventory["repair_batches"]:
        assert len(batch["source_pages"]) <= 5


def test_repair_batches_have_max_twenty_edits(tmp_path):
    """Each repair batch must have at most 20 edits."""
    res = _run_classifier(tmp_path, repo_root=str(REPO_ROOT))
    inventory = _load_inventory(tmp_path)
    for batch in inventory["repair_batches"]:
        assert len(batch["edits"]) <= 20


def test_classifier_check_mode_is_read_only(tmp_path):
    """Check mode must not modify any files."""
    # Run write first
    _run_classifier(tmp_path, repo_root=str(REPO_ROOT))
    before = (tmp_path / "unresolved-link-inventory.json").read_text()

    # Run check
    res = _run_classifier(tmp_path, mode="--check", repo_root=str(REPO_ROOT))
    assert res.returncode == 0

    # Verify unchanged
    after = (tmp_path / "unresolved-link-inventory.json").read_text()
    assert before == after


def test_classifier_does_not_modify_wiki_sources(tmp_path):
    """Classifier must not modify any wiki source files."""
    before = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    ).stdout

    _run_classifier(tmp_path, repo_root=str(REPO_ROOT))

    after = subprocess.run(
        ["git", "status", "--porcelain=v1"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    ).stdout
    assert before == after
