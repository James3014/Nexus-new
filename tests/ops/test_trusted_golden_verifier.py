from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts.ops.trusted_golden_verifier import verify

GOOD = """\
CASES = (
    _c("GB-001", "one", "invariant", "normal", "x", ("AGENTS.md",)),
    _c("GB-002", "two", "regression", "normal", "x", ("AGENTS.md",)),
)
"""


def _repo(tmp_path: Path, source: str) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "tests/golden_behavior").mkdir(parents=True)
    (repo / "tests/golden_behavior/corpus.py").write_text(source, encoding="utf-8")
    subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "fixture",
        ],
        check=True,
    )
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    return repo, head


def test_invalid_duplicate_corpus_fails_closed(tmp_path: Path) -> None:
    repo, head = _repo(tmp_path, GOOD.replace('"GB-002"', '"GB-001"'))
    with pytest.raises(ValueError, match="duplicate_case_id: GB-001"):
        manifest, evidence = _sealed_evidence(repo, head, tmp_path)
        verify(repo, head, manifest_path=manifest, evidence_path=evidence)


def test_single_case_ast_false_green_fails_closed(tmp_path: Path) -> None:
    repo, head = _repo(tmp_path, GOOD.split('    _c("GB-002"')[0] + ")\n")
    with pytest.raises(ValueError, match="too few case ids"):
        manifest, evidence = _sealed_evidence(repo, head, tmp_path)
        verify(repo, head, manifest_path=manifest, evidence_path=evidence)


def test_missing_sealed_evidence_fails_closed(tmp_path: Path) -> None:
    repo, head = _repo(tmp_path, GOOD)
    manifest, _ = _sealed_evidence(repo, head, tmp_path)
    with pytest.raises(ValueError, match="must be supplied together"):
        verify(repo, head, manifest_path=manifest)
    with pytest.raises(ValueError, match="must be supplied together"):
        _, evidence = _sealed_evidence(repo, head, tmp_path)
        verify(repo, head, evidence_path=evidence)


def test_unsealed_evidence_cannot_produce_trusted_pass(tmp_path: Path) -> None:
    repo, head = _repo(tmp_path, GOOD)
    manifest, _ = _sealed_evidence(repo, head, tmp_path)
    evidence = tmp_path / "unsealed.json"
    evidence.write_text(
        '{"golden_report": null, "golden_report_sha256": "unsealed"}\n', encoding="utf-8"
    )
    with pytest.raises(ValueError, match="sealed Golden evidence is missing"):
        verify(repo, head, manifest_path=manifest, evidence_path=evidence)


def test_missing_exact_head_fails_closed(tmp_path: Path) -> None:
    repo, head = _repo(tmp_path, GOOD)
    head = "0" * 40
    manifest = tmp_path / "manifest.json"
    evidence = tmp_path / "evidence.json"
    manifest.write_text("{}", encoding="utf-8")
    evidence.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="git cat-file"):
        verify(repo, head, manifest_path=manifest, evidence_path=evidence)


def _sealed_evidence(repo: Path, head: str, tmp_path: Path) -> tuple[Path, Path]:
    blob = subprocess.check_output([
        "git",
        "-C",
        str(repo),
        "show",
        f"{head}:tests/golden_behavior/corpus.py",
    ])
    tree = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", f"{head}^{{tree}}"], text=True
    ).strip()
    evaluator_sha = "a" * 64
    report = {
        "schema": "nexus.golden_behavior_eval.v1",
        "source_revision": head,
        "source_tree": tree,
        "corpus_identity": hashlib.sha256(blob).hexdigest(),
        "evaluator_identity": evaluator_sha,
        "root_binding_mode": "explicit_sha_bound",
        "case_evidence": [
            {"case_id": "GB-001", "status": "covered"},
            {"case_id": "GB-002", "status": "covered"},
        ],
    }
    sealed = json.dumps(report, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    manifest = tmp_path / "manifest.json"
    evidence = tmp_path / "evidence.json"
    manifest.write_text(
        json.dumps({"head_sha": head, "head_tree": tree, "golden_evaluator_sha256": evaluator_sha}),
        encoding="utf-8",
    )
    evidence.write_text(
        json.dumps({
            "golden_report": report,
            "golden_report_sha256": hashlib.sha256(sealed).hexdigest(),
            "golden_evaluator_sha256": evaluator_sha,
        }),
        encoding="utf-8",
    )
    return manifest, evidence


def test_sealed_exact_canonical_report_passes(tmp_path: Path) -> None:
    repo, head = _repo(tmp_path, GOOD)
    manifest, evidence = _sealed_evidence(repo, head, tmp_path)
    report = verify(repo, head, manifest_path=manifest, evidence_path=evidence)
    assert report["status"] == "PASS"
    assert report["sealed_report_sha256"] is not None


@pytest.mark.parametrize(
    ("target", "mutation"),
    [
        ("manifest", lambda value: value.__setitem__("head_sha", "b" * 40)),
        (
            "evidence",
            lambda value: value["golden_report"].__setitem__("schema", "untrusted.v0"),
        ),
        (
            "evidence",
            lambda value: value["golden_report"].__setitem__("case_evidence", [123, 456]),
        ),
    ],
)
def test_sealed_manifest_schema_and_case_rows_fail_closed(
    tmp_path: Path, target: str, mutation: object
) -> None:
    repo, head = _repo(tmp_path, GOOD)
    manifest, evidence = _sealed_evidence(repo, head, tmp_path)
    path = manifest if target == "manifest" else evidence
    value = json.loads(path.read_text(encoding="utf-8"))
    assert callable(mutation)
    mutation(value)
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="sealed Golden evidence"):
        verify(repo, head, manifest_path=manifest, evidence_path=evidence)


def test_manifest_and_evidence_must_be_supplied_together(tmp_path: Path) -> None:
    repo, head = _repo(tmp_path, GOOD)
    manifest, _ = _sealed_evidence(repo, head, tmp_path)
    with pytest.raises(ValueError, match="must be supplied together"):
        verify(repo, head, manifest_path=manifest)
