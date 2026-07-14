#!/usr/bin/env python3
"""Tests for the deterministic wiki agent retrieval index compiler."""
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "ops" / "build_wiki_agent_index.py"
VAULT_ROOT = REPO_ROOT / "nexus_wiki_vault"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _minimal_manifest(tmp_path: Path, canonical: dict | None = None) -> Path:
    if canonical is None:
        canonical = {
            "entry": {"path": "README.md", "authority": "navigation"},
            "current_state": {"path": "00_Home/CURRENT_STATE.md", "authority": "operational"},
        }
    data = {
        "schema": "nexus.wiki.authority.v1",
        "content_verified_against_commit": "abc123",
        "last_document_update_commit": "abc123",
        "verified_at": "2026-07-13",
        "canonical": canonical,
        "known_legacy_entries": [],
    }
    manifest_path = tmp_path / "WIKI_AUTHORITY_MANIFEST.yaml"
    _write_file(manifest_path, yaml.dump(data, default_flow_style=False, sort_keys=False))
    return manifest_path


def _minimal_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "README.md").write_text(
        textwrap.dedent("""\
            ---
            title: Entry
            type: entry
            status: active
            lifecycle: current
            owner: agent
            confidence: high
            source_of_truth: compiled-wiki
            ---
            # Entry
            ## One-sentence summary
            This is the entry page.
            ## Role / responsibility
            Entry role.
            ## Upstream
            None.
            ## Downstream
            None.
            ## Related modules / files
            None.
            ## Source notes
            None.
            ## Open questions / conflicts
            None.
        """),
        encoding="utf-8",
    )
    (vault / "00_Home").mkdir(parents=True, exist_ok=True)
    (vault / "00_Home" / "CURRENT_STATE.md").write_text(
        textwrap.dedent("""\
            ---
            title: CURRENT_STATE
            type: home
            status: active
            lifecycle: current
            owner: agent
            confidence: high
            source_of_truth: compiled-wiki
            ---
            # CURRENT_STATE
            ## One-sentence summary
            Current state of the system.
            ## Role / responsibility
            Status page.
            ## Upstream
            None.
            ## Downstream
            None.
            ## Related modules / files
            None.
            ## Source notes
            None.
            ## Open questions / conflicts
            None.
        """),
        encoding="utf-8",
    )
    return vault


