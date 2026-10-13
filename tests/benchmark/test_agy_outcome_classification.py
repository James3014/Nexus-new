"""Agy outcome classification against real recorded samples (#1932 R0/R3, agy 1.3.3).

Fixtures in ``fixtures/agy_outcomes`` are minimal redacted excerpts of live calls: stdout/stderr
verbatim (no account data in them) and only the model-identity, conversation and timeout lines of
Agy's log. ``quota_1362_empty_success`` reproduces the #1362 shape with the terminal-quota log line
recorded in tests/services/test_agy_dispatch.py. Every Agy process here is a fake replaying a
fixture; nothing calls Agy or a model.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from scripts.bench.agy_account_lease import (
    QUOTA_EXHAUSTED_AFTER_EFFECT,
    QUOTA_EXHAUSTED_PRE_EFFECT,
)
from scripts.bench.agy_provider import (
    AGY_NO_DELIVERY_PERMISSION_DENIED,
    AGY_NO_TOOLS_PREFIX,
    AGY_NO_TOOLS_PREFIX_ENV,
    ask_direct_agy_patch,
)
from scripts.bench.benchmark_eligibility import classify_infra_invalid_reason
from tests.benchmark.agy_outcome_fixtures import AGY_OUTCOME_FIXTURES


def _sample(name: str) -> tuple[str, str, str]:
    return tuple(  # type: ignore[return-value]
        AGY_OUTCOME_FIXTURES[(name, suffix)] for suffix in ("stdout", "stderr", "agylog.txt")
    )


def _replay(*samples: tuple[str, str, str], prompts: list[str] | None = None):
    """Fake ``subprocess.run`` replaying samples in order (last one repeats), rc=0 like Agy."""
    queue = list(samples)

    def runner(cmd: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        stdout, stderr, log = queue.pop(0) if len(queue) > 1 else queue[0]
        Path(cmd[cmd.index("--log-file") + 1]).write_text(log, encoding="utf-8")
        if prompts is not None:
            prompts.append(cmd[cmd.index("--print") + 1])
        return subprocess.CompletedProcess(cmd, 0, stdout, stderr)

    return runner


def _ask(agy_pool, *samples, **env_extra: str):
    prompts: list[str] = []
    out, raw = ask_direct_agy_patch(
        prompt="fix it",
        timeout_sec=30,
        env=agy_pool.env(**env_extra),
        runner=_replay(*samples, prompts=prompts),
    )
    return out, raw, prompts


def _bare_arm_row(out: dict[str, Any], raw: str) -> dict[str, Any]:
    """The fields capability_ab_runner derives for a bare-arm row (model_calls=0 on timeout)."""
    category = str(out.get("error_category") or "")
    return {
        "baseline_gateway_error_category": category,
        "baseline_raw_tail": raw[-1000:],
        "model_calls": 0 if category == "timeout" else 1,
        "total_tokens": int(out.get("tokens_used") or 0),
        "token_capture_status": out.get("token_capture_status", "unknown"),
    }


def _eligibility(out: dict[str, Any], raw: str) -> str | None:
    return classify_infra_invalid_reason(
        _bare_arm_row(out, raw), model_required=True, nexus_required=False
    )


def test_fixtures_hold_no_account_data_or_secrets():
    for key, raw in sorted(AGY_OUTCOME_FIXTURES.items()):
        text = raw.lower()
        assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text), key
        for needle in (
            "jameschen",
            "bearer",
            "api_key",
            "access_token",
            "refresh_token",
            "/users/",
        ):
            assert needle not in text, (key, needle)


@pytest.mark.parametrize("name", ["denied_command", "denied_read_file"])
def test_denied_tool_without_delivery_is_its_own_model_failure(agy_pool, name):
    out, raw, _ = _ask(agy_pool, _sample(name))
    assert out["status"] == "FAIL"
    assert out["error_category"] == AGY_NO_DELIVERY_PERMISSION_DENIED
    assert out["model_identity_status"] == "MODEL_IDENTITY_OK"
    assert out["agy_denied_actions"] == [
        json.loads(_sample(name)[0])["denied_actions"][0]["action"]
    ]
    assert out["tokens_used"] > 0 and out["token_capture_status"] == "measured"
    # Served and billed, no answer: a model failure that stays run-eligible (scored unsolved).
    assert _eligibility(out, raw) is None


def test_stderr_only_no_delivery_marker_is_classified_too(agy_pool):
    stdout, stderr, log = _sample("denied_command")
    envelope = json.loads(stdout)
    envelope.pop("denied_actions")
    out, _, _ = _ask(agy_pool, (json.dumps(envelope), stderr, log))
    assert out["error_category"] == AGY_NO_DELIVERY_PERMISSION_DENIED
    assert out["agy_denied_actions"] == []


@pytest.mark.parametrize("name", ["print_timeout", "print_timeout_2"])
def test_agy_print_timeout_is_a_timeout_not_a_parse_failure(agy_pool, name):
    out, raw, _ = _ask(agy_pool, _sample(name))
    assert out["error_category"] == "timeout"
    assert out["timeout_source"] == "agy_print_timeout"
    assert out["tokens_used"] == 0
    assert out["account_attempts"] == 1 and out["run_retired"] is False
    assert _eligibility(out, raw) == "timeout_before_model_call"


def test_print_timeout_in_log_alone_is_still_a_timeout(agy_pool):
    stdout, _stderr, log = _sample("print_timeout")
    out, _, _ = _ask(agy_pool, (stdout, "", log))
    assert out["error_category"] == "timeout"


def test_quota_1362_rc0_empty_success_rotates_before_effect(agy_pool):
    out, _, _ = _ask(agy_pool, _sample("quota_1362_empty_success"), _sample("success_patch_json"))
    assert out.get("error_category") is None
    assert out["status"] == "OK"
    assert out["account_attempts"] == 2 and out["account_rotations"] == 1
    assert out["account_lease_records"][0]["outcome"] == QUOTA_EXHAUSTED_PRE_EFFECT


def test_quota_rc0_with_stderr_marker_rotates_through_every_account(agy_pool):
    stdout, _, log = _sample("quota_1362_empty_success")
    quota_log = "".join(log.splitlines(keepends=True)[:3])  # identity lines, no terminal line
    out, _, _ = _ask(agy_pool, (stdout, "RESOURCE_EXHAUSTED: quota exhausted", quota_log))
    assert out["error_category"] == QUOTA_EXHAUSTED_PRE_EFFECT
    assert out["account_attempts"] == len(agy_pool.accounts)
    assert out["run_retired"] is False


def test_quota_rc0_after_billed_effect_retires_the_run(agy_pool):
    stdout, stderr, log = _sample("quota_1362_empty_success")
    billed = json.loads(stdout)
    billed["usage"]["total_tokens"] = 900
    out, _, _ = _ask(agy_pool, (json.dumps(billed), stderr, log))
    assert out["error_category"] == QUOTA_EXHAUSTED_AFTER_EFFECT
    assert out["run_retired"] is True and out["account_attempts"] == 1


def test_real_success_with_patch_json_still_scores(agy_pool):
    out, raw, _ = _ask(agy_pool, _sample("success_patch_json"))
    assert "error_category" not in out
    assert out["status"] == "OK"
    assert out["patch"].startswith("--- a/calc.py")
    assert out["model_patch_generated"] is True
    assert out["tokens_used"] == 16065 and out["token_capture_status"] == "measured"
    assert out["account_attempts"] == 1 and out["account_rotations"] == 0
    assert _eligibility(out, raw) is None


def test_real_plain_text_success_is_not_mistaken_for_infra(agy_pool):
    # R0 identity probe answered "OK": delivered, so neither quota, timeout nor no-delivery.
    out, _, _ = _ask(agy_pool, _sample("success_plain_text"))
    assert out["error_category"] == "parse_failure"
    assert out["tokens_used"] == 15197
    assert out["account_attempts"] == 1


def test_no_tools_prefix_is_on_by_default_and_recorded(agy_pool):
    out, _, prompts = _ask(agy_pool, _sample("success_patch_json"))
    assert prompts == [AGY_NO_TOOLS_PREFIX + "fix it"]
    assert out["agy_no_tools_prefix_applied"] is True
    assert out["agy_no_tools_prefix_id"] == "agy_no_tools_v1"


def test_no_tools_prefix_can_be_disabled_and_is_recorded_on_failures(agy_pool):
    out, _, prompts = _ask(agy_pool, _sample("print_timeout"), **{AGY_NO_TOOLS_PREFIX_ENV: "0"})
    assert prompts == ["fix it"]
    assert out["agy_no_tools_prefix_applied"] is False
    assert out["error_category"] == "timeout"
    missing, _ = ask_direct_agy_patch(
        prompt="p", timeout_sec=5, env={"NEXUS_AGY_BIN": "/nonexistent/agy"}
    )
    assert missing["agy_no_tools_prefix_applied"] is True
