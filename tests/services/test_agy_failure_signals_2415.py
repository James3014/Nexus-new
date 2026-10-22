"""#2415: retire Agy accounts only on agy's structured errors; cap account-wide retirements.

Fixtures are real agy outputs captured on the Mac mini (operation logs under
``~/.local/state/nexus-agy-operations/operations/*/stderr.log``, probe jobs
under ``Nexus-new-self-hosted-state/assisted_provider_jobs``, and Agy
transcripts), shortened and redacted (conversation ids zeroed, LAN address
replaced by a documentation address).
"""

from __future__ import annotations

import hashlib
import os
import threading
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
DISPATCH_PATH = ROOT / "scripts" / "ops" / "nexus-agy-dispatch"
os.environ["NEXUS_AGY_SNAPSHOT"] = str(ROOT)
dispatch = SourceFileLoader(
    "nexus_agy_dispatch_failure_signals_2415", str(DISPATCH_PATH)
).load_module()

from nexus.services.agy_account_pool import (  # noqa: E402
    AgyAccount,
    AgyAccountPoolManager,
    CrossProcessLeaseCoordinator,
)
from nexus.services.agy_failure_signals import (  # noqa: E402
    DEFAULT_MAX_ACCOUNT_RETIREMENTS,
    agy_envelope_errors,
    agy_error_payloads,
    agy_login_required,
    classify_agy_account_failure,
    is_account_global_retirement,
    max_account_retirements,
)
from nexus.services.external_account_pool import AccountFailureKind  # noqa: E402

GEMINI = "gemini-3.8-flash-high"

# --- real agy samples (redacted) -------------------------------------------

# agyop_19b888c7…: upstream capacity outage, text mode, nothing on stdout.
OUTAGE_503_STDERR = (
    "error: Our servers are experiencing high traffic right now, please try again in a "
    "minute. (UNAVAILABLE (code 503): No capacity available for model "
    "gpt-oss-120b-medium on the server)\n"
    'AGY_ERROR: {"short_error":"UNAVAILABLE (code 503): No capacity available for model '
    'gpt-oss-120b-medium on the server","status":"UNAVAILABLE","error_code":503,'
    '"code_kind":"http","retryable":true,"error_id":"9427d4ac-40fa-49a9-9370-f97746474be9-33-2010"}\n'
)

# agyop_a70b3b41…: host-wide outage reported on stderr without an AGY_ERROR line.
ELIGIBILITY_503_STDERR = (
    "error: Eligibility check failed: UNAVAILABLE (code 503): The service is currently "
    "unavailable.\n"
)

# probe-e60a20c4…: quota, --output-format json (envelope on stdout).
QUOTA_ENVELOPE_STDOUT = (
    '{"conversation_id":"00000000-0000-0000-0000-000000000000","status":"ERROR","response":"",'
    '"error":"Individual quota reached. Please upgrade your subscription to increase your '
    'limits. Resets in 22h3m37s.","duration_seconds":0,"num_turns":1,"usage":{"input_tokens":0,'
    '"output_tokens":0,"thinking_tokens":0,"cache_read_tokens":0,"total_tokens":0}}\n'
)
QUOTA_STDERR = (
    "error: Individual quota reached. Please upgrade your subscription to increase your "
    "limits. Resets in 22h3m37s.\n"
    'AGY_ERROR: {"short_error":"RESOURCE_EXHAUSTED (code 429): Individual quota reached. '
    'Please upgrade your subscription to increase your limits. Resets in 22h3m37s.",'
    '"status":"RESOURCE_EXHAUSTED","error_code":429,"code_kind":"http","retryable":true,'
    '"error_id":"d9e1423b-4fe8-4f7c-8626-0e405ac2b88f-1"}\n'
)

# agyop_40fd1b1a…: network read timeout; gRPC UNKNOWN, not an account failure.
NETWORK_STDERR = (
    "error: There was a network issue connecting to the server, please try again.\n"
    'AGY_ERROR: {"short_error":"agent executor error: generating and executing: request '
    'failed: Post \\"https://daily-cloudcode-pa.googleapis.com/v1internal:streamGenerateContent'
    '?alt=sse\\": read tcp 192.0.2.10:59603-\\u003e172.217.119.4:443: read: operation timed '
    'out","status":"UNKNOWN","error_code":2,"code_kind":"grpc","retryable":true,'
    '"error_id":"f58c6531-e2c2-49ef-be2a-b4aa6299d3c4-126"}\n'
)