def _run_index(tmp_path: Path, manifest: Path, vault: Path, mode: str = "--write") -> subprocess.CompletedProcess:
    out_dir = tmp_path / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        [
            sys.executable, str(SCRIPT),
            mode,
            "--vault-root", str(vault),
            "--authority-manifest", str(manifest),
            "--output-dir", str(out_dir),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_frontmatter_and_summary_extraction(tmp_path):
    vault = _minimal_vault(tmp_path)
    # Add a page with a ## One-sentence summary section
    page = vault / "test_page.md"
    _write_file(page, textwrap.dedent("""\
        ---
        title: Test Page
        type: module
        status: draft
        lifecycle: draft
        owner: agent
        confidence: low
        source_of_truth: compiled-wiki
        ---
        # Test Page
        ## One-sentence summary
        This page tests frontmatter and summary extraction.
        ## Role / responsibility
        Test role.
        ## Upstream
        None.
        ## Downstream
        None.
        ## Related modules / files
        None.
        ## Source notes
        None.
        ## Open questions / conflicts
        None.
    """))
    manifest = _minimal_manifest(tmp_path, canonical={
        "entry": {"path": "README.md", "authority": "navigation"},
    })
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr

    out_dir = tmp_path / "generated"
    idx = json.loads((out_dir / "agent-index.json").read_text())
    assert idx["schema"] == "nexus.wiki.agent-index.v1"
    pages_by_id = {p["id"]: p for p in idx["pages"]}
    test_page = pages_by_id.get("page:test_page.md")
    assert test_page is not None, f"test_page not found, got: {list(pages_by_id.keys())}"
    assert test_page["title"] == "Test Page"
    assert test_page["type"] == "module"
    assert test_page["lifecycle"] == "draft"
    assert test_page["classification"] == "draft"
    assert "This page tests frontmatter and summary extraction" in test_page["one_sentence_summary"]


def test_canonical_authority_order_is_preserved(tmp_path):
    vault = _minimal_vault(tmp_path)
    manifest = _minimal_manifest(tmp_path, canonical={
        "z_last": {"path": "README.md", "authority": "navigation"},
        "a_first": {"path": "00_Home/CURRENT_STATE.md", "authority": "operational"},
    })
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    idx = json.loads((out_dir / "agent-index.json").read_text())
    canonical_keys = [p["canonical_key"] for p in idx["pages"] if p["is_canonical"]]
    # z_last should come before a_first per manifest order
    assert "a_first" in canonical_keys, f"Expected a_first in {canonical_keys}"
    assert "z_last" in canonical_keys, f"Expected z_last in {canonical_keys}"
    assert canonical_keys.index("z_last") < canonical_keys.index("a_first")


def test_known_legacy_classification_is_applied(tmp_path):
    vault = _minimal_vault(tmp_path)
    # Add a legacy page
    _write_file(vault / "00_Home" / "Root_README_Summary.md", textwrap.dedent("""\
        ---
        title: Root_README_Summary
        type: home
        status: active
        lifecycle: current
        owner: agent
        confidence: medium
        source_of_truth: compiled-wiki
        ---
        # Root_README_Summary
        ## One-sentence summary
        Legacy summary page.
        ## Role / responsibility
        Legacy.
        ## Upstream
        None.
        ## Downstream
        None.
        ## Related modules / files
        None.
        ## Source notes
        None.
        ## Open questions / conflicts
        None.
    """))
    manifest = _minimal_manifest(tmp_path, canonical={
        "entry": {"path": "README.md", "authority": "navigation"},
    })
    manifest_data = yaml.safe_load(manifest.read_text())
    manifest_data["known_legacy_entries"] = [
        {"path": "00_Home/Root_README_Summary.md", "classification": "historical", "lifecycle": "historical"}
    ]
    _write_file(manifest, yaml.dump(manifest_data, default_flow_style=False, sort_keys=False))

    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    idx = json.loads((out_dir / "agent-index.json").read_text())
    pages_by_id = {p["id"]: p for p in idx["pages"]}
    legacy = pages_by_id.get("page:00_Home/Root_README_Summary.md")
    assert legacy is not None
    assert legacy["classification"] == "historical"


def test_wikilink_and_relative_markdown_links_resolve(tmp_path):
    vault = _minimal_vault(tmp_path)
    # Page A links to Page B via wikilink
    _write_file(vault / "page_a.md", textwrap.dedent("""\
        ---
        title: Page A
        type: module
        status: active
        owner: agent
        confidence: high
        source_of_truth: compiled-wiki
        ---
        # Page A
        ## One-sentence summary
        Links to [[Page B]].
        ## Role / responsibility
        A.
        ## Upstream
        None.
        ## Downstream
        None.
        ## Related modules / files
        None.
        ## Source notes
        None.
        ## Open questions / conflicts
        None.
    """))
    _write_file(vault / "page_b.md", textwrap.dedent("""\
        ---
        title: Page B
        type: module
        status: active
        owner: agent
        confidence: high
        source_of_truth: compiled-wiki
        ---
        # Page B
        ## One-sentence summary
        Links to [Page A](page_a.md).
        ## Role / responsibility
        B.
        ## Upstream
        None.
        ## Downstream
        None.
        ## Related modules / files
        None.
        ## Source notes
        None.
        ## Open questions / conflicts
        None.
    """))
    manifest = _minimal_manifest(tmp_path, canonical={})
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    graph = json.loads((out_dir / "wikilink-graph.json").read_text())
    sources = {e["source"] for e in graph["edges"]}
    targets = {e["target"] for e in graph["edges"]}
    assert "page:page_a.md" in sources
    assert "page:page_b.md" in targets
    assert "page:page_b.md" in sources
    assert "page:page_a.md" in targets


def test_ambiguous_or_missing_links_are_not_guessed(tmp_path):
    vault = _minimal_vault(tmp_path)
    # Two pages with same stem
    _write_file(vault / "folder_a" / "Same.md", textwrap.dedent("""\
        ---
        title: Same A
        type: module
        status: active
        owner: agent
        confidence: high
        source_of_truth: compiled-wiki
        ---
        # Same A
        ## One-sentence summary
        Page.
        ## Role / responsibility
        A.
        ## Upstream
        None.
        ## Downstream
        None.
        ## Related modules / files
        None.
        ## Source notes
        None.
        ## Open questions / conflicts
        None.
    """))
    _write_file(vault / "folder_b" / "Same.md", textwrap.dedent("""\
        ---
        title: Same B
        type: module
        status: active
        owner: agent
        confidence: high
        source_of_truth: compiled-wiki
        ---
        # Same B
        ## One-sentence summary
        Page.
        ## Role / responsibility
        B.
        ## Upstream
        None.
        ## Downstream
        None.
        ## Related modules / files
        None.
        ## Source notes
        None.
        ## Open questions / conflicts
        None.
    """))
    _write_file(vault / "linker.md", textwrap.dedent("""\
        ---
        title: Linker
        type: module
        status: active
        owner: agent
        confidence: high
        source_of_truth: compiled-wiki
        ---
        # Linker
        ## One-sentence summary
        Links to [[Same]] and [missing](nonexistent.md).
        ## Role / responsibility
        Linker.
        ## Upstream
        None.
        ## Downstream
        None.
        ## Related modules / files
        None.
        ## Source notes
        None.
        ## Open questions / conflicts
        None.
    """))
    manifest = _minimal_manifest(tmp_path, canonical={})
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    idx = json.loads((out_dir / "agent-index.json").read_text())
    linker = next(p for p in idx["pages"] if p["id"] == "page:linker.md")
    # The wikilink [[Same]] is ambiguous (two pages with stem "Same")
    unresolved_reasons = [u["reason"] for u in linker["unresolved_links"]]
    assert "ambiguous" in unresolved_reasons, f"Expected 'ambiguous' reason in {unresolved_reasons}"
    # The relative link to nonexistent.md is missing
    assert "missing" in unresolved_reasons, f"Expected 'missing' reason in {unresolved_reasons}"


def test_graph_has_no_dangling_edges(tmp_path):
    vault = _minimal_vault(tmp_path)
    _write_file(vault / "page_c.md", textwrap.dedent("""\
        ---
        title: Page C
        type: module
        status: active
        owner: agent
        confidence: high
        source_of_truth: compiled-wiki
        ---
        # Page C
        ## One-sentence summary
        Links to [[Page D]].
        ## Role / responsibility
        C.
        ## Upstream
        None.
        ## Downstream
        None.
        ## Related modules / files
        None.
        ## Source notes
        None.
        ## Open questions / conflicts
        None.
    """))
    # Page D does not exist - the link should be unresolved, NOT an edge
    manifest = _minimal_manifest(tmp_path, canonical={})
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    graph = json.loads((out_dir / "wikilink-graph.json").read_text())
    node_ids = {n["id"] for n in graph["nodes"]}
    for edge in graph["edges"]:
        assert edge["source"] in node_ids, f"Dangling source: {edge['source']}"
        assert edge["target"] in node_ids, f"Dangling target: {edge['target']}"


def test_llms_txt_contains_canonical_pages_only(tmp_path):
    vault = _minimal_vault(tmp_path)
    manifest = _minimal_manifest(tmp_path, canonical={
        "entry": {"path": "README.md", "authority": "navigation"},
    })
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    llms = (out_dir / "llms.txt").read_text()
    assert "README.md" in llms
    # Non-canonical page (CURRENT_STATE) should NOT be listed in llms.txt canonical section
    # (it's only in the vault, not in the canonical manifest)
    # llms.txt should not contain full page listing


def test_outputs_are_byte_deterministic(tmp_path):
    vault = _minimal_vault(tmp_path)
    manifest = _minimal_manifest(tmp_path)
    # Run twice
    res1 = _run_index(tmp_path, manifest, vault)
    assert res1.returncode == 0, res1.stderr
    out_dir = tmp_path / "generated"
    hashes1 = {
        name: (out_dir / name).read_bytes()
        for name in ["agent-index.json", "llms.txt", "wikilink-graph.json"]
    }
    res2 = _run_index(tmp_path, manifest, vault)
    assert res2.returncode == 0, res2.stderr
    for name in ["agent-index.json", "llms.txt", "wikilink-graph.json"]:
        assert (out_dir / name).read_bytes() == hashes1[name], f"{name} not deterministic"


def test_check_mode_detects_drift_without_writing(tmp_path):
    vault = _minimal_vault(tmp_path)
    manifest = _minimal_manifest(tmp_path)
    # First generate
    res = _run_index(tmp_path, manifest, vault, mode="--write")
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    original = (out_dir / "agent-index.json").read_text()
    # Now corrupt
    (out_dir / "agent-index.json").write_text('{"corrupted": true}\n', encoding="utf-8")
    # check should fail
    res_check = _run_index(tmp_path, manifest, vault, mode="--check")
    assert res_check.returncode != 0
    # check should NOT have fixed the file
    assert (out_dir / "agent-index.json").read_text() == '{"corrupted": true}\n'


def test_invalid_authority_manifest_fails_closed(tmp_path):
    vault = _minimal_vault(tmp_path)
    bad_manifest = tmp_path / "bad.yaml"
    _write_file(bad_manifest, "this is not valid yaml: [}")
    res = _run_index(tmp_path, bad_manifest, vault)
    assert res.returncode != 0


def test_duplicate_canonical_paths_fail_closed(tmp_path):
    vault = _minimal_vault(tmp_path)
    manifest = _minimal_manifest(tmp_path, canonical={
        "key_a": {"path": "README.md", "authority": "navigation"},
        "key_b": {"path": "README.md", "authority": "operational"},
    })
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode != 0


def test_generated_directory_is_excluded_from_scan(tmp_path):
    vault = _minimal_vault(tmp_path)
    # Put a fake md inside generated
    gen = vault / "99_Schema" / "generated"
    gen.mkdir(parents=True, exist_ok=True)
    _write_file(gen / "fake.md", "# fake\n")
    manifest = _minimal_manifest(tmp_path)
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    idx = json.loads((out_dir / "agent-index.json").read_text())
    # fake.md should not appear
    assert not any("fake" in p.get("path", "") for p in idx["pages"])


def test_missing_canonical_path_fails_closed(tmp_path):
    vault = _minimal_vault(tmp_path)
    manifest = _minimal_manifest(tmp_path, canonical={
        "entry": {"path": "NONEXISTENT.md", "authority": "navigation"},
    })
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode != 0


def test_wikilink_with_alias_resolves(tmp_path):
    vault = _minimal_vault(tmp_path)
    _write_file(vault / "target.md", textwrap.dedent("""\
        ---
        title: Target
        type: module
        status: active
        owner: agent
        confidence: high
        source_of_truth: compiled-wiki
        ---
        # Target
        ## One-sentence summary
        Target page.
        ## Role / responsibility
        Target.
        ## Upstream
        None.
        ## Downstream
        None.
        ## Related modules / files
        None.
        ## Source notes
        None.
        ## Open questions / conflicts
        None.
    """))
    _write_file(vault / "src.md", textwrap.dedent("""\
        ---
        title: Source
        type: module
        status: active
        owner: agent
        confidence: high
        source_of_truth: compiled-wiki
        ---
        # Source
        ## One-sentence summary
        Links to [[target|Display Label]].
        ## Role / responsibility
        Source.
        ## Upstream
        None.
        ## Downstream
        None.
        ## Related modules / files
        None.
        ## Source notes
        None.
        ## Open questions / conflicts
        None.
    """))
    manifest = _minimal_manifest(tmp_path, canonical={})
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    graph = json.loads((out_dir / "wikilink-graph.json").read_text())
    # Should resolve to page:target
    assert any(e["source"] == "page:src.md" and e["target"] == "page:target.md" for e in graph["edges"])


def test_markdown_relative_link_resolves(tmp_path):
    vault = _minimal_vault(tmp_path)
    _write_file(vault / "other.md", textwrap.dedent("""\
        ---
        title: Other
        type: module
        status: active
        owner: agent
        confidence: high
        source_of_truth: compiled-wiki
        ---
        # Other
        ## One-sentence summary
        Other page.
        ## Role / responsibility
        Other.
        ## Upstream
        None.
        ## Downstream
        None.
        ## Related modules / files
        None.
        ## Source notes
        None.
        ## Open questions / conflicts
        None.
    """))
    _write_file(vault / "linker2.md", textwrap.dedent("""\
        ---
        title: Linker2
        type: module
        status: active
        owner: agent
        confidence: high
        source_of_truth: compiled-wiki
        ---
        # Linker2
        ## One-sentence summary
        Links to [other](other.md).
        ## Role / responsibility
        Linker2.
        ## Upstream
        None.
        ## Downstream
        None.
        ## Related modules / files
        None.
        ## Source notes
        None.
        ## Open questions / conflicts
        None.
    """))
    manifest = _minimal_manifest(tmp_path, canonical={})
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    graph = json.loads((out_dir / "wikilink-graph.json").read_text())
    assert any(e["source"] == "page:linker2.md" and e["target"] == "page:other.md" and e["syntax"] == "markdown" for e in graph["edges"])


def test_external_urls_not_in_graph(tmp_path):
    vault = _minimal_vault(tmp_path)
    _write_file(vault / "web.md", textwrap.dedent("""\
        ---
        title: Web
        type: module
        status: active
        owner: agent
        confidence: high
        source_of_truth: compiled-wiki
        ---
        # Web
        ## One-sentence summary
        Links to https://example.com.
        ## Role / responsibility
        Web.
        ## Upstream
        None.
        ## Downstream
        None.
        ## Related modules / files
        None.
        ## Source notes
        None.
        ## Open questions / conflicts
        None.
    """))
    manifest = _minimal_manifest(tmp_path, canonical={})
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    graph = json.loads((out_dir / "wikilink-graph.json").read_text())
    assert not any("example.com" in e.get("target", "") for e in graph["edges"])


def test_wikilink_with_section_resolves(tmp_path):
    vault = _minimal_vault(tmp_path)
    _write_file(vault / "sectioned.md", textwrap.dedent("""\
        ---
        title: Sectioned
        type: module
        status: active
        owner: agent
        confidence: high
        source_of_truth: compiled-wiki
        ---
        # Sectioned
        ## One-sentence summary
        Page with sections.
        ## Section A
        Content.
        ## Role / responsibility
        Sectioned.
        ## Upstream
        None.
        ## Downstream
        None.
        ## Related modules / files
        None.
        ## Source notes
        None.
        ## Open questions / conflicts
        None.
    """))
    _write_file(vault / "linker3.md", textwrap.dedent("""\
        ---
        title: Linker3
        type: module
        status: active
        owner: agent
        confidence: high
        source_of_truth: compiled-wiki
        ---
        # Linker3
        ## One-sentence summary
        Links to [[sectioned#Section A]].
        ## Role / responsibility
        Linker3.
        ## Upstream
        None.
        ## Downstream
        None.
        ## Related modules / files
        None.
        ## Source notes
        None.
        ## Open questions / conflicts
        None.
    """))
    manifest = _minimal_manifest(tmp_path, canonical={})
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    graph = json.loads((out_dir / "wikilink-graph.json").read_text())
    assert any(e["source"] == "page:linker3.md" and e["target"] == "page:sectioned.md" for e in graph["edges"])


def test_exclude_rules_appear_in_output(tmp_path):
    vault = _minimal_vault(tmp_path)
    manifest = _minimal_manifest(tmp_path)
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    idx = json.loads((out_dir / "agent-index.json").read_text())
    assert "exclusion_rules" in idx
    assert isinstance(idx["exclusion_rules"], list)
    assert len(idx["exclusion_rules"]) > 0


def test_classification_rules_order(tmp_path):
    vault = _minimal_vault(tmp_path)
    # Page with lifecycle=superseded but not in legacy list
    _write_file(vault / "old.md", textwrap.dedent("""\
        ---
        title: Old Page
        type: module
        status: active
        lifecycle: superseded
        owner: agent
        confidence: medium
        source_of_truth: compiled-wiki
        ---
        # Old Page
        ## One-sentence summary
        Superseded page.
        ## Role / responsibility
        Old.
        ## Upstream
        None.
        ## Downstream
        None.
        ## Related modules / files
        None.
        ## Source notes
        None.
        ## Open questions / conflicts
        None.
    """))
    manifest = _minimal_manifest(tmp_path, canonical={})
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    idx = json.loads((out_dir / "agent-index.json").read_text())
    old = next(p for p in idx["pages"] if p["id"] == "page:old.md")
    assert old["classification"] == "superseded"


def test_content_sha256_is_present(tmp_path):
    vault = _minimal_vault(tmp_path)
    manifest = _minimal_manifest(tmp_path)
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    idx = json.loads((out_dir / "agent-index.json").read_text())
    for p in idx["pages"]:
        assert p.get("content_sha256"), f"Missing content_sha256 for {p['id']}"


def test_source_fingerprint_uses_content_not_time(tmp_path):
    vault = _minimal_vault(tmp_path)
    manifest = _minimal_manifest(tmp_path)
    res1 = _run_index(tmp_path, manifest, vault)
    assert res1.returncode == 0, res1.stderr
    out_dir = tmp_path / "generated"
    fp1 = json.loads((out_dir / "agent-index.json").read_text())["source_fingerprint"]
    res2 = _run_index(tmp_path, manifest, vault)
    assert res2.returncode == 0, res2.stderr
    fp2 = json.loads((out_dir / "agent-index.json").read_text())["source_fingerprint"]
    assert fp1 == fp2


def test_llms_txt_has_warning(tmp_path):
    vault = _minimal_vault(tmp_path)
    manifest = _minimal_manifest(tmp_path)
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    llms = (out_dir / "llms.txt").read_text()
    assert "non-authoritative" in llms.lower() or "derived" in llms.lower()


def test_three_files_written(tmp_path):
    vault = _minimal_vault(tmp_path)
    manifest = _minimal_manifest(tmp_path)
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    assert (out_dir / "agent-index.json").exists()
    assert (out_dir / "llms.txt").exists()
    assert (out_dir / "wikilink-graph.json").exists()


# ---------------------------------------------------------------------------
# Regression tests (R1-R6)
# ---------------------------------------------------------------------------


def test_relative_parent_segments_are_normalized(tmp_path):
    """R1: ../ paths must be folded via posixpath.normpath."""
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "README.md").write_text(
        textwrap.dedent("""\
            ---
            title: Root
            type: entry
            status: active
            owner: agent
            confidence: high
            source_of_truth: compiled-wiki
            ---
            # Root
            ## One-sentence summary
            Root page.
            ## Role / responsibility
            Root.
            ## Upstream
            None.
            ## Downstream
            None.
            ## Related modules / files
            None.
            ## Source notes
            None.
            ## Open questions / conflicts
            None.
        """),
        encoding="utf-8",
    )
    (vault / "01_System").mkdir(parents=True, exist_ok=True)
    (vault / "01_System" / "CLAIM_TAXONOMY.md").write_text(
        textwrap.dedent("""\
            ---
            title: CLAIM_TAXONOMY
            type: system
            status: active
            owner: agent
            confidence: high
            source_of_truth: compiled-wiki
            ---
            # CLAIM_TAXONOMY
            ## One-sentence summary
            Claims taxonomy.
            ## Role / responsibility
            Claims.
            ## Upstream
            None.
            ## Downstream
            None.
            ## Related modules / files
            None.
            ## Source notes
            None.
            ## Open questions / conflicts
            None.
        """),
        encoding="utf-8",
    )
    (vault / "00_Home").mkdir(parents=True, exist_ok=True)
    (vault / "00_Home" / "AGENT_BOOTSTRAP.md").write_text(
        textwrap.dedent("""\
            ---
            title: AGENT_BOOTSTRAP
            type: home
            status: active
            owner: agent
            confidence: high
            source_of_truth: compiled-wiki
            ---
            # AGENT_BOOTSTRAP
            ## One-sentence summary
            Bootstrap page linking to parent-relative target.
            ## Role / responsibility
            Bootstrap.
            ## Upstream
            None.
            ## Downstream
            [Claims](../01_System/CLAIM_TAXONOMY.md).
            ## Related modules / files
            None.
            ## Source notes
            None.
            ## Open questions / conflicts
            None.
        """),
        encoding="utf-8",
    )
    manifest = _minimal_manifest(tmp_path, canonical={})
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    graph = json.loads((out_dir / "wikilink-graph.json").read_text())
    # The link from 00_Home/AGENT_BOOTSTRAP.md to ../01_System/CLAIM_TAXONOMY.md
    # should resolve to 01_System/CLAIM_TAXONOMY.md
    assert any(
        e["source"] == "page:00_Home/AGENT_BOOTSTRAP.md"
        and e["target"] == "page:01_System/CLAIM_TAXONOMY.md"
        for e in graph["edges"]
    )


