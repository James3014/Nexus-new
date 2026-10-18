"""agy provider for the same-model A/B lane (issue #1820), exercised with a fake agy executable.

Since #1932 every call is leased from the Agy account pool; ``agy_pool`` (conftest.py) supplies a
temp pool, leases dir and quota snapshot so these tests never touch the real pool.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from nexus.engine.sandboxed_lane import os_sandbox_available
from scripts.bench.agy_provider import (
    AGY_DEFAULT_MODEL,
    AGY_NO_TOOLS_PREFIX,
    agy_model,
    ask_direct_agy_patch,
    configure_agy_lane_env,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _assert_excluded_without_os_barrier(res: dict) -> None:
    """The counted lane confines the visible test (#2211). With no OS barrier (Seatbelt is
    macOS-only, so Linux CI) the task is excluded for both arms before any model call (fail closed)."""
    row = res["row"]
    assert row["status"] == "NOT_RUN"
    assert row["not_run_reason"] == "confinement_parity_failed"
    assert row["confinement_parity_detail"] == "visible:confinement_unavailable"
    assert row["model_calls"] == 0
    assert row["run_eligible"] is False
    assert res["summary"]["eligible_n"] == 0
    assert res["summary"]["solved_n"] == 0


VALUE_FIXTURE = REPO_ROOT / "scripts" / "bench" / "public_benchmark_nexus_value_v1.json"


def test_default_model_is_the_agy_listed_gemini_3_8_flash_id():
    assert AGY_DEFAULT_MODEL == "gemini-3.8-flash-medium"
    assert agy_model({}) == AGY_DEFAULT_MODEL
    assert agy_model({"NEXUS_AGY_MODEL": "gemini-3.8-flash-high"}) == "gemini-3.8-flash-high"


def test_ask_parses_patch_tokens_and_uses_contained_invocation(agy_pool):
    agy_pool.set_behaviour('```json\n{"status": "ok", "patch": "x = 1\\n"}\n```')
    out, raw = ask_direct_agy_patch(prompt="fix it", timeout_sec=30, env=agy_pool.env())
    assert out["patch"] == "x = 1\n"
    assert out["model_name"] == AGY_DEFAULT_MODEL
    assert out["tokens_used"] == 1000
    assert out["token_capture_status"] == "measured"
    assert out["gateway_token_source"] == "usage_metadata"
    assert out["model_patch_generated"] is True
    assert out["gateway_process_sec"] >= 0
    assert "error_category" not in out
    argv = agy_pool.calls()[0]["argv"]
    assert argv[argv.index("--model") + 1] == AGY_DEFAULT_MODEL
    assert argv[argv.index("--mode") + 1] == "plan"
    assert "--sandbox" in argv
    assert "--new-project" in argv
    assert "--dangerously-skip-permissions" not in argv
    assert argv[argv.index("--print") + 1] == AGY_NO_TOOLS_PREFIX + "fix it"
    assert out["agy_no_tools_prefix_applied"] is True


def test_missing_agy_fails_closed_without_a_model_call():
    out, raw = ask_direct_agy_patch(
        prompt="p", timeout_sec=5, env={"NEXUS_AGY_BIN": "/nonexistent/agy"}
    )
    assert out["error_category"] == "agy_missing"
    assert raw == "agy_missing"


def test_cli_error_and_parse_failure_are_distinct(agy_pool):
    agy_pool.set_behaviour("", default="fail")
    out, raw = ask_direct_agy_patch(prompt="p", timeout_sec=5, env=agy_pool.env())
    assert out["error_category"] == "cli_error"
    assert "boom" in raw
    agy_pool.set_behaviour("not json at all")
    out2, _ = ask_direct_agy_patch(prompt="p", timeout_sec=5, env=agy_pool.env())
    assert out2["error_category"] == "parse_failure"
    # The model was billed for the unparsable answer: tokens stay measured so it is a model failure.
    assert out2["tokens_used"] == 1000
    assert out2["token_capture_status"] == "measured"


def test_timeout_is_reported_as_timeout(agy_pool):
    def runner(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="agy", timeout=5)

    out, _ = ask_direct_agy_patch(prompt="p", timeout_sec=5, env=agy_pool.env(), runner=runner)
    assert out["error_category"] == "timeout"


def test_configure_lane_env_pins_one_model_for_both_arms():
    env: dict[str, str] = {"NEXUS_AGY_MODEL": "gemini-3.8-flash-low"}
    assert configure_agy_lane_env(env) == "gemini-3.8-flash-low"
    assert (
        env["NEXUS_GEMINI_MODEL_NAME"] == env["NEXUS_DIRECT_GEMINI_MODEL"] == "gemini-3.8-flash-low"
    )


def _run_bare_arm(tmp_path: Path, agy_bin: str, pool_env: dict[str, str]) -> dict:
    env = {
        **os.environ,
        **pool_env,
        "HOME": str(tmp_path / "isolated_home"),
        "NEXUS_AGY_BIN": agy_bin,
        "NEXUS_VALUE_HIDDEN_VERIFIER": "1",
        "NEXUS_BENCH_SUBPROCESS_PYTHON": sys.executable,
        "PYTHONPATH": str(REPO_ROOT),
    }
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "bench" / "capability_ab_runner.py"),
            "--tasks-file",
            str(VALUE_FIXTURE),
            "--output-dir",
            str(tmp_path / "out"),
            "--max-tasks",
            "1",
            "--repeat-trials",
            "1",
            "--without-only",
            "--without-mode",
            "agy",
            "--require-same-model-baseline",
            "--strict-llm-baseline",
            # The counted lane validates one per-call cap for both arms (task budget - 30 s > 5 s).
            "--timeout-sec",
            "120",
            "--difficulty",
            "all",
            "--repo-kind-filter",
            "all",
            "--materialize-missing",
            "--isolation-mode",
            "preserve_target",
            "--neutralize-history",
            "--disable-learning-loop",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    summary = json.loads(proc.stdout.strip().splitlines()[-1])
    row = json.loads(Path(summary["without_nexus_file"]).read_text().splitlines()[0])
    return {"summary": summary["benchmark_summary"]["without_nexus"], "row": row}


def test_lane_bare_arm_with_agy_missing_is_infra_invalid_agy_missing(tmp_path: Path, agy_pool):
    res = _run_bare_arm(tmp_path, "/nonexistent/agy", agy_pool.env())
    if not os_sandbox_available():
        return _assert_excluded_without_os_barrier(res)
    assert res["row"]["model_calls"] == 0
    assert res["row"]["run_eligible"] is False
    assert res["row"]["infra_invalid_reason"] == "agy_missing"
    assert res["summary"]["eligible_n"] == 0
    assert res["summary"]["solved_n"] == 0


def test_lane_bare_arm_counts_one_model_call_and_no_rescue(tmp_path: Path, agy_pool):
    agy_pool.set_behaviour('{"status": "ok", "patch": "unchanged = True\\n"}')
    res = _run_bare_arm(tmp_path, str(agy_pool.exe), agy_pool.env())
    if not os_sandbox_available():
        assert agy_pool.calls() == []
        return _assert_excluded_without_os_barrier(res)
    row = res["row"]
    assert row["model_calls"] == 1
    assert row["model_name"] == AGY_DEFAULT_MODEL
    assert row["total_tokens"] == 1000
    assert row["solve_classification"] == "not_solved"
    assert row["deterministic_rescue"] is False
    assert res["summary"]["deterministic_rescue_n"] == 0
    assert res["summary"]["solved_n"] == 0


def test_lane_bare_arm_without_an_eligible_account_makes_no_model_call(tmp_path: Path, agy_pool):
    res = _run_bare_arm(
        tmp_path, str(agy_pool.exe), agy_pool.env(NEXUS_AGY_ACCOUNT_ALLOWLIST="acc-none")
    )
    assert agy_pool.calls() == []
    if not os_sandbox_available():
        return _assert_excluded_without_os_barrier(res)
    assert res["row"]["model_calls"] == 0
    assert res["row"]["run_eligible"] is False
    assert res["row"]["infra_invalid_reason"] == "agy_no_eligible_account"


def test_resolve_agy_bin_fallback_uses_home_not_a_user_name(monkeypatch, tmp_path: Path):
    from scripts.bench.agy_provider import resolve_agy_bin

    home = tmp_path / "home"
    fake_agy = home / ".local" / "bin" / "agy"
    fake_agy.parent.mkdir(parents=True, exist_ok=True)
    fake_agy.write_text("")
    fake_agy.chmod(0o755)

    empty = tmp_path / "empty"
    empty.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("HOME", str(home))
    assert resolve_agy_bin({"PATH": str(empty)}) == str(fake_agy)
