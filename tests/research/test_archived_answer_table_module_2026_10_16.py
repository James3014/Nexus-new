"""Guard for the deleted local answer table (#2339 follow-up, Owner decision 2026-10-16).

``nexus/research/local_sprint_mutator.py`` held deterministic patches keyed on benchmark
fixture names. It is deleted along with every route into it: sprint fallbacks, the baseline
local patch, companion edits, the nightshift bundle shortcut and the bench local arms. These
tests fail if the module or a reference to it comes back, in any form (re-added file, import,
``importlib`` string, JSON/text config). Without a model, Nexus reports
``no_local_candidate_generator`` and never fabricates a patch.
"""

from __future__ import annotations

import importlib
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE = "nexus.research.local_sprint_mutator"
STEM = "local_sprint_mutator"
SCANNED_DIRS = ("nexus", "scripts")
SCANNED_SUFFIXES = {".py", ".json", ".txt", ".toml", ".yaml", ".yml", ".cfg", ".ini"}
FORBIDDEN = re.compile(
    r"local_sprint_mutator"
    r"|\bgenerate_local_candidate\b"
    r"|\bgenerate_local_companion_edits\b"
    r"|\bgenerate_nightshift_bundle_edits\b"
    r"|\bLocalCandidateGenerator\b"
    r"|\bnightshift_bundle_repair\b"
)


def _scanned_files() -> list[Path]:
    files: list[Path] = []
    for top in SCANNED_DIRS:
        for path in (ROOT / top).rglob("*"):
            if (
                path.is_file()
                and path.suffix in SCANNED_SUFFIXES
                and "__pycache__" not in path.parts
            ):
                files.append(path)
    return files


def test_answer_table_module_is_not_importable() -> None:
    assert importlib.util.find_spec(MODULE) is None
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(MODULE)


def test_no_answer_table_file_is_re_added_under_any_suffix() -> None:
    re_added = sorted(
        path.relative_to(ROOT).as_posix()
        for top in SCANNED_DIRS
        for path in (ROOT / top).rglob(f"{STEM}*")
        if "__pycache__" not in path.parts
    )
    assert re_added == []


def test_no_reference_to_the_answer_table_under_nexus_or_scripts() -> None:
    hits: list[str] = []
    for path in _scanned_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for number, line in enumerate(text.splitlines(), start=1):
            if FORBIDDEN.search(line):
                hits.append(f"{path.relative_to(ROOT).as_posix()}:{number}: {line.strip()[:120]}")
    assert hits == []


def test_forbidden_pattern_catches_importlib_strings_and_config_re_adds() -> None:
    samples = (
        'importlib.import_module("nexus.research.local_sprint_mutator")',
        '{"module": "nexus.research.local_sprint_mutator"}',
        "candidate = generate_local_candidate(source, task, 'local', 0)",
        "from x import generate_local_companion_edits",
        "LocalCandidateGenerator()",
    )
    assert all(FORBIDDEN.search(sample) for sample in samples)
    # An unrelated Ollama-backed generator name stays allowed.
    assert not FORBIDDEN.search('"candidate_generate_fn": "generate_local_candidate_by_ollama"')


def test_sprint_without_a_model_reports_no_local_candidate_generator(tmp_path: Path) -> None:
    from nexus.research.sprint_service import SprintConfig, run_hyper_sprint

    original = "def value():\n    return 1\n"
    (tmp_path / "demo.py").write_text(original, encoding="utf-8")
    res = run_hyper_sprint(
        repo_root=tmp_path,
        config=SprintConfig(
            task="fix value", target_file="demo.py", candidate_count=2, llm_mode=False
        ),
    )

    assert res.status == "FAILED"
    assert res.reason == "no_local_candidate_generator"
    assert res.winner_source == "no_local_candidate_generator"
    assert res.attempt_count == 0 and res.model_calls == 0
    assert not res.patch
    assert (tmp_path / "demo.py").read_text(encoding="utf-8") == original


def test_baseline_without_a_model_reports_no_local_candidate_generator(tmp_path: Path) -> None:
    from nexus.app import research_flow_service

    original = "def value():\n    return 1\n"
    patched, source, meta = research_flow_service._build_baseline_patch(
        trial=0,
        original_code=original,
        task_desc="fix value",
        route={},
        llm_baseline_required=False,
        llm_baseline=False,
        task_desc_with_codeintel="fix value",
        repo_root=tmp_path,
        task_type="feature",
    )

    assert patched == original
    assert source == "no_local_candidate_generator"
    assert meta["model_calls"] == 0 and meta["model_patch_generated"] is False


def test_bench_deterministic_rescue_helpers_never_produce_a_candidate(tmp_path: Path) -> None:
    from scripts.bench import capability_ab_runner as runner

    target = tmp_path / "target.py"
    target.write_text("def value():\n    return 1\n", encoding="utf-8")
    rescue = runner._deterministic_failed_tests_pre_rescue(
        task=None,
        repo_root=tmp_path,
        target_file=str(target),
        test_file="test_target.py",
        timeout_sec=5,
    )
    retry = runner._deterministic_hidden_pre_retry(
        task=None,
        repo_root=tmp_path,
        target_file=str(target),
        verification_test_file="test_target.py",
        failure_tail="E   assert 1 == 2",
        decision=None,
        timeout_sec=5,
    )

    assert rescue == {"used": False, "reason": "no_local_candidate_generator"}
    assert retry == {"used": False, "reason": "no_local_candidate_generator"}
    assert target.read_text(encoding="utf-8") == "def value():\n    return 1\n"