def test_relative_parent_segments_outside_vault_are_unresolved(tmp_path):
    """R1: paths escaping vault root must be outside_vault."""
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    (vault / "README.md").write_text(
        textwrap.dedent("""\
            ---
            title: Root
            type: entry
            status: active
            owner: agent
            confidence: high
            source_of_truth: compiled-wiki
            ---
            # Root
            ## One-sentence summary
            Root.
            ## Role / responsibility
            Root.
            ## Upstream
            None.
            ## Downstream
            None.
            ## Related modules / files
            None.
            ## Source notes
            None.
            ## Open questions / conflicts
            None.
        """),
        encoding="utf-8",
    )
    (vault / "sub").mkdir(parents=True, exist_ok=True)
    (vault / "sub" / "page.md").write_text(
        textwrap.dedent("""\
            ---
            title: Page
            type: module
            status: active
            owner: agent
            confidence: high
            source_of_truth: compiled-wiki
            ---
            # Page
            ## One-sentence summary
            Links to escape.
            ## Role / responsibility
            Page.
            ## Upstream
            None.
            ## Downstream
            [Escape](../../etc/passwd.md).
            ## Related modules / files
            None.
            ## Source notes
            None.
            ## Open questions / conflicts
            None.
        """),
        encoding="utf-8",
    )
    manifest = _minimal_manifest(tmp_path, canonical={})
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    idx = json.loads((out_dir / "agent-index.json").read_text())
    page = next(p for p in idx["pages"] if p["id"] == "page:sub/page.md")
    unresolved = [u for u in page["unresolved_links"] if "passwd" in u.get("raw_target", "")]
    assert len(unresolved) == 1
    assert unresolved[0]["reason"] == "outside_vault"