# agyop_f24910f6…: model function-call format error; structured, no status.
FORMAT_STDERR = (
    "error: Your previous response contained an improperly formatted function call\n"
    'AGY_ERROR: {"short_error":"Your previous response contained an improperly formatted '
    "function call\\nPlease retry with a properly formatted function call\\nRetries "
    'remaining: 3","retryable":false,"error_id":"26870965-2839-4509-a593-db54e2a4299c-2"}\n'
)

# #2403 live sample: OAuth login prompt; no AGY_ERROR, envelope ``error``.
LOGIN_ENVELOPE_STDOUT = (
    '{"conversation_id":"","status":"ERROR","response":"",'
    '"error":"authentication failed or timed out","duration_seconds":0}\n'
)

# Real Agy model replies (transcript PLANNER_RESPONSE content) that quote
# provider error tokens while reviewing Nexus code.
MODEL_REPLY = (
    "The accept-edits permission scan of the provider log treated those lines as a "
    "permission denial, so a provider quota failure (AGY_ERROR RESOURCE_EXHAUSTED / 429) "
    "became PERMISSION_OR_SCOPE_ERROR and the dispatcher stopped after one attempt.\n"
    "The endpoint returns 401 Unauthorized when the token expired, and 503 Service "
    "Unavailable when the quota is exceeded; the account was disabled.\n"
)
MODEL_REPLY_WITH_FAKE_ERROR_LINE = (
    MODEL_REPLY + 'AGY_ERROR: {"status":"RESOURCE_EXHAUSTED","error_code":429}\n'
)


def _envelope(response: str, *, status: str = "SUCCESS", error: str = "") -> str:
    import json

    return (
        json.dumps({
            "conversation_id": "00000000-0000-0000-0000-000000000000",
            "status": status,
            "response": response,
            "error": error,
            "num_turns": 3,
            "usage": {"input_tokens": 900, "output_tokens": 120, "thinking_tokens": 40},
        })
        + "\n"
    )


# --- classification ----------------------------------------------------------


def test_real_structured_samples_classify_by_status_and_code() -> None:
    assert classify_agy_account_failure("", OUTAGE_503_STDERR, stdout_is_envelope=False) is (
        AccountFailureKind.ACCOUNT_UNAVAILABLE
    )
    assert (
        classify_agy_account_failure(QUOTA_ENVELOPE_STDOUT, QUOTA_STDERR, stdout_is_envelope=True)
        is AccountFailureKind.QUOTA_EXHAUSTED
    )
    # The envelope alone (no AGY_ERROR line) is enough in JSON mode.
    assert (
        classify_agy_account_failure(QUOTA_ENVELOPE_STDOUT, "", stdout_is_envelope=True)
        is AccountFailureKind.QUOTA_EXHAUSTED
    )
    assert (
        classify_agy_account_failure(LOGIN_ENVELOPE_STDOUT, "", stdout_is_envelope=True)
        is AccountFailureKind.AUTH_OR_SESSION_INVALID
    )


def test_structured_non_account_errors_are_not_account_failures() -> None:
    # A structured error decides alone: its stderr prose ("network issue",
    # "function call") is not rescanned for account markers.
    assert classify_agy_account_failure("", NETWORK_STDERR, stdout_is_envelope=False) is None
    assert classify_agy_account_failure("", FORMAT_STDERR, stdout_is_envelope=False) is None
    noisy = NETWORK_STDERR.replace(
        "error: There was", "warning: 401 unauthorized quota exhausted; there was"
    )
    assert classify_agy_account_failure("", noisy, stdout_is_envelope=False) is None


