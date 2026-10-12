"""agy provider for the same-model A/B lane (issue #1820), exercised with a fake agy executable."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

from scripts.bench.agy_provider import (
    AGY_DEFAULT_MODEL,
    agy_model,
    ask_direct_agy_patch,
    configure_agy_lane_env,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
VALUE_FIXTURE = REPO_ROOT / "scripts" / "bench" / "public_benchmark_nexus_value_v1.json"

FAKE_AGY = """#!{python}
import json, sys
argv = sys.argv[1:]
open({log!r}, "a").write(json.dumps(argv) + "\\n")
reply = {reply!r}
if reply == "__fail__":
    sys.stderr.write("boom")
    raise SystemExit(7)
print(json.dumps({{"conversation_id": "c1", "status": "SUCCESS", "response": reply,
                  "duration_seconds": 0.1, "num_turns": 1,
                  "usage": {{"input_tokens": 900, "output_tokens": 100, "total_tokens": 1000}}}}))
"""


def _fake_agy(tmp_path: Path, reply: str) -> tuple[Path, Path]:
    log = tmp_path / "argv.log"
    exe = tmp_path / "agy"
    exe.write_text(
        FAKE_AGY.format(python=sys.executable, log=str(log), reply=reply), encoding="utf-8"
    )
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
    return exe, log


def test_default_model_is_the_agy_listed_gemini_3_8_flash_id():
    assert AGY_DEFAULT_MODEL == "gemini-3.8-flash-medium"
    assert agy_model({}) == AGY_DEFAULT_MODEL
    assert agy_model({"NEXUS_AGY_MODEL": "gemini-3.8-flash-high"}) == "gemini-3.8-flash-high"


def test_ask_parses_patch_tokens_and_uses_contained_invocation(tmp_path: Path):
    exe, log = _fake_agy(tmp_path, '```json\n{"status": "ok", "patch": "x = 1\\n"}\n```')
    out, raw = ask_direct_agy_patch(
        prompt="fix it", timeout_sec=30, env={"NEXUS_AGY_BIN": str(exe), "PATH": os.environ["PATH"]}
    )
    assert out["patch"] == "x = 1\n"
    assert out["model_name"] == AGY_DEFAULT_MODEL
    assert out["tokens_used"] == 1000
    assert out["token_capture_status"] == "measured"
    assert out["gateway_token_source"] == "usage_metadata"
    assert out["model_patch_generated"] is True
    assert out["gateway_process_sec"] >= 0
    assert "error_category" not in out
    argv = json.loads(log.read_text().splitlines()[0])
    assert argv[argv.index("--model") + 1] == AGY_DEFAULT_MODEL
    assert argv[argv.index("--mode") + 1] == "plan"
    assert "--new-project" in argv
    assert "--dangerously-skip-permissions" not in argv
    assert argv[argv.index("--print") + 1] == "fix it"


def test_missing_agy_fails_closed_without_a_model_call():
    out, raw = ask_direct_agy_patch(
        prompt="p", timeout_sec=5, env={"NEXUS_AGY_BIN": "/nonexistent/agy"}
    )
    assert out["error_category"] == "agy_missing"
    assert raw == "agy_missing"


def test_cli_error_and_parse_failure_are_distinct(tmp_path: Path):
    exe, _ = _fake_agy(tmp_path, "__fail__")
    out, raw = ask_direct_agy_patch(prompt="p", timeout_sec=5, env={"NEXUS_AGY_BIN": str(exe)})
    assert out["error_category"] == "cli_error"
    assert "boom" in raw
    other = tmp_path / "other"
    other.mkdir()
    exe2, _ = _fake_agy(other, "not json at all")
    out2, _ = ask_direct_agy_patch(prompt="p", timeout_sec=5, env={"NEXUS_AGY_BIN": str(exe2)})
    assert out2["error_category"] == "parse_failure"
    # The model was billed for the unparsable answer: tokens stay measured so it is a model failure.
    assert out2["tokens_used"] == 1000
    assert out2["token_capture_status"] == "measured"


def test_timeout_is_reported_as_timeout():
    def runner(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="agy", timeout=5)

    out, _ = ask_direct_agy_patch(
        prompt="p", timeout_sec=5, env={"NEXUS_AGY_BIN": sys.executable}, runner=runner
    )
    assert out["error_category"] == "timeout"


def test_configure_lane_env_pins_one_model_for_both_arms():
    env: dict[str, str] = {"NEXUS_AGY_MODEL": "gemini-3.8-flash-low"}
    assert configure_agy_lane_env(env) == "gemini-3.8-flash-low"
    assert (
        env["NEXUS_GEMINI_MODEL_NAME"] == env["NEXUS_DIRECT_GEMINI_MODEL"] == "gemini-3.8-flash-low"
    )


def _run_bare_arm(tmp_path: Path, agy_bin: str) -> dict:
    env = {
        **os.environ,
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


def test_lane_bare_arm_with_agy_missing_is_infra_invalid_agy_missing(tmp_path: Path):
    res = _run_bare_arm(tmp_path, "/nonexistent/agy")
    assert res["row"]["model_calls"] == 0
    assert res["row"]["run_eligible"] is False
    assert res["row"]["infra_invalid_reason"] == "agy_missing"
    assert res["summary"]["eligible_n"] == 0
    assert res["summary"]["solved_n"] == 0


def test_lane_bare_arm_counts_one_model_call_and_no_rescue(tmp_path: Path):
    exe, _ = _fake_agy(tmp_path, '{"status": "ok", "patch": "unchanged = True\\n"}')
    res = _run_bare_arm(tmp_path, str(exe))
    row = res["row"]
    assert row["model_calls"] == 1
    assert row["model_name"] == AGY_DEFAULT_MODEL
    assert row["total_tokens"] == 1000
    assert row["solve_classification"] == "not_solved"
    assert row["deterministic_rescue"] is False
    assert res["summary"]["deterministic_rescue_n"] == 0
    assert res["summary"]["solved_n"] == 0