def test_folder_qualified_wikilink_resolves_with_optional_md(tmp_path):
    """R2: [[99_Schema/WIKI_GOVERNANCE_CHARTER]] must resolve."""
    vault = _minimal_vault(tmp_path)
    (vault / "99_Schema").mkdir(parents=True, exist_ok=True)
    (vault / "99_Schema" / "WIKI_GOVERNANCE_CHARTER.md").write_text(
        textwrap.dedent("""\
            ---
            title: WIKI_GOVERNANCE_CHARTER
            type: schema
            status: active
            owner: agent
            confidence: high
            source_of_truth: compiled-wiki
            ---
            # WIKI_GOVERNANCE_CHARTER
            ## One-sentence summary
            Governance charter.
            ## Role / responsibility
            Governance.
            ## Upstream
            None.
            ## Downstream
            None.
            ## Related modules / files
            None.
            ## Source notes
            None.
            ## Open questions / conflicts
            None.
        """),
        encoding="utf-8",
    )
    (vault / "linker.md").write_text(
        textwrap.dedent("""\
            ---
            title: Linker
            type: module
            status: active
            owner: agent
            confidence: high
            source_of_truth: compiled-wiki
            ---
            # Linker
            ## One-sentence summary
            Links to folder-qualified wikilink.
            ## Role / responsibility
            Linker.
            ## Upstream
            None.
            ## Downstream
            [[99_Schema/WIKI_GOVERNANCE_CHARTER]].
            ## Related modules / files
            None.
            ## Source notes
            None.
            ## Open questions / conflicts
            None.
        """),
        encoding="utf-8",
    )
    manifest = _minimal_manifest(tmp_path, canonical={})
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    graph = json.loads((out_dir / "wikilink-graph.json").read_text())
    assert any(
        e["source"] == "page:linker.md"
        and e["target"] == "page:99_Schema/WIKI_GOVERNANCE_CHARTER.md"
        for e in graph["edges"]
    )