@pytest.mark.parametrize("stdout", [MODEL_REPLY, MODEL_REPLY_WITH_FAKE_ERROR_LINE])
def test_model_reply_text_never_classifies_an_account_failure(stdout: str) -> None:
    assert classify_agy_account_failure(stdout, "", stdout_is_envelope=False) is None
    # JSON mode: the reply sits in ``response``; only ``error`` is read.
    for envelope in (_envelope(stdout), _envelope(stdout, status="ERROR")):
        assert classify_agy_account_failure(envelope, "", stdout_is_envelope=True) is None
    # A reply quoting agy's login message is not a login failure.
    assert not agy_login_required(
        _envelope("authentication failed or timed out"), "", stdout_is_envelope=True
    )
    assert agy_login_required(LOGIN_ENVELOPE_STDOUT, "", stdout_is_envelope=True)


def test_dispatch_classify_failure_ignores_model_reply_tokens() -> None:
    for stdout in (MODEL_REPLY, MODEL_REPLY_WITH_FAKE_ERROR_LINE):
        kind = dispatch.classify_failure(1, stdout, "", False)
        assert kind is AccountFailureKind.UNKNOWN
        assert not dispatch.is_account_failover_failure(kind)
    assert dispatch.classify_failure(1, MODEL_REPLY, OUTAGE_503_STDERR, False) is (
        AccountFailureKind.ACCOUNT_UNAVAILABLE
    )
    assert dispatch.classify_failure(1, "", NETWORK_STDERR, False) is AccountFailureKind.UNKNOWN
    assert dispatch.classify_failure(1, "", QUOTA_STDERR, False) is (
        AccountFailureKind.QUOTA_EXHAUSTED
    )


def test_payload_and_envelope_parsers_are_strict() -> None:
    assert [p["status"] for p in agy_error_payloads(OUTAGE_503_STDERR)] == ["UNAVAILABLE"]
    # Only a line that starts with AGY_ERROR: counts.
    assert agy_error_payloads('note: AGY_ERROR: {"status":"UNAVAILABLE"}\n') == []
    # A JSON object without the envelope's conversation_id is not an envelope.
    assert agy_envelope_errors('{"status":"ERROR","error":"401 unauthorized"}') == []
    assert agy_envelope_errors(LOGIN_ENVELOPE_STDOUT) == ["authentication failed or timed out"]
    # A grpc error code is not an HTTP code: error_code 2 / 14 alone decide nothing.
    assert (
        classify_agy_account_failure(
            "", 'AGY_ERROR: {"error_code":401,"code_kind":"grpc"}\n', stdout_is_envelope=False
        )
        is None
    )
    assert (
        classify_agy_account_failure(
            "",
            'AGY_ERROR: {"status":"UNAUTHENTICATED","short_error":"token expired"}\n',
            stdout_is_envelope=False,
        )
        is AccountFailureKind.TOKEN_EXPIRED
    )


def test_retirement_scope_and_cap_setting(monkeypatch) -> None:
    assert not is_account_global_retirement(AccountFailureKind.QUOTA_EXHAUSTED, "gemini")
    assert is_account_global_retirement(AccountFailureKind.QUOTA_EXHAUSTED, None)
    assert is_account_global_retirement(AccountFailureKind.ACCOUNT_UNAVAILABLE, "gemini")
    assert is_account_global_retirement(AccountFailureKind.AUTH_OR_SESSION_INVALID, "gemini")
    assert not is_account_global_retirement(AccountFailureKind.TIMEOUT, "gemini")
    assert not is_account_global_retirement(AccountFailureKind.UNKNOWN, None)
    monkeypatch.delenv("NEXUS_AGY_MAX_ACCOUNT_RETIREMENTS", raising=False)
    assert max_account_retirements() == DEFAULT_MAX_ACCOUNT_RETIREMENTS == 3
    for raw, expected in (("5", 5), ("0", 1), ("-2", 1), ("x", 3)):
        monkeypatch.setenv("NEXUS_AGY_MAX_ACCOUNT_RETIREMENTS", raw)
        assert max_account_retirements() == expected


# --- nexus-agy-dispatch end to end against the real coordinator --------------


def _fresh_snapshot(names: list[str]) -> dict:
    checked_at = datetime.now(timezone.utc).isoformat()
    return {
        "checked_at": checked_at,
        "accounts": [
            {
                "account": name,
                "checked_at": checked_at,
                "ok": True,
                "groups": {
                    "Gemini Models": {
                        "5h": {"status": "known", "remaining_pct": 100.0, "reset_at": None}
                    }
                },
            }
            for name in names
        ],
    }


