"""Counted-run start-up precheck: a bench path carrying a task's hidden-only text is refused.

nexus-runtime renders the resolved run root into [NEXUS MODEL CONTEXT]; a hidden-only word in
that path (e.g. "main" for hard_v1 oabh-remote) made the prompt audit void a whole counted run.
"""

from __future__ import annotations

from pathlib import Path

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


def test_path_with_a_hidden_only_word_is_reported() -> None:
    hits = bench_path_hidden_hits(["/bench/zebrafish-run/nn"], [MATERIAL])
    assert hits and "zebrafish" in hits[0] and hits[0].startswith("demo:")


def test_clean_path_and_words_the_bare_arm_sees_are_not_reported() -> None:
    # "test" and "return" are in the visible material: never hidden-only.
    assert bench_path_hidden_hits(["/bench/test-return/nn", "/srv/runs/x1"], [MATERIAL]) == []


def test_runner_precheck_uses_the_real_fixtures(tmp_path: Path) -> None:
    task = next(t for t in P16 if t.id == "nexus-value-hidden-001")
    clean = _bench_path_hidden_hits([task], tmp_path, tmp_path / "out", materialize_missing=True)
    assert clean == []
    target = tmp_path / ".nexus" / "bench_cases" / task.id / "target.py"
    visible = target.with_name("test_visible.py")
    material = psa.TaskMaterial(
        task_id=task.id,
        visible_test=visible.read_text(encoding="utf-8"),
        hidden_test=target.with_name("test_hidden.py").read_text(encoding="utf-8"),
        source=target.read_text(encoding="utf-8"),
        task_desc=task.task_desc,
    )
    words = sorted(psa.hidden_only_words(material, psa.synthetic_bare_reference(material)))
    assert words, "fixture has hidden-only vocabulary"
    hits = _bench_path_hidden_hits(
        [task], tmp_path, tmp_path / f"run-{words[0]}", materialize_missing=True
    )
    assert any(f"{words[0]!r}" in hit for hit in hits), hits


@pytest.fixture
def _restore_environ():
    """runner.main() writes os.environ before its argument checks; restore it afterwards."""

    import os

    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)


def test_counted_runner_refuses_to_start_on_a_hidden_word_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    _restore_environ: None,
) -> None:
    import sys

    from scripts.bench import capability_ab_runner as runner

    monkeypatch.setattr(runner, "_counted_mode_expects_model_calls", lambda _args: True)
    monkeypatch.setattr(
        runner,
        "_bench_path_hidden_hits",
        lambda *_a, **_k: ["oabh-remote: /bench/proof-main contains hidden-only word 'main'"],
    )
    monkeypatch.setattr(runner, "_missing_hidden_tests", lambda *_a, **_k: [])
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capability_ab_runner.py",
            "--tasks-file",
            str(REPO_ROOT / "scripts" / "bench" / "public_benchmark_nexus_value_v1.json"),
            "--output-dir",
            str(tmp_path / "out"),
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
        ],
    )
    with pytest.raises(SystemExit) as exc:
        runner.main()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "counted run refused" in err and "hidden-only word 'main'" in err