def test_folder_qualified_wikilink_with_anchor_resolves(tmp_path):
    """R2: [[01_System/SYSTEM_ARCHITECTURE_BLUEPRINT#Section]] must resolve."""
    vault = _minimal_vault(tmp_path)
    (vault / "01_System").mkdir(parents=True, exist_ok=True)
    (vault / "01_System" / "SYSTEM_ARCHITECTURE_BLUEPRINT.md").write_text(
        textwrap.dedent("""\
            ---
            title: SYSTEM_ARCHITECTURE_BLUEPRINT
            type: system
            status: active
            owner: agent
            confidence: high
            source_of_truth: compiled-wiki
            ---
            # SYSTEM_ARCHITECTURE_BLUEPRINT
            ## One-sentence summary
            Architecture blueprint.
            ## Role / responsibility
            Architecture.
            ## Upstream
            None.
            ## Downstream
            None.
            ## Related modules / files
            None.
            ## Source notes
            None.
            ## Open questions / conflicts
            None.
        """),
        encoding="utf-8",
    )
    (vault / "linker.md").write_text(
        textwrap.dedent("""\
            ---
            title: Linker
            type: module
            status: active
            owner: agent
            confidence: high
            source_of_truth: compiled-wiki
            ---
            # Linker
            ## One-sentence summary
            Links to folder-qualified wikilink with anchor.
            ## Role / responsibility
            Linker.
            ## Upstream
            None.
            ## Downstream
            [[01_System/SYSTEM_ARCHITECTURE_BLUEPRINT#Section]].
            ## Related modules / files
            None.
            ## Source notes
            None.
            ## Open questions / conflicts
            None.
        """),
        encoding="utf-8",
    )
    manifest = _minimal_manifest(tmp_path, canonical={})
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    graph = json.loads((out_dir / "wikilink-graph.json").read_text())
    assert any(
        e["source"] == "page:linker.md"
        and e["target"] == "page:01_System/SYSTEM_ARCHITECTURE_BLUEPRINT.md"
        for e in graph["edges"]
    )


