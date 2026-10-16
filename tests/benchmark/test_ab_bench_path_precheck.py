"""Counted-run start-up precheck: a bench path the prompt audit would reject is refused.

nexus-runtime renders the resolved run root into [NEXUS MODEL CONTEXT]; a hidden-only word in
that path (e.g. "main" for hard_v1 oabh-remote), a non-plain path or one longer than the audit's
string limit made the prompt audit void a whole counted run after the paid calls.
"""

from __future__ import annotations

import dataclasses
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from scripts.bench import prompt_symmetry_audit as psa
from scripts.bench.bench_path_precheck import bench_path_hidden_hits
from scripts.bench.capability_ab_runner import _bench_path_hidden_hits, load_tasks

REPO_ROOT = Path(__file__).resolve().parents[2]
P16 = load_tasks(REPO_ROOT / "scripts" / "bench" / "public_benchmark_nexus_value_v1.json")

MATERIAL = psa.TaskMaterial(
    task_id="demo",
    visible_test="def test_v():\n    assert f(1) == 1\n",
    hidden_test="def test_h():\n    assert f('zebrafish') == 'zebrafish'\n",
    source="def f(x):\n    return x\n",
    task_desc="Make f return its input.",
)


@pytest.fixture
def short_root() -> Any:
    """A short real directory (pytest tmp paths exceed the audit's 120-char string limit)."""

    with tempfile.TemporaryDirectory(dir="/tmp", prefix="bp") as name:
        yield Path(name)


def _material(root: Path, task: Any) -> psa.TaskMaterial:
    target = root / ".nexus" / "bench_cases" / task.id / "target.py"
    return psa.TaskMaterial(
        task_id=task.id,
        visible_test=target.with_name("test_visible.py").read_text(encoding="utf-8"),
        hidden_test=target.with_name("test_hidden.py").read_text(encoding="utf-8"),
        source=target.read_text(encoding="utf-8"),
        task_desc=task.task_desc,
    )


def _hidden_word(root: Path, task: Any) -> str:
    material = _material(root, task)
    words = sorted(psa.hidden_only_words(material, psa.synthetic_bare_reference(material)))
    assert words, "fixture has hidden-only vocabulary"
    return words[0]


def test_path_with_a_hidden_only_word_is_reported() -> None:
    hits = bench_path_hidden_hits(["/bench/zebrafish-run/nn"], [MATERIAL])
    assert hits and "zebrafish" in hits[0] and hits[0].startswith("demo:")


def test_clean_path_and_words_the_bare_arm_sees_are_not_reported() -> None:
    # "test" and "return" are in the visible material: never hidden-only.
    assert bench_path_hidden_hits(["/bench/test-return/nn", "/srv/runs/x1"], [MATERIAL]) == []


@pytest.mark.parametrize(
    "path",
    ["/tmp/My Projects/bench", "/opt/py@3/bench", "/tmp/café/bench", "/b/" + "x" * 130],
)
def test_rendered_path_failing_the_audit_format_or_length_is_reported(path: str) -> None:
    hits = bench_path_hidden_hits([], [MATERIAL], rendered=[path])
    assert hits and path in hits[0]


def test_percent_encoded_hidden_word_is_decoded_like_the_audit() -> None:
    encoded = "/bench/" + "".join(f"%{ord(c):02X}" for c in "zebrafish") + "/run"
    hits = bench_path_hidden_hits([encoded], [MATERIAL])
    assert any("'zebrafish' (decoded)" in hit for hit in hits), hits


def test_literal_and_line_hits_never_print_the_hidden_text() -> None:
    material = dataclasses.replace(
        MATERIAL, hidden_test="def test_h():\n    assert f('Qx9 secret,value') == 1\n"
    )
    hits = bench_path_hidden_hits(["/bench/qx9 secret,value/run"], [material])
    literal_hits = [hit for hit in hits if "hidden-only literal" in hit]
    assert literal_hits
    # Only the path (which the operator chose) and a length + sha256 prefix, never the literal.
    assert all(
        "qx9 secret,value" not in hit.split(" contains ", 1)[1].lower() for hit in literal_hits
    )
    assert all("sha256" in hit for hit in literal_hits)


