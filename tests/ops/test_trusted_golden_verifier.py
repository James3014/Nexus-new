from __future__ import annotations

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


def test_exact_valid_head_passes(tmp_path: Path) -> None:
    repo, head = _repo(tmp_path, GOOD)
    report = verify(repo, head)
    assert report["status"] == "PASS"
    assert report["trusted_source"] == "default-branch-verifier"
    assert report["head_sha"] == head
    assert report["case_count"] == 2


def test_invalid_duplicate_corpus_fails_closed(tmp_path: Path) -> None:
    repo, head = _repo(tmp_path, GOOD.replace('"GB-002"', '"GB-001"'))
    with pytest.raises(ValueError, match="duplicate_case_id: GB-001"):
        verify(repo, head)


def test_single_case_ast_false_green_fails_closed(tmp_path: Path) -> None:
    repo, head = _repo(tmp_path, GOOD.split('    _c("GB-002"')[0] + ")\n")
    with pytest.raises(ValueError, match="too few case ids"):
        verify(repo, head)


def test_fake_same_name_evidence_cannot_produce_trusted_pass(tmp_path: Path) -> None:
    repo, head = _repo(tmp_path, GOOD)
    fake = tmp_path / "fake-same-name-report.json"
    fake.write_text(
        '{"name":"Trusted verifier (default branch)","conclusion":"success"}\n', encoding="utf-8"
    )
    report = verify(repo, head)
    assert report["status"] == "PASS"
    assert report["trusted_source"] == "default-branch-verifier"
    assert "fake-same-name-report" not in report


def test_missing_exact_head_fails_closed(tmp_path: Path) -> None:
    repo, _ = _repo(tmp_path, GOOD)
    with pytest.raises(ValueError, match="git cat-file"):
        verify(repo, "0" * 40)