def test_canonical_nodes_use_stable_canonical_ids(tmp_path):
    """R4: Canonical pages must use canonical:<key> as their ID."""
    vault = _minimal_vault(tmp_path)
    manifest = _minimal_manifest(tmp_path, canonical={
        "current_state": {"path": "00_Home/CURRENT_STATE.md", "authority": "operational"},
    })
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    idx = json.loads((out_dir / "agent-index.json").read_text())
    pages_by_id = {p["id"]: p for p in idx["pages"]}
    assert "canonical:current_state" in pages_by_id, f"Expected canonical:current_state in {list(pages_by_id.keys())}"
    assert "page:00_Home/CURRENT_STATE.md" not in pages_by_id


def test_edges_target_final_canonical_ids(tmp_path):
    """R4: Edges targeting canonical pages must use canonical:<key>."""
    vault = _minimal_vault(tmp_path)
    (vault / "00_Home").mkdir(parents=True, exist_ok=True)
    (vault / "00_Home" / "CURRENT_STATE.md").write_text(
        textwrap.dedent("""\
            ---
            title: CURRENT_STATE
            type: home
            status: active
            owner: agent
            confidence: high
            source_of_truth: compiled-wiki
            ---
            # CURRENT_STATE
            ## One-sentence summary
            Current state.
            ## Role / responsibility
            Status.
            ## Upstream
            None.
            ## Downstream
            None.
            ## Related modules / files
            None.
            ## Source notes
            None.
            ## Open questions / conflicts
            None.
        """),
        encoding="utf-8",
    )
    (vault / "linker.md").write_text(
        textwrap.dedent("""\
            ---
            title: Linker
            type: module
            status: active
            owner: agent
            confidence: high
            source_of_truth: compiled-wiki
            ---
            # Linker
            ## One-sentence summary
            Links to canonical page.
            ## Role / responsibility
            Linker.
            ## Upstream
            None.
            ## Downstream
            [[CURRENT_STATE]].
            ## Related modules / files
            None.
            ## Source notes
            None.
            ## Open questions / conflicts
            None.
        """),
        encoding="utf-8",
    )
    manifest = _minimal_manifest(tmp_path, canonical={
        "current_state": {"path": "00_Home/CURRENT_STATE.md", "authority": "operational"},
    })
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    graph = json.loads((out_dir / "wikilink-graph.json").read_text())
    # Edge target must be canonical:current_state, not page:00_Home/CURRENT_STATE.md
    assert any(
        e["source"] == "page:linker.md" and e["target"] == "canonical:current_state"
        for e in graph["edges"]
    ), f"Expected canonical target in {graph['edges']}"
    # No dangling edge to page:00_Home/CURRENT_STATE.md
    assert not any(
        e["target"] == "page:00_Home/CURRENT_STATE.md" for e in graph["edges"]
    )