def test_runner_precheck_uses_the_real_fixtures(short_root: Path) -> None:
    task = next(t for t in P16 if t.id == "nexus-value-hidden-001")
    clean = _bench_path_hidden_hits(
        [task], short_root, short_root / "out", materialize_missing=True
    )
    assert clean == []
    word = _hidden_word(short_root, task)
    hits = _bench_path_hidden_hits(
        [task], short_root, short_root / f"run-{word}", materialize_missing=True
    )
    assert any(f"{word!r}" in hit for hit in hits), hits


def test_task_id_with_a_hidden_word_is_caught_on_the_derived_run_root(short_root: Path) -> None:
    """The registry's default run root embeds the task id (``_resolve_run_root``)."""

    task = next(t for t in P16 if t.id == "nexus-value-hidden-001")
    _bench_path_hidden_hits([task], short_root, short_root / "out", materialize_missing=True)
    word = _hidden_word(short_root, task)
    renamed = dataclasses.replace(task, id=f"custom-{word}-01")
    case = short_root / ".nexus" / "bench_cases"
    os.rename(case / task.id, case / renamed.id)
    hits = _bench_path_hidden_hits(
        [renamed], short_root, short_root / "out", materialize_missing=True
    )
    assert any(".nexus/runtime/custom-" in hit and f"{word!r}" in hit for hit in hits), hits


def test_unreadable_fixture_is_reported_with_the_task_id(short_root: Path) -> None:
    task = next(t for t in P16 if t.id == "nexus-value-hidden-001")
    hits = _bench_path_hidden_hits(
        [task], short_root, short_root / "out", materialize_missing=False
    )
    assert hits and hits[0].startswith(f"{task.id}: fixture unreadable")


@pytest.fixture
def _restore_environ():
    """runner.main() writes os.environ before its argument checks; restore it afterwards."""

    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)


def _counted_argv(out_dir: Path) -> list[str]:
    return [
        "capability_ab_runner.py",
        "--tasks-file",
        str(REPO_ROOT / "scripts" / "bench" / "public_benchmark_nexus_value_v1.json"),
        "--output-dir",
        str(out_dir),
        "--max-tasks",
        "1",
        "--counted-first-attempt",
        "--strict-llm-baseline",
        "--require-same-model-baseline",
        "--no-hidden-feedback",
        "--no-nexus-task-hints",
        "--without-mode",
        "agy",
        "--with-llm-mode",
        "all",
        "--enable-hidden-verifier",
        "--materialize-missing",
        "--timeout-sec",
        "420",
        "--per-call-timeout-sec",
        "300",
        "--persistent-worker",
    ]


def test_counted_runner_refuses_to_start_on_a_hidden_word_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    _restore_environ: None,
) -> None:
    """Unpatched precheck inside main(); the refusal comes before any subprocess starts."""

    import subprocess

    from scripts.bench import capability_ab_runner as runner

    task = next(
        t
        for t in runner.load_tasks(REPO_ROOT / "scripts/bench/public_benchmark_nexus_value_v1.json")
    )
    _bench_path_hidden_hits([task], REPO_ROOT, tmp_path, materialize_missing=True)
    word = _hidden_word(REPO_ROOT, task)

    def no_subprocess(*_a: Any, **_k: Any) -> Any:
        raise AssertionError("a subprocess started before the path precheck")

    monkeypatch.setattr(subprocess, "Popen", no_subprocess)
    monkeypatch.setattr(runner, "_counted_mode_expects_model_calls", lambda _args: True)
    out_dir = Path(tempfile.mkdtemp(dir="/tmp", prefix="bp")) / f"run-{word}"
    monkeypatch.setattr(sys, "argv", _counted_argv(out_dir))
    with pytest.raises(SystemExit) as exc:
        runner.main()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "counted run refused" in err and f"{word!r}" in err
