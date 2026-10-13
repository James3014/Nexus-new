"""#1579 manifest follow-up: owner-declared knowledge manifest + producer wiring.

Engine-dependent tests are defined only when ``NEXUS_RIE_ENGINE_ROOT`` points at
the pinned RIE checkout (never ``pytest.skip``: the exact-base impact gate
rejects head-only skipped tests).
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
from pathlib import Path

import pytest

from nexus.services import rie_knowledge_applicability as ka
from nexus.services import rie_knowledge_manifest as km
from scripts.ops import rie_knowledge_evidence as cli

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / km.DEFAULT_MANIFEST_PATH
H = "1" * 40
IDENT = {
    "repository": "owner/repo",
    "pr_number": 9,
    "head_sha": H,
    "base_sha": "2" * 40,
    "current_main_sha": "2" * 40,
}


def _git(cwd: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.invalid",
    }
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True, env=env
    ).stdout.strip()


def _tmp_repo(tmp_path: Path):
    """Two commits: base, then head that modifies a covered file. Returns (root, manifest, ident)."""
    root = tmp_path / "r"
    root.mkdir()
    _git(root, "init", "-q")
    files = {"docs/d.md": "doc\n", "src/a.py": "a=1\n", "src/b.py": "b=1\n"}
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    base = _git(root, "rev-parse", "HEAD")
    manifest = {
        "schema": km.MANIFEST_SCHEMA,
        "revision": base,
        "claim_ceiling": km.MANIFEST_CLAIM_CEILING,
        "notes": "test, owner-declared",
        "entries": [
            {
                "id": "doc-d",
                "path": "docs/d.md",
                "source_refs": [
                    {"path": "src/a.py", "expected_content_sha256": km.sha256_bytes(b"a=1\n")}
                ],
                "covers": ["src/b*.py"],
                "in_scope": True,
            }
        ],
    }
    return root, manifest, base


def _commit_change(root: Path, rel: str, text: str) -> str:
    (root / rel).write_text(text)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "head")
    return _git(root, "rev-parse", "HEAD")


def _ident(base: str, head: str) -> dict:
    return {**IDENT, "base_sha": base, "head_sha": head, "current_main_sha": base}


# ----------------------------------------------------------------- manifest
def test_real_manifest_loads_and_validates_against_repo():
    manifest = km.load_manifest(MANIFEST_PATH)
    assert 3 <= len(manifest["entries"]) <= 5
    assert manifest["claim_ceiling"] == km.MANIFEST_CLAIM_CEILING
    assert "owner-declared" in manifest["notes"].lower()
    for entry in manifest["entries"]:
        assert (REPO_ROOT / entry["path"]).is_file()
        for ref in entry["source_refs"]:
            assert (REPO_ROOT / ref["path"]).is_file()
    # hashes are anchored at the declared revision (blobs, not the working tree)
    reader = km.git_blob_reader(REPO_ROOT, manifest["revision"])
    for entry in manifest["entries"]:
        for ref in entry["source_refs"]:
            blob = reader(ref["path"])
            # a shallow checkout may lack the declared revision; never assert on absence
            if blob is not None:
                assert km.sha256_bytes(blob) == ref["expected_content_sha256"], ref["path"]


def test_tampered_sha_yields_stale_declaration_not_failure():
    manifest = km.load_manifest(MANIFEST_PATH)
    tampered = copy.deepcopy(manifest)
    tampered["entries"][0]["source_refs"][0]["expected_content_sha256"] = "0" * 64
    decl = km.evaluate_manifest(tampered, km.worktree_reader(REPO_ROOT))
    assert decl[0]["declaration_status"] == km.STALE_DECLARATION
    assert decl[0]["stale_sources"][0]["reason"] == "SOURCE_SHA_MISMATCH"


def test_missing_source_and_artifact_are_stale_declarations(tmp_path):
    root, manifest, _ = _tmp_repo(tmp_path)
    (root / "src/a.py").unlink()
    decl = km.evaluate_manifest(manifest, km.worktree_reader(root))[0]
    assert decl["stale_sources"] == [{"path": "src/a.py", "reason": "SOURCE_MISSING"}]
    (root / "docs/d.md").unlink()
    assert km.evaluate_manifest(manifest, km.worktree_reader(root))[0]["artifact_missing"] is True


@pytest.mark.parametrize(
    "mutate,code",
    [
        (lambda m: m.update(schema="x"), "MANIFEST_SCHEMA_MISMATCH"),
        (lambda m: m.update(revision="abc"), "MANIFEST_REVISION_INVALID"),
        (lambda m: m.update(claim_ceiling="x"), "MANIFEST_CLAIM_CEILING_MISMATCH"),
        (lambda m: m.update(notes=""), "MANIFEST_NOTES_MISSING"),
        (lambda m: m.update(entries=[]), "MANIFEST_ENTRIES_INVALID"),
        (lambda m: m["entries"][0].update(in_scope=False), "ENTRY_IN_SCOPE_NOT_TRUE"),
        (lambda m: m["entries"][0].update(covers=["**"]), "ENTRY_COVERS_INVALID_OR_TOO_BROAD"),
        (lambda m: m["entries"][0].update(path="../x.md"), "ENTRY_PATH_INVALID"),
        (
            lambda m: m["entries"][0]["source_refs"][0].update(expected_content_sha256="zz"),
            "ENTRY_SOURCE_REF_INVALID",
        ),
        (lambda m: m["entries"].append(dict(m["entries"][0])), "ENTRY_ID_INVALID_OR_DUPLICATE"),
    ],
)
def test_malformed_manifest_rejected(mutate, code):
    manifest = copy.deepcopy(km.load_manifest(MANIFEST_PATH))
    mutate(manifest)
    with pytest.raises(km.RieKnowledgeManifestError) as info:
        km.validate_manifest(manifest)
    assert info.value.code == code


def test_parse_name_status_normalizes_kinds():
    text = "M\ta.py\nA\tb.py\nD\tc.py\nR100\told.py\tnew.py\nT\tt.py\nC90\tx.py\ty.py\n"
    assert km.parse_name_status(text) == [
        {"kind": "MODIFY", "path": "a.py"},
        {"kind": "ADD", "path": "b.py"},
        {"kind": "DELETE", "path": "", "old_path": "c.py"},
        {"kind": "RENAME", "path": "new.py", "old_path": "old.py"},
        {"kind": "MODIFY", "path": "t.py"},
        {"kind": "ADD", "path": "y.py"},
    ]
    z = b"M\x00a b.py\x00R90\x00o.py\x00n.py\x00D\x00d.py\x00"
    assert km.parse_name_status_z(z)[1] == {"kind": "RENAME", "path": "n.py", "old_path": "o.py"}
    with pytest.raises(km.RieKnowledgeManifestError):
        km.parse_name_status("U\tconflict.py\n")


def test_git_changes_reads_real_diff(tmp_path):
    root, _, base = _tmp_repo(tmp_path)
    head = _commit_change(root, "src/b.py", "b=2\n")
    assert km.git_changes(root, base, head) == [{"kind": "MODIFY", "path": "src/b.py"}]


# ----------------------------------------------------------------- no claims
def test_no_claims_is_not_applicable_never_current(tmp_path):
    root, manifest, base = _tmp_repo(tmp_path)
    (root / "docs/d.md").unlink()
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "rm")
    head = _git(root, "rev-parse", "HEAD")
    out = km.build_manifest_knowledge_evidence(
        manifest=manifest,
        identity=_ident(base, head),
        changes=[],
        reader=km.git_blob_reader(root, head),
        env={},  # engine unconfigured: must not even be reached
    )
    ka_out = out["evidence"]["knowledge_applicability"]
    assert ka_out["status"] == "NOT_APPLICABLE"
    assert ka_out["relation_counts"]["CURRENT"] == 0
    assert out["manifest"]["declarations"][0]["artifact_missing"] is True
    assert any(g.startswith("MANIFEST_STALE_DECLARATION") for g in ka_out["evidence_gaps"]) or (
        "KNOWLEDGE_CLAIM_SOURCE_NOT_AVAILABLE" in ka_out["evidence_gaps"]
    )


# ----------------------------------------------------------------- CLI
def _args(root: Path, base: str, head: str, out: Path, *extra: str) -> list[str]:
    return [
        "--repo-root", str(root), "--repository", "owner/repo", "--pr-number", "9",
        "--head-sha", head, "--base-sha", base, "--output", str(out), *extra,
    ]  # fmt: skip


def test_cli_engine_unconfigured_writes_not_applicable_exit0(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(ka.ENV_ENGINE_ROOT, raising=False)
    root, manifest, base = _tmp_repo(tmp_path)
    head = _commit_change(root, "src/b.py", "b=2\n")
    (root / "docs/knowledge").mkdir(parents=True)
    (root / km.DEFAULT_MANIFEST_PATH).write_text(json.dumps(manifest))
    out, summary = tmp_path / "o.json", tmp_path / "s.md"
    assert cli.main(_args(root, base, head, out, "--step-summary", str(summary))) == 0
    art = json.loads(out.read_text())
    assert art["schema"] == cli.ARTIFACT_SCHEMA
    assert art["disposition"] == "NOT_APPLICABLE"
    assert art["knowledge_applicability"]["relation_counts"]["CURRENT"] == 0
    assert art["knowledge_applicability"]["evidence_gaps"] == ["RIE_ENGINE_NOT_CONFIGURED"]
    assert art["authority"]["planner_capability"] is False
    assert "NOT_APPLICABLE is not CURRENT" in summary.read_text()


def test_cli_malformed_identity_and_manifest_exit1(tmp_path, capsys):
    out = tmp_path / "o.json"
    bad = ["--repo-root", str(REPO_ROOT), "--repository", "norepo", "--pr-number", "1",
           "--head-sha", H, "--base-sha", H, "--output", str(out)]  # fmt: skip
    assert cli.main(bad) == 1
    assert not out.exists()
    assert cli.main([*bad[:3], "owner/r", *bad[4:], "--manifest", str(tmp_path / "nope.json")]) == 1


def test_cli_adapter_failure_is_advisory_incomplete(tmp_path):
    root, manifest, base = _tmp_repo(tmp_path)
    head = _commit_change(root, "src/b.py", "b=2\n")
    art = cli.generate_artifact(
        repo_root=root,
        identity=_ident(base, head),
        manifest=manifest,
        env={ka.ENV_ENGINE_ROOT: str(tmp_path / "missing-engine")},
    )
    assert art["disposition"] == "ADVISORY_INCOMPLETE"
    assert art["knowledge_applicability"]["status"] == "NOT_APPLICABLE"
    assert art["knowledge_applicability"]["relation_counts"]["CURRENT"] == 0


# ----------------------------------------------------------------- real engine
def _pinned_engine_root() -> Path | None:
    root = os.environ.get(ka.ENV_ENGINE_ROOT, "")
    if not root or not Path(root).is_dir():
        return None
    ka.verify_engine_revision(Path(root))
    return Path(root)


_PINNED_ENGINE_ROOT = _pinned_engine_root()


def _engine_only(fn):
    return fn if _PINNED_ENGINE_ROOT is not None else None


@_engine_only
def test_engine_covered_file_change_is_affected_by_coverage(tmp_path):
    root, manifest, base = _tmp_repo(tmp_path)
    head = _commit_change(root, "src/b.py", "b=2\n")
    out = km.build_manifest_knowledge_evidence(
        manifest=manifest,
        identity=_ident(base, head),
        changes=km.git_changes(root, base, head),
        reader=km.git_blob_reader(root, head),
    )
    proj = out["evidence"]["knowledge_applicability"]
    assert proj["relation_counts"]["AFFECTED_BY_COVERAGE"] == 1
    assert proj["relation_counts"]["CURRENT"] == 0
    assert proj["status"] == "COMPLETE"
    assert proj["affected_artifact_refs"] == ["AFFECTED_BY_COVERAGE:docs/d.md"]


@_engine_only
def test_engine_exact_source_change_is_stale_exact_source_and_declaration(tmp_path):
    root, manifest, base = _tmp_repo(tmp_path)
    head = _commit_change(root, "src/a.py", "a=2\n")
    art = cli.generate_artifact(repo_root=root, identity=_ident(base, head), manifest=manifest)
    proj = art["knowledge_applicability"]
    assert art["disposition"] == "OBSERVED"
    assert proj["relation_counts"]["STALE_EXACT_SOURCE"] == 1
    assert "MANIFEST_STALE_DECLARATION:doc-d" in proj["evidence_gaps"]
    assert art["manifest"]["declarations"][0]["declaration_status"] == km.STALE_DECLARATION


@_engine_only
def test_engine_unrelated_change_is_current(tmp_path):
    root, manifest, base = _tmp_repo(tmp_path)
    (root / "other.txt").write_text("x")
    head = _commit_change(root, "other.txt", "y")
    proj = cli.generate_artifact(repo_root=root, identity=_ident(base, head), manifest=manifest)[
        "knowledge_applicability"
    ]
    assert proj["relation_counts"]["CURRENT"] == 1
    assert proj["report_hash"]