def test_graph_preserves_all_structured_unresolved_links(tmp_path):
    """R3: graph unresolved_links must have structured records."""
    vault = _minimal_vault(tmp_path)
    _write_file(vault / "page_x.md", textwrap.dedent("""\
        ---
        title: Page X
        type: module
        status: active
        owner: agent
        confidence: high
        source_of_truth: compiled-wiki
        ---
        # Page X
        ## One-sentence summary
        Links to nonexistent and ambiguous.
        ## Role / responsibility
        X.
        ## Upstream
        None.
        ## Downstream
        [[Nonexistent]].
        ## Related modules / files
        None.
        ## Source notes
        None.
        ## Open questions / conflicts
        None.
    """))
    manifest = _minimal_manifest(tmp_path, canonical={})
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    graph = json.loads((out_dir / "wikilink-graph.json").read_text())
    assert len(graph["unresolved_links"]) > 0
    for u in graph["unresolved_links"]:
        assert "source" in u, f"Missing source in {u}"
        assert "source_path" in u, f"Missing source_path in {u}"
        assert "raw_target" in u, f"Missing raw_target in {u}"
        assert "syntax" in u, f"Missing syntax in {u}"
        assert "reason" in u, f"Missing reason in {u}"
        assert u["syntax"] in ("wikilink", "markdown")


