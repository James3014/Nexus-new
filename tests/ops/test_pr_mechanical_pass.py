from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ops import pr_mechanical_pass as mp
from scripts.ops.pr_impact_gate import (
    WRITTEN_ROW_RISK_REASON,
    propose_impact_rows,
    propose_impact_targets,
    write_impact_rows,
    write_missing_impact_rows,
)
from scripts.ops.select_tests import load_impact_rules, select_target_details

LEGACY = 'import sys\nimport os\n\nA  =  1\n\n\ndef keep( x ):\n    return x\n\n\nB = {"a":1}\n'


def _ruff() -> str:
    for candidate in (Path(sys.executable).parent / "ruff", shutil.which("ruff")):
        if candidate and Path(candidate).is_file():
            return str(candidate)
    if os.environ.get("CI"):
        pytest.fail("ruff must be installed in CI")
    pytest.skip("ruff not installed")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, text=True, capture_output=True
    ).stdout


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "t")
    _git(repo, "config", "user.email", "t@example.invalid")
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    _git(repo, "branch", "base")
    return repo


def _pass(repo: Path, *, check_only: bool = False) -> mp.PassReport:
    return mp.run_pass(repo, base_ref="base", ruff=_ruff(), skip_impact=True, check_only=check_only)


def test_changed_line_ranges_merges_adjacent_and_drops_pure_deletions() -> None:
    old = "a\nb\nc\nd\ne\n"
    new = "a\nB\nC\nd\nx\n"
    assert mp.changed_line_ranges(old, new) == [(2, 3), (5, 5)]
    assert mp.changed_line_ranges(old, "a\nb\nd\ne\n") == []


def test_formats_only_changed_hunk_of_a_legacy_file_and_is_idempotent(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"pkg/legacy.py": LEGACY})
    edited = LEGACY + "\n\ndef added( y ):\n    return  y\n"
    (repo / "pkg/legacy.py").write_text(edited, encoding="utf-8")

    report = _pass(repo)

    text = (repo / "pkg/legacy.py").read_text(encoding="utf-8")
    assert report.formatted == {"pkg/legacy.py": 1}
    assert "def added(y):\n    return y\n" in text
    # Legacy debt outside the PR's hunk is untouched, imports included.
    assert text.startswith("import sys\nimport os\n\nA  =  1\n\n\ndef keep( x ):")
    assert 'B = {"a":1}' in text
    assert report.imports_sorted == []

    again = _pass(repo)
    assert not again.changed
    assert (repo / "pkg/legacy.py").read_text(encoding="utf-8") == text


def test_new_file_is_formatted_whole_and_imports_sorted(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"pkg/legacy.py": LEGACY})
    (repo / "pkg/new.py").write_text("import sys\nimport os\nX={'a':1}\n", encoding="utf-8")

    report = _pass(repo)

    assert report.imports_sorted == ["pkg/new.py"]
    assert report.formatted == {"pkg/new.py": 1}
    assert (repo / "pkg/new.py").read_text(encoding="utf-8") == (
        'import os\nimport sys\n\nX = {"a": 1}\n'
    )
    assert (repo / "pkg/legacy.py").read_text(encoding="utf-8") == LEGACY


def test_imports_sorted_when_the_import_block_is_touched(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"pkg/legacy.py": LEGACY})
    edited = LEGACY.replace("import os\n", "import os\nimport json\n", 1)
    (repo / "pkg/legacy.py").write_text(edited, encoding="utf-8")

    report = _pass(repo)

    text = (repo / "pkg/legacy.py").read_text(encoding="utf-8")
    assert report.imports_sorted == ["pkg/legacy.py"]
    assert text.startswith("import json\nimport os\nimport sys\n")
    assert "A  =  1" in text  # outside the hunk


def test_check_mode_writes_nothing(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"pkg/legacy.py": LEGACY})
    (repo / "pkg/new.py").write_text("X={'a':1}\n", encoding="utf-8")

    report = _pass(repo, check_only=True)

    assert report.formatted == {"pkg/new.py": 1}
    assert (repo / "pkg/new.py").read_text(encoding="utf-8") == "X={'a':1}\n"
    assert mp.main(["--repo", str(repo), "--base-ref", "base", "--ruff", _ruff(),
                    "--skip-impact", "--check"]) == 1  # fmt: skip


def test_syntax_error_is_reported_not_written(tmp_path: Path) -> None:
    repo = _repo(tmp_path, {"pkg/legacy.py": LEGACY})
    (repo / "pkg/broken.py").write_text("def f(:\n", encoding="utf-8")

    report = _pass(repo)

    assert report.errors and report.needs_attention
    assert (repo / "pkg/broken.py").read_text(encoding="utf-8") == "def f(:\n"