def _state() -> dict[str, object]:
    return {
        "family": "gemini",
        "snapshot_fresh": True,
        "preferred": [],
        "reserve": [],
        "fallback": [],
        "blocked": [],
        "unknown": [],
    }


@pytest.fixture
def pool_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NEXUS_AGY_MODEL_CATALOG_CHECK", "0")
    monkeypatch.setenv("NEXUS_AGY_POOL_QUEUE_POLL_SECONDS", "0.1")
    for name in (
        "NEXUS_AGY_POOL_WAIT_TIMEOUT",
        "NEXUS_AGY_MAX_ACCOUNT_RETIREMENTS",
        "NEXUS_AGY_MAX_ACCOUNT_FAILOVERS",
        "NEXUS_AGY_PREFERRED_ACCOUNTS",
        "NEXUS_AGY_RESERVE_ACCOUNTS",
        "NEXUS_AGY_FALLBACK_ACCOUNTS",
        "NEXUS_AGY_BLOCKED_ACCOUNTS",
    ):
        monkeypatch.delenv(name, raising=False)
    metas: list[dict] = []
    lock = threading.Lock()

    def collect(meta: dict) -> None:
        with lock:
            metas.append(dict(meta))

    monkeypatch.setattr(dispatch, "emit_meta", collect)

    def make(names: list[str]) -> CrossProcessLeaseCoordinator:
        accounts = [
            AgyAccount(alias=name, home_dir=str(tmp_path / f"home-{name}")) for name in names
        ]
        for account in accounts:
            Path(account.home_dir).mkdir(parents=True, exist_ok=True)
        snapshot = _fresh_snapshot(names)
        monkeypatch.setattr(
            dispatch, "_apply_dynamic_availability", lambda _m: (snapshot, _state())
        )
        return CrossProcessLeaseCoordinator(
            manager=AgyAccountPoolManager(accounts=accounts, use_real_manager=False),
            allocator_lock_path=tmp_path / "allocator.lock",
            leases_dir=tmp_path / "leases",
            poll_interval=0.02,
        )

    return SimpleNamespace(make=make, metas=metas, tmp_path=tmp_path, monkeypatch=monkeypatch)


def _account_of(env: dict) -> str:
    return Path(env["HOME"]).name.removeprefix("home-")


def _retired(pool_env) -> set[str]:
    leases = pool_env.tmp_path / "leases"
    return {path.name.split(".")[0] for path in leases.glob("*.quarantine.json")}