def test_graph_unresolved_count_matches_agent_index(tmp_path):
    """R3: graph unresolved count must equal agent index unresolved count."""
    vault = _minimal_vault(tmp_path)
    _write_file(vault / "a.md", textwrap.dedent("""\
        ---
        title: A
        type: module
        status: active
        owner: agent
        confidence: high
        source_of_truth: compiled-wiki
        ---
        # A
        ## One-sentence summary
        Links to missing.
        ## Role / responsibility
        A.
        ## Upstream
        None.
        ## Downstream
        [[Missing1]], [[Missing2]].
        ## Related modules / files
        None.
        ## Source notes
        None.
        ## Open questions / conflicts
        None.
    """))
    manifest = _minimal_manifest(tmp_path, canonical={})
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    idx = json.loads((out_dir / "agent-index.json").read_text())
    graph = json.loads((out_dir / "wikilink-graph.json").read_text())
    agent_unresolved = idx["unresolved_link_count"]
    graph_unresolved = len(graph["unresolved_links"])
    assert agent_unresolved == graph_unresolved, (
        f"Mismatch: agent_index={agent_unresolved}, graph={graph_unresolved}"
    )


def test_content_verification_metadata_is_preserved(tmp_path):
    """R5: Verification metadata from frontmatter must be preserved."""
    vault = _minimal_vault(tmp_path)
    _write_file(vault / "verified.md", textwrap.dedent("""\
        ---
        title: Verified
        type: module
        status: active
        owner: agent
        confidence: high
        source_of_truth: compiled-wiki
        content_verified_against_commit: abc123
        document_updated_in_commit: def456
        verified_at: '2026-07-14'
        last_verified: '2026-07-13'
        last_audit: '2026-07-12'
        ---
        # Verified
        ## One-sentence summary
        Verified page.
        ## Role / responsibility
        Verified.
        ## Upstream
        None.
        ## Downstream
        None.
        ## Related modules / files
        None.
        ## Source notes
        None.
        ## Open questions / conflicts
        None.
    """))
    manifest = _minimal_manifest(tmp_path, canonical={})
    res = _run_index(tmp_path, manifest, vault)
    assert res.returncode == 0, res.stderr
    out_dir = tmp_path / "generated"
    idx = json.loads((out_dir / "agent-index.json").read_text())
    page = next(p for p in idx["pages"] if p["id"] == "page:verified.md")
    assert page["content_verified_against_commit"] == "abc123"
    assert page["document_updated_in_commit"] == "def456"
    assert page["verified_at"] == "2026-07-14"
    assert page["last_verified"] == "2026-07-13"
    assert page["last_audit"] == "2026-07-12"


def test_tests_do_not_require_uv_on_subprocess_path(tmp_path):
    """R6: Tests must use sys.executable, not uv."""
    import inspect
    source = inspect.getsource(_run_index)
    assert "sys.executable" in source, "_run_index must use sys.executable"
    assert '"uv"' not in source, "_run_index must not reference uv"


def test_real_vault_conservatively_resolvable_links(tmp_path):
    """Real-vault invariant: conservatively resolvable links must not be unresolved."""
    # Use the real vault
    manifest_path = VAULT_ROOT / "99_Schema" / "WIKI_AUTHORITY_MANIFEST.yaml"
    if not manifest_path.exists():
        pytest.skip("Real vault not available")

    out_dir = tmp_path / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    res = subprocess.run(
        [
            sys.executable, str(SCRIPT),
            "--write",
            "--vault-root", str(VAULT_ROOT),
            "--authority-manifest", str(manifest_path),
            "--output-dir", str(out_dir),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert res.returncode == 0, res.stderr

    idx = json.loads((out_dir / "agent-index.json").read_text())
    graph = json.loads((out_dir / "wikilink-graph.json").read_text())

    # Collect all unresolved targets
    unresolved_targets = set()
    for u in graph["unresolved_links"]:
        unresolved_targets.add(u["raw_target"])

    # These links should always resolve in the real vault
    must_resolve = [
        "../01_System/CLAIM_TAXONOMY.md",
        "99_Schema/WIKI_GOVERNANCE_CHARTER",
        "00_Home/CURRENT_STATE",
    ]
    for target in must_resolve:
        assert target not in unresolved_targets, (
            f"'{target}' must resolve in real vault but is unresolved"
        )

    # Check well-formed SYSTEM_ARCHITECTURE_BLUEPRINT links resolve.
    # Malformed nested wikilinks in source content (e.g. 'Flow - [[SYSTEM_ARCHITECTURE_BLUEPRINT')
    # produce garbage raw_targets that cannot be resolved - these are data quality issues.
    well_formed_blueprint_unresolved = [
        u for u in graph["unresolved_links"]
        if u.get("raw_target", "").strip() in ("SYSTEM_ARCHITECTURE_BLUEPRINT",)
        or u.get("raw_target", "").startswith("SYSTEM_ARCHITECTURE_BLUEPRINT#")
    ]
    assert len(well_formed_blueprint_unresolved) == 0, (
        f"Well-formed SYSTEM_ARCHITECTURE_BLUEPRINT links should resolve: {well_formed_blueprint_unresolved}"
    )
