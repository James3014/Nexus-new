"""Benchmark CI runs only on demand and skips explicitly when it cannot run (#2964)."""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "benchmark-ci.yml"
GATE = "steps.prereq.outputs.runnable == 'true'"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _steps() -> list[dict]:
    return _workflow()["jobs"]["benchmark"]["steps"]


def test_benchmark_ci_has_no_schedule_only_manual_dispatch():
    triggers = _workflow()[True]  # YAML 1.1 reads the ``on`` key as True
    assert set(triggers) == {"workflow_dispatch"}


def test_benchmark_ci_checks_prerequisites_before_any_setup():
    steps = _steps()
    names = [step["name"] for step in steps]
    prereq = names.index("Check Benchmark Prerequisites")
    assert names[:prereq] == ["Checkout Repository", "Remove checkout credentials"]
    script = steps[prereq]["run"]
    for needed in ("GEMINI_API_KEY", "OPENAI_API_KEY", "nexus_benchmark.sh"):
        assert needed in script
    assert 'echo "runnable=false" >> "$GITHUB_OUTPUT"' in script
    # A missing prerequisite is a green skip, never a red run.
    assert "exit 1" not in script and "::error::" not in script
    # Only key presence reaches this step, never the secret values.
    env = steps[prereq]["env"]
    assert all(value.endswith("!= '' }}") for value in env.values())


def test_benchmark_ci_gates_every_later_step_on_the_prerequisites():
    steps = _steps()
    prereq = [step["name"] for step in steps].index("Check Benchmark Prerequisites")
    for step in steps[prereq + 1 :]:
        assert GATE in str(step.get("if", "")), step["name"]
    assert steps[-1]["if"] == f"always() && {GATE}"


def test_benchmark_ci_uses_secret_values_only_in_the_benchmark_step():
    for step in _steps():
        text = yaml.safe_dump(step)
        if step["name"] == "Execute Benchmark Subset":
            continue
        if step["name"] == "Check Benchmark Prerequisites":
            # Presence booleans only: no secret value.
            assert all(value.endswith("!= '' }}") for value in step["env"].values())
            continue
        assert "secrets." not in text, step["name"]