def _hash(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()[:12]


def _run(pool_env, coordinator, runner) -> int:
    return dispatch.dispatch_run(
        prompt="work",
        cwd=str(ROOT),
        mode="plan",
        model=GEMINI,
        timeout=60,
        max_calls=1,
        coordinator=coordinator,
        run_agy_fn=runner,
    )


def test_dispatch_outage_retires_at_most_the_cap_and_names_the_outage(pool_env) -> None:
    names = [f"acc{i}" for i in range(8)]
    coordinator = pool_env.make(names)
    calls: list[str] = []

    def runner(**kwargs):
        calls.append(_account_of(kwargs["env"]))
        return 3, "", OUTAGE_503_STDERR, False, 5

    code = _run(pool_env, coordinator, runner)

    assert code == 75
    assert len(calls) == DEFAULT_MAX_ACCOUNT_RETIREMENTS
    assert _retired(pool_env) == {_hash(name) for name in calls}
    final = pool_env.metas[-1]
    assert final["failure_kind"] == "AGY_UPSTREAM_UNAVAILABLE"
    assert final["last_account_failure_kind"] == "ACCOUNT_UNAVAILABLE"
    assert final["account_retirements"] == DEFAULT_MAX_ACCOUNT_RETIREMENTS
    assert len(_retired(pool_env)) < len(names)


def test_dispatch_outage_cap_is_configurable(pool_env) -> None:
    pool_env.monkeypatch.setenv("NEXUS_AGY_MAX_ACCOUNT_RETIREMENTS", "1")
    coordinator = pool_env.make(["a", "b", "c"])
    calls: list[str] = []

    def runner(**kwargs):
        calls.append(_account_of(kwargs["env"]))
        return 3, "", OUTAGE_503_STDERR, False, 5

    assert _run(pool_env, coordinator, runner) == 75
    assert len(calls) == 1
    assert _retired(pool_env) == {_hash(calls[0])}
    assert pool_env.metas[-1]["failure_kind"] == "AGY_UPSTREAM_UNAVAILABLE"


def test_dispatch_model_reply_with_401_retires_nothing(pool_env) -> None:
    coordinator = pool_env.make(["a", "b"])
    calls: list[str] = []

    def runner(**kwargs):
        calls.append(_account_of(kwargs["env"]))
        return 1, MODEL_REPLY_WITH_FAKE_ERROR_LINE, "", False, 5

    code = _run(pool_env, coordinator, runner)

    assert code == 1
    assert len(calls) == 1
    assert _retired(pool_env) == set()
    leases = pool_env.tmp_path / "leases"
    assert list(leases.glob("*.family-unavailable.*.json")) == []
    assert pool_env.metas[-1]["failure_kind"] == "UNKNOWN"


def test_dispatch_family_quota_rotation_is_not_capped(pool_env) -> None:
    coordinator = pool_env.make([f"q{i}" for i in range(6)])
    calls: list[str] = []

    def runner(**kwargs):
        calls.append(_account_of(kwargs["env"]))
        if len(calls) <= 5:
            return 1, "", QUOTA_STDERR, False, 5
        return 0, "done", "", False, 5

    code = _run(pool_env, coordinator, runner)

    assert code == 0
    assert len(calls) == 6 > DEFAULT_MAX_ACCOUNT_RETIREMENTS
    assert _retired(pool_env) == set()
    markers = list((pool_env.tmp_path / "leases").glob("*.family-unavailable.gemini.json"))
    assert len(markers) == 5


def test_dispatch_stderr_only_outage_is_capped_too(pool_env) -> None:
    assert dispatch.classify_failure(1, "", ELIGIBILITY_503_STDERR, False) is (
        AccountFailureKind.ACCOUNT_UNAVAILABLE
    )
    coordinator = pool_env.make([f"e{i}" for i in range(6)])
    calls: list[str] = []

    def runner(**kwargs):
        calls.append(_account_of(kwargs["env"]))
        return 1, "", ELIGIBILITY_503_STDERR, False, 5

    assert _run(pool_env, coordinator, runner) == 75
    assert len(calls) == DEFAULT_MAX_ACCOUNT_RETIREMENTS
    assert len(_retired(pool_env)) == DEFAULT_MAX_ACCOUNT_RETIREMENTS
    assert pool_env.metas[-1]["failure_kind"] == "AGY_UPSTREAM_UNAVAILABLE"


# --- #2866: "not logged into Antigravity" -------------------------------------

# agy's own wording (agy --log-file, 2026-10-22, every operation since 2026-09-28).
NOT_LOGGED_IN_STDERR = "error getting token source: You are not logged into Antigravity.\n"

# agyop_7a2645a9…: the stderr of the #2866 report.  agy logged in and streamed
# model turns; the run failed because a ReadFile tool was soft-denied.  The
# "not logged into" lines exist only in agy's --log-file startup output.
HEADLESS_DENIED_STDERR = (
    'jetski: no output produced — a tool required the "read_file" permission that '
    "headless mode cannot prompt for, so it was auto-denied. Add an allow-rule under "
    "permissions.allow in settings.json (e.g. read_file(<target>)). Alternatively, "
    "re-run with --dangerously-skip-permissions to auto-approve all tools.\n"
)


def test_not_logged_in_on_agy_error_channel_is_account_auth_failure_2866() -> None:
    assert classify_agy_account_failure("", NOT_LOGGED_IN_STDERR, stdout_is_envelope=False) is (
        AccountFailureKind.AUTH_OR_SESSION_INVALID
    )
    envelope = _envelope("", status="ERROR", error=NOT_LOGGED_IN_STDERR.strip())
    assert classify_agy_account_failure(envelope, "", stdout_is_envelope=True) is (
        AccountFailureKind.AUTH_OR_SESSION_INVALID
    )
    assert dispatch.classify_failure(1, "", NOT_LOGGED_IN_STDERR, False) is (
        AccountFailureKind.AUTH_OR_SESSION_INVALID
    )
    assert is_account_global_retirement(AccountFailureKind.AUTH_OR_SESSION_INVALID, "gemini")


def test_headless_denial_stderr_of_2866_report_is_not_an_account_failure() -> None:
    assert (
        classify_agy_account_failure("", HEADLESS_DENIED_STDERR, stdout_is_envelope=False) is None
    )


def test_dispatch_not_logged_in_rotates_and_marks_account_2866(pool_env) -> None:
    coordinator = pool_env.make(["a", "b"])
    calls: list[str] = []

    def runner(**kwargs):
        calls.append(_account_of(kwargs["env"]))
        if len(calls) == 1:
            return 1, "", NOT_LOGGED_IN_STDERR, False, 5
        return 0, "done", "", False, 5

    code = _run(pool_env, coordinator, runner)

    assert code == 0
    assert len(calls) == 2 and calls[0] != calls[1]
    # max_calls=1: the account failover did not consume the model-call budget.
    assert _retired(pool_env) == {_hash(calls[0])}
    final = pool_env.metas[-1]
    assert final["status"] == "completed"
    assert final["rotations"] == 1
    assert final["account_alias_hash"] == _hash(calls[1])


def test_dispatch_not_logged_in_account_is_skipped_by_later_dispatch_2866(pool_env) -> None:
    coordinator = pool_env.make(["a", "b"])
    first: list[str] = []

    def failing_then_ok(**kwargs):
        first.append(_account_of(kwargs["env"]))
        if len(first) == 1:
            return 1, "", NOT_LOGGED_IN_STDERR, False, 5
        return 0, "done", "", False, 5

    assert _run(pool_env, coordinator, failing_then_ok) == 0
    bad = first[0]
    later: list[str] = []

    def ok(**kwargs):
        later.append(_account_of(kwargs["env"]))
        return 0, "done", "", False, 5

    for _ in range(3):
        assert _run(pool_env, coordinator, ok) == 0
    assert bad not in later


def test_dispatch_every_account_not_logged_in_ends_bounded_2866(pool_env) -> None:
    names = [f"n{i}" for i in range(6)]
    coordinator = pool_env.make(names)
    calls: list[str] = []

    def runner(**kwargs):
        calls.append(_account_of(kwargs["env"]))
        return 1, "", NOT_LOGGED_IN_STDERR, False, 5

    code = _run(pool_env, coordinator, runner)

    assert code == 75
    assert len(calls) == DEFAULT_MAX_ACCOUNT_RETIREMENTS == len(set(calls))
    final = pool_env.metas[-1]
    assert final["status"] == "failed"
    assert final["failure_kind"] == "AGY_UPSTREAM_UNAVAILABLE"
    assert final["last_account_failure_kind"] == "AUTH_OR_SESSION_INVALID"


def test_dispatch_every_account_not_logged_in_small_pool_terminates_2866(pool_env) -> None:
    pool_env.monkeypatch.setenv("NEXUS_AGY_MAX_ACCOUNT_RETIREMENTS", "10")
    pool_env.monkeypatch.setenv("NEXUS_AGY_POOL_WAIT_TIMEOUT", "1")
    coordinator = pool_env.make(["x", "y"])
    calls: list[str] = []

    def runner(**kwargs):
        calls.append(_account_of(kwargs["env"]))
        return 1, "", NOT_LOGGED_IN_STDERR, False, 5

    code = _run(pool_env, coordinator, runner)

    assert code != 0
    assert sorted(calls) == ["x", "y"]
    assert _retired(pool_env) == {_hash("x"), _hash("y")}
    assert pool_env.metas[-1]["status"] != "completed"


def test_dispatch_task_failure_does_not_rotate_2866(pool_env) -> None:
    coordinator = pool_env.make(["a", "b"])
    calls: list[str] = []

    def runner(**kwargs):
        calls.append(_account_of(kwargs["env"]))
        return 1, "", HEADLESS_DENIED_STDERR, False, 5

    code = _run(pool_env, coordinator, runner)

    assert code != 0
    assert len(calls) == 1
    assert _retired(pool_env) == set()
    assert pool_env.metas[-1]["rotations"] == 0