def _impact_root(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    files = {
        "nexus/alpha.py": "X = 1\n",
        "tests/a/test_alpha.py": "from nexus.alpha import X\n",
        "tests/b/test_uses_alpha.py": "import nexus.alpha\n",
        "tests/c/test_mentions.py": "PATH = 'nexus/alpha.py'\n",
        "tests/d/test_unrelated.py": "import nexus.alphabet\n",
        "tests/e/test_beta.py": "def test_beta():\n    pass\n",
        "tests/f/test_utils.py": "",
        "tests/g/test_utils.py": "",
        "docs/testing/test_impact_map.md": (
            "| 程式碼路徑 | 測試集合 | 狀態 | 風險 | 風險原因 |\n"
            "| :--- | :--- | :--- | :--- | :--- |\n"
            "| nexus/old.py | tests/e/test_beta.py | active | low | x |"
        ),
    }
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    return root


def test_proposed_targets_rank_named_then_imported_then_referenced(tmp_path: Path) -> None:
    root = _impact_root(tmp_path)

    assert propose_impact_targets("nexus/alpha.py", root=root) == [
        "tests/a/test_alpha.py",
        "tests/b/test_uses_alpha.py",
        "tests/c/test_mentions.py",
    ]
    # A unique same-named test is accepted alone; an ambiguous name is not.
    assert propose_impact_targets("scripts/beta.py", root=root) == ["tests/e/test_beta.py"]
    assert propose_impact_targets("nexus/x/utils.py", root=root) == []


def test_written_rows_match_in_the_selector_and_are_not_duplicated(tmp_path: Path) -> None:
    root = _impact_root(tmp_path)
    map_path = root / "docs/testing/test_impact_map.md"

    proposal = write_missing_impact_rows(["nexus/alpha.py", "nexus/orphan.py"], root=root)

    assert proposal.unresolved == ["nexus/orphan.py"]
    assert proposal.rows == [
        "| nexus/alpha.py | tests/a/test_alpha.py, tests/b/test_uses_alpha.py, "
        f"tests/c/test_mentions.py | active | medium | {WRITTEN_ROW_RISK_REASON} |"
    ]
    text = map_path.read_text(encoding="utf-8")
    assert "| x |\n| nexus/alpha.py |" in text  # newline restored before appending
    details = select_target_details(
        ["nexus/alpha.py"],
        load_impact_rules(map_path),
        fallback_targets=(),
        index_path=tmp_path / "none.json",
    )
    assert details.unmatched_paths == []
    assert "tests/a/test_alpha.py" in details.targets

    assert write_missing_impact_rows(["nexus/alpha.py"], root=root).rows == []
    assert write_impact_rows(propose_impact_rows(["nexus/old.py"], root=root).rows,
                             map_path=map_path) == []  # fmt: skip
    assert map_path.read_text(encoding="utf-8") == text


def test_impact_step_uses_the_planner_unmatched_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.ops import pr_impact_gate as gate

    root = _impact_root(tmp_path)
    seen: list[list[str]] = []

    class _Plan:
        unmatched_paths = ["nexus/alpha.py"]

    def fake_plan(paths: list[str], **_: object) -> _Plan:
        seen.append(paths)
        return _Plan()

    monkeypatch.setattr(gate, "build_impact_plan", fake_plan)
    report = mp.PassReport(base_sha="0" * 40, check_only=True)
    mp.impact_step(root, ["nexus/alpha.py", "tests/a/test_alpha.py"], report)

    assert seen == [["nexus/alpha.py", "tests/a/test_alpha.py"]]
    assert report.impact_rows == {
        "nexus/alpha.py": [
            "tests/a/test_alpha.py",
            "tests/b/test_uses_alpha.py",
            "tests/c/test_mentions.py",
        ]
    }
    assert "nexus/alpha.py" not in (root / "docs/testing/test_impact_map.md").read_text(
        encoding="utf-8"
    )


def test_bindings_step_reuses_preflight_only_bindings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        out = "nexus-pr-preflight  base=x  head=y\nFAIL  bindings: missing Closes\nRESULT: FAIL\n"
        return subprocess.CompletedProcess(cmd, 1, out, "")

    monkeypatch.setattr(mp.subprocess, "run", fake_run)
    report = mp.PassReport(base_sha="0" * 40, check_only=False)
    mp.bindings_step(tmp_path, "origin/main", tmp_path / "body.md", report)

    assert calls[0][1].endswith("scripts/ops/pr_preflight.py")
    assert calls[0][calls[0].index("--only") + 1] == "bindings"
    assert calls[0][calls[0].index("--body-file") + 1] == str(tmp_path / "body.md")
    assert report.bindings == "FAIL"
    assert report.bindings_detail == ["FAIL  bindings: missing Closes"]
    assert report.needs_attention


def test_plan_write_rows_cli_appends_rows_for_unmatched_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from scripts.ops import pr_impact_gate as gate

    root = _impact_root(tmp_path)
    plan = gate.ImpactPlan(
        base_sha="a" * 40,
        head_sha="b" * 40,
        changed_paths=["nexus/alpha.py", "nexus/orphan.py"],
        tier=3,
        impact_class=gate.FULL_SUITE_IMPACT_CLASS,
        confidence=0.4,
        pytest_targets=["tests"],
        pytest_required=True,
        wiki_required=False,
        workflow_validation_required=False,
        changed_python_paths=["nexus/alpha.py", "nexus/orphan.py"],
        reasons=[],
        unmatched_paths=["nexus/alpha.py", "nexus/orphan.py"],
    )
    monkeypatch.setattr(gate, "ROOT", root)
    monkeypatch.setattr(gate, "_git_changed_paths", lambda *a, **k: plan.changed_paths)
    monkeypatch.setattr(gate, "build_impact_plan", lambda *a, **k: plan)
    out = tmp_path / "plan.json"
    argv = ["plan", "--base-sha", "a" * 40, "--head-sha", "b" * 40, "--output", str(out)]

    assert gate.main([*argv, "--write-rows"]) == 0

    map_path = root / "docs/testing/test_impact_map.md"
    text = map_path.read_text(encoding="utf-8")
    assert "| nexus/alpha.py | tests/a/test_alpha.py" in text
    assert "nexus/orphan.py" not in text
    err = capsys.readouterr().err
    assert "impact-map row written: | nexus/alpha.py" in err
    assert "NOT written for nexus/orphan.py" in err
    # Without the flag the planner never touches the map.
    assert gate.main(argv) == 0
    assert map_path.read_text(encoding="utf-8") == text
