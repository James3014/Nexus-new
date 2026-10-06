"""Regression tests for the canonical Agy dispatch wrapper."""

from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import sys
import textwrap
import threading
import time
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DISPATCH_PATH = ROOT / "scripts" / "ops" / "nexus-agy-dispatch"
INSTALLER_PATH = ROOT / "scripts" / "ops" / "install_nexus_agy_dispatch.sh"

os.environ["NEXUS_AGY_SNAPSHOT"] = str(ROOT)
dispatch = SourceFileLoader("nexus_agy_dispatch_canonical", str(DISPATCH_PATH)).load_module()


def _window(remaining: float, *, reset_at: str | None = None) -> dict:
    return {
        "status": "known",
        "remaining_pct": remaining,
        "reset_at": reset_at,
    }


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()


def test_weekly_only_quota_is_usable_fallback() -> None:
    groups = {"Gemini Models": {"weekly": _window(86.0)}}
    assert dispatch._usable_quota_window(groups, "Gemini Models") == (
        True,
        "weekly",
    )


def test_explicit_disabled_five_hour_stays_fail_closed() -> None:
    groups = {
        "Gemini Models": {
            "5h": {
                "status": "disabled",
                "remaining_pct": None,
                "reset_at": None,
            },
            "weekly": _window(86.0),
        }
    }
    assert dispatch._usable_quota_window(groups, "Gemini Models") == (
        False,
        "5h",
    )


def test_explicit_five_hour_takes_precedence_over_weekly() -> None:
    groups = {
        "Gemini Models": {
            "5h": _window(25.0),
            "weekly": _window(0.0, reset_at="2999-01-01T00:00:00Z"),
        }
    }
    assert dispatch._usable_quota_window(groups, "Gemini Models") == (
        True,
        "5h",
    )


def test_weekly_only_dual_family_account_enters_reserve() -> None:
    now = 2_000_000_000.0
    snapshot = {
        "checked_at": _iso(now),
        "accounts": [
            {
                "account": "weekly-only",
                "ok": True,
                "groups": {
                    "Gemini Models": {"weekly": _window(86.0)},
                    "Claude and GPT models": {"weekly": _window(100.0)},
                },
            },
            {
                "account": "gemini-5h",
                "ok": True,
                "groups": {
                    "Gemini Models": {
                        "5h": _window(80.0, reset_at=_iso(now + 3600)),
                        "weekly": _window(70.0),
                    },
                    "Claude and GPT models": {"weekly": _window(100.0)},
                },
            },
            {
                "account": "dual-5h",
                "ok": True,
                "groups": {
                    "Gemini Models": {
                        "5h": _window(90.0, reset_at=_iso(now + 3600)),
                        "weekly": _window(60.0),
                    },
                    "Claude and GPT models": {
                        "5h": _window(75.0, reset_at=_iso(now + 3600)),
                        "weekly": _window(65.0),
                    },
                },
            },
            {
                "account": "blocked",
                "ok": True,
                "groups": {
                    "Gemini Models": {
                        "weekly": _window(0.0, reset_at=_iso(now + 86400)),
                    }
                },
            },
            {
                "account": "unknown",
                "ok": False,
                "error": "timeout",
            },
        ],
    }

    state = dispatch._dynamic_availability_state(
        "gemini-3.8-flash-medium",
        snapshot,
        now_ts=now,
        max_age_seconds=900,
    )

    assert state["snapshot_fresh"] is True
    assert state["preferred"] == ["gemini-5h"]
    assert state["reserve"] == ["dual-5h"]
    assert state["fallback"] == ["weekly-only"]
    assert state["blocked"] == ["blocked"]
    assert state["unknown"] == ["unknown"]


def test_expiry_aware_draining_orders_five_hour_accounts_by_pressure() -> None:
    now = 2_000_000_000.0
    snapshot = {
        "checked_at": _iso(now),
        "accounts": [
            {
                "account": "far-high",
                "ok": True,
                "groups": {
                    "Gemini Models": {
                        "5h": _window(90.0, reset_at=_iso(now + 9 * 3600)),
                    }
                },
            },
            {
                "account": "near-medium",
                "ok": True,
                "groups": {
                    "Gemini Models": {
                        "5h": _window(60.0, reset_at=_iso(now + 2 * 3600)),
                    }
                },
            },
            {
                "account": "near-low",
                "ok": True,
                "groups": {
                    "Gemini Models": {
                        "5h": _window(5.0, reset_at=_iso(now + 3600)),
                    }
                },
            },
            {
                "account": "no-reset",
                "ok": True,
                "groups": {
                    "Gemini Models": {
                        "5h": _window(100.0),
                    }
                },
            },
        ],
    }

    state = dispatch._dynamic_availability_state(
        "gemini-3.8-flash-medium",
        snapshot,
        now_ts=now,
        max_age_seconds=900,
    )

    # Pressure = remaining_pct / hours_to_reset:
    # near-medium=30, far-high=10, near-low=5; unknown reset comes last.
    assert state["preferred"] == [
        "near-medium",
        "far-high",
        "near-low",
        "no-reset",
    ]


def test_expiry_aware_draining_orders_weekly_fallback_by_pressure() -> None:
    now = 2_000_000_000.0
    snapshot = {
        "checked_at": _iso(now),
        "accounts": [
            {
                "account": "weekly-later",
                "ok": True,
                "groups": {
                    "Gemini Models": {
                        "weekly": _window(90.0, reset_at=_iso(now + 90 * 3600)),
                    }
                },
            },
            {
                "account": "weekly-soon",
                "ok": True,
                "groups": {
                    "Gemini Models": {
                        "weekly": _window(50.0, reset_at=_iso(now + 10 * 3600)),
                    }
                },
            },
        ],
    }

    state = dispatch._dynamic_availability_state(
        "gemini-3.8-flash-medium",
        snapshot,
        now_ts=now,
        max_age_seconds=900,
    )

    assert state["fallback"] == ["weekly-soon", "weekly-later"]


def test_stale_quota_snapshot_cannot_block_or_prioritize_accounts() -> None:
    now = 2_000_000_000.0
    snapshot = {
        "checked_at": _iso(now - 901),
        "accounts": [
            {
                "account": "apparently-blocked",
                "ok": True,
                "groups": {
                    "Gemini Models": {
                        "weekly": _window(0.0, reset_at=_iso(now + 86400)),
                    }
                },
            }
        ],
    }

    state = dispatch._dynamic_availability_state(
        "gemini-3.8-flash-medium",
        snapshot,
        now_ts=now,
        max_age_seconds=900,
    )

    assert state == {
        "family": "gemini",
        "snapshot_fresh": False,
        "preferred": [],
        "reserve": [],
        "fallback": [],
        "blocked": [],
        "unknown": [],
    }


def test_partial_refresh_does_not_make_old_account_rows_fresh() -> None:
    now = 2_000_000_000.0
    snapshot = {
        "checked_at": _iso(now),
        "accounts": [
            {
                "account": "fresh-row",
                "checked_at": _iso(now),
                "ok": True,
                "groups": {
                    "Gemini Models": {"weekly": _window(90.0)},
                },
            },
            {
                "account": "old-row",
                "checked_at": _iso(now - 3600),
                "ok": True,
                "groups": {
                    "Gemini Models": {
                        "5h": _window(100.0, reset_at=_iso(now + 3600)),
                    },
                },
            },
        ],
    }

    state = dispatch._dynamic_availability_state(
        "gemini-3.8-flash-medium",
        snapshot,
        now_ts=now,
        max_age_seconds=900,
    )

    assert state["fallback"] == ["fresh-row"]
    assert state["unknown"] == ["old-row"]
    assert state["preferred"] == []
    assert state["blocked"] == []


def test_family_failure_uses_matching_quota_reset_when_available() -> None:
    now = 2_000_000_000.0
    reset = now + 1800
    snapshot = {
        "checked_at": _iso(now),
        "accounts": [
            {
                "account": "dual-5h",
                "ok": True,
                "groups": {
                    "Gemini Models": {
                        "5h": _window(10.0, reset_at=_iso(reset)),
                    }
                },
            }
        ],
    }

    unavailable_until = dispatch._family_failure_unavailable_until(
        snapshot=snapshot,
        account_name="dual-5h",
        model_family="gemini",
        failure_kind=dispatch.AccountFailureKind.QUOTA_EXHAUSTED,
        now_ts=now,
    )

    assert unavailable_until == reset


def test_stale_account_row_uses_bounded_family_failure_ttl() -> None:
    now = 2_000_000_000.0
    snapshot = {
        "checked_at": _iso(now),
        "accounts": [
            {
                "account": "dual-5h",
                "checked_at": _iso(now - 3600),
                "ok": True,
                "groups": {
                    "Gemini Models": {
                        "5h": _window(10.0, reset_at=_iso(now + 86400)),
                    }
                },
            }
        ],
    }

    unavailable_until = dispatch._family_failure_unavailable_until(
        snapshot=snapshot,
        account_name="dual-5h",
        model_family="gemini",
        failure_kind=dispatch.AccountFailureKind.QUOTA_EXHAUSTED,
        now_ts=now,
    )

    assert unavailable_until == now + dispatch.DEFAULT_QUOTA_FAMILY_BLOCK_SECONDS


def test_stale_snapshot_uses_bounded_family_failure_ttl() -> None:
    now = 2_000_000_000.0
    snapshot = {
        "checked_at": _iso(now - 3600),
        "accounts": [
            {
                "account": "dual-5h",
                "ok": True,
                "groups": {
                    "Gemini Models": {
                        "5h": _window(10.0, reset_at=_iso(now + 86400)),
                    }
                },
            }
        ],
    }

    unavailable_until = dispatch._family_failure_unavailable_until(
        snapshot=snapshot,
        account_name="dual-5h",
        model_family="gemini",
        failure_kind=dispatch.AccountFailureKind.QUOTA_EXHAUSTED,
        now_ts=now,
    )

    assert unavailable_until == now + dispatch.DEFAULT_QUOTA_FAMILY_BLOCK_SECONDS


def test_installer_deploys_exact_canonical_bytes(tmp_path: Path) -> None:
    target = tmp_path / "nexus-agy-dispatch"
    env = os.environ.copy()
    env.update({
        "NEXUS_AGY_REPO_ROOT": str(ROOT),
        "NEXUS_AGY_SNAPSHOT": str(ROOT),
        "NEXUS_AGY_DISPATCH_TARGET": str(target),
    })

    proc = subprocess.run(
        ["bash", str(INSTALLER_PATH)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert target.read_bytes() == DISPATCH_PATH.read_bytes()
    mode = target.stat().st_mode
    assert mode & stat.S_IXUSR
    assert mode & stat.S_IXGRP
    assert mode & stat.S_IXOTH


def test_default_snapshot_prefers_host_runtime_generation(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    current = tmp_path / ".local/share/nexus-host-runtime/current/snapshot"
    current.mkdir(parents=True)

    assert dispatch._default_snapshot() == current


def test_default_snapshot_falls_back_to_legacy_before_host_sync(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))

    assert dispatch._default_snapshot() == (tmp_path / ".local/share/nexus-agy-direct/Nexus-new")


def test_background_timeout_is_persisted_as_outcome_unknown(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "ops"
    journal = dispatch.AgyOperationJournal(root)
    operation_id = dispatch.new_operation_id()
    prompt_path = journal.prompt_path(operation_id)
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model="gemini-test",
        effort="medium",
        prompt_sha256="0" * 64,
        runtime_revision="a" * 40,
    )
    dispatch._write_private_prompt(prompt_path, "long task")

    def fake_dispatch_run(**kwargs):
        kwargs["operation_hook"]({
            "phase": "CLASSIFYING_FAILURE",
            "attempts": 1,
            "rotations": 0,
            "failure_kind": "TIMEOUT",
            "timed_out": True,
            "account_alias_hash": "acct",
            "lease_id_hash": "lease",
        })
        return 1

    monkeypatch.setattr(dispatch, "dispatch_run", fake_dispatch_run)

    code = dispatch._run_background_operation(
        operation_id=operation_id,
        prompt_file=str(prompt_path),
        cwd=str(tmp_path),
        mode="accept-edits",
        model="gemini-test",
        effort="medium",
        timeout=30,
        max_calls=1,
        pool_wait_timeout=1.0,
        allow=[],
        deny=[],
        temp_command_permissions=False,
        operation_root=root,
        heartbeat_interval=0.01,
    )

    record = journal.read(operation_id)
    assert code == 1
    assert record["status"] == "OUTCOME_UNKNOWN"
    assert record["failure_kind"] == "TIMEOUT"
    assert record["reconciliation"]["retry_permitted"] is False
    assert record["reconciliation"]["result"] == "PROVIDER_TURN_MAY_STILL_BE_RUNNING"
    assert not prompt_path.exists()


def test_quota_progress_is_durable_while_child_runs_and_identity_safe(
    tmp_path: Path, monkeypatch
) -> None:
    operation_root = tmp_path / "ops"
    journal = dispatch.AgyOperationJournal(operation_root)
    operation_id = dispatch.new_operation_id()
    prompt_path = journal.prompt_path(operation_id)
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model="gemini-test",
        effort="medium",
        prompt_sha256="0" * 64,
        runtime_revision="a" * 40,
    )
    dispatch._write_private_prompt(prompt_path, "quota progress probe")

    command = tmp_path / "fake-quota-command"
    command.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import json
            import os
            import sys
            import time
            from pathlib import Path

            running = Path(os.environ["QUOTA_RUNNING_MARKER"])
            release = Path(os.environ["QUOTA_RELEASE_MARKER"])
            finished = Path(os.environ["QUOTA_FINISHED_MARKER"])
            print("provider diagnostic credential=provider-secret", file=sys.stderr)
            sys.stderr.write("NEXUS_AGY_QUOTA {malformed json}\\n")
            sys.stderr.write(
                "NEXUS_AGY_QUOTA "
                + json.dumps({"phase": "UNRECOGNIZED", "token": "unknown-secret"})
                + "\\n"
            )
            running.write_text("running", encoding="utf-8")
            sys.stderr.write(
                "NEXUS_AGY_QUOTA "
                + json.dumps({
                    "phase": "QUERYING_ACCOUNT",
                    "timestamp": "2026-10-04T12:00:00+00:00",
                    "account": sys.argv[1],
                    "email": "private@example.test",
                    "credential": "must-not-persist",
                    "timeout": 4,
                    "arbitrary_provider_log": "do-not-store",
                })
                + "\\n"
            )
            sys.stderr.flush()
            while not release.exists():
                time.sleep(0.01)
            sys.stderr.write(
                "NEXUS_AGY_QUOTA "
                + json.dumps({
                    "phase": "ACCOUNT_RESULT",
                    "account": sys.argv[1],
                    "ok": False,
                    "error": "api_key=should-not-persist",
                })
                + "\\n"
            )
            sys.stderr.flush()
            print(json.dumps({"machine_result": "preserved-on-stdout"}))
            finished.write_text("finished", encoding="utf-8")
            """
        ),
        encoding="utf-8",
    )
    command.chmod(0o755)
    running_marker = tmp_path / "quota-running"
    release_marker = tmp_path / "quota-release"
    finished_marker = tmp_path / "quota-finished"
    monkeypatch.setenv("QUOTA_RUNNING_MARKER", str(running_marker))
    monkeypatch.setenv("QUOTA_RELEASE_MARKER", str(release_marker))
    monkeypatch.setenv("QUOTA_FINISHED_MARKER", str(finished_marker))
    monkeypatch.setattr(dispatch, "_quota_refresh_binary", lambda: str(command))
    monkeypatch.setattr(dispatch, "_load_quota_snapshot", lambda *_args: {})
    monkeypatch.setattr(dispatch, "_runtime_revision", lambda: "b" * 40)

    account_alias_hash = "012345abcdef"

    def fake_dispatch_run(**kwargs):
        operation_hook = kwargs["operation_hook"]
        operation_hook({
            "phase": "ACCOUNT_LEASED",
            "account_alias_hash": account_alias_hash,
            "provider_started_at": None,
            "first_effect_at": None,
        })
        dispatch._refresh_quota_snapshot_for_account(
            "private-account-id",
            timeout=4,
            account_alias_hash=account_alias_hash,
            on_phase_hook=lambda **event: operation_hook(event),
        )
        return 1

    monkeypatch.setattr(dispatch, "dispatch_run", fake_dispatch_run)
    observed: dict[str, object] = {}

    def observe_durable_progress() -> None:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            record = journal.read(operation_id)
            progress = record.get("quota_preflight_progress")
            if isinstance(progress, dict) and progress.get("phase") == "QUERYING_ACCOUNT":
                observed["record"] = record
                observed["raw_record"] = journal.record_path(operation_id).read_text(
                    encoding="utf-8"
                )
                observed["child_was_running"] = running_marker.is_file()
                observed["child_was_finished"] = finished_marker.exists()
                release_marker.touch()
                return
            time.sleep(0.01)
        observed["error"] = "quota child did not durably report QUERYING_ACCOUNT"
        release_marker.touch()

    observer = threading.Thread(target=observe_durable_progress, daemon=True)
    observer.start()
    code = dispatch._run_background_operation(
        operation_id=operation_id,
        prompt_file=str(prompt_path),
        cwd=str(tmp_path),
        mode="plan",
        model="gemini-test",
        effort="medium",
        timeout=30,
        max_calls=1,
        pool_wait_timeout=1.0,
        allow=[],
        deny=[],
        temp_command_permissions=False,
        operation_root=operation_root,
        heartbeat_interval=60,
    )
    observer.join(timeout=5)
    assert not observer.is_alive()
    assert "error" not in observed, observed.get("error")

    record = observed["record"]
    progress = record["quota_preflight_progress"]
    assert observed["child_was_running"] is True
    assert observed["child_was_finished"] is False
    assert record["status"] == "RUNNING"
    assert record["phase"] == "ACCOUNT_LEASED"
    assert progress["account_alias_hash"] == account_alias_hash
    assert progress["timeout_seconds"] == 4.0
    assert record["provider_started_at"] is None
    assert record["first_effect_at"] is None
    raw_record = observed["raw_record"]
    for secret in (
        "private-account-id",
        "private@example.test",
        "provider-secret",
        "must-not-persist",
        "unknown-secret",
        "do-not-store",
    ):
        assert secret not in raw_record

    assert code == 1
    terminal = journal.read(operation_id)
    assert terminal["status"] == "FAILED"
    assert terminal["provider_started_at"] is None
    assert terminal["first_effect_at"] is None
    assert terminal["quota_preflight_progress"]["phase"] == "ACCOUNT_RESULT"
    terminal_raw = journal.record_path(operation_id).read_text(encoding="utf-8")
    assert "api_key=should-not-persist" not in terminal_raw


def test_quota_child_timeout_is_bounded_and_does_not_claim_provider_outcome_unknown(
    tmp_path: Path, monkeypatch
) -> None:
    operation_root = tmp_path / "ops"
    journal = dispatch.AgyOperationJournal(operation_root)
    operation_id = dispatch.new_operation_id()
    prompt_path = journal.prompt_path(operation_id)
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model="gemini-test",
        effort="medium",
        prompt_sha256="0" * 64,
        runtime_revision="a" * 40,
    )
    dispatch._write_private_prompt(prompt_path, "quota timeout probe")

    child_pid_path = tmp_path / "quota-child.pid"
    command = tmp_path / "stalled-quota-command"
    command.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import json
            import os
            import sys
            import time
            from pathlib import Path

            Path(os.environ["QUOTA_CHILD_PID_PATH"]).write_text(str(os.getpid()))
            sys.stderr.write(
                "NEXUS_AGY_QUOTA "
                + json.dumps({
                    "phase": "QUERYING_ACCOUNT",
                    "timestamp": "2026-10-04T12:00:00+00:00",
                    "account": sys.argv[1],
                })
                + "\\n"
            )
            sys.stderr.flush()
            while True:
                time.sleep(0.1)
            """
        ),
        encoding="utf-8",
    )
    command.chmod(0o755)
    monkeypatch.setenv("QUOTA_CHILD_PID_PATH", str(child_pid_path))
    monkeypatch.setattr(dispatch, "_quota_refresh_binary", lambda: str(command))
    monkeypatch.setattr(dispatch, "_load_quota_snapshot", lambda *_args: {})
    monkeypatch.setattr(dispatch, "_runtime_revision", lambda: "b" * 40)
    account_alias_hash = "012345abcdef"

    def fake_dispatch_run(**kwargs):
        operation_hook = kwargs["operation_hook"]
        operation_hook({"phase": "ACCOUNT_LEASED", "account_alias_hash": account_alias_hash})
        dispatch._refresh_quota_snapshot_for_account(
            "private-account-id",
            timeout=1,
            account_alias_hash=account_alias_hash,
            on_phase_hook=lambda **event: operation_hook(event),
        )
        return 1

    monkeypatch.setattr(dispatch, "dispatch_run", fake_dispatch_run)
    code = dispatch._run_background_operation(
        operation_id=operation_id,
        prompt_file=str(prompt_path),
        cwd=str(tmp_path),
        mode="plan",
        model="gemini-test",
        effort="medium",
        timeout=30,
        max_calls=1,
        pool_wait_timeout=1.0,
        allow=[],
        deny=[],
        temp_command_permissions=False,
        operation_root=operation_root,
        heartbeat_interval=60,
    )

    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    record = journal.read(operation_id)
    assert code == 1
    assert record["status"] == "FAILED"
    assert record["phase"] == "TERMINAL"
    assert record["reconciliation"] is None
    assert record["provider_started_at"] is None
    assert record["first_effect_at"] is None
    assert record["quota_preflight_progress"] == {
        "phase": "TIMED_OUT",
        "error_kind": "TIMEOUT",
        "account_alias_hash": account_alias_hash,
    }
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)


def test_quota_deadline_keeps_finalize_headroom_for_partial_snapshot(
    tmp_path: Path, monkeypatch
) -> None:
    command = tmp_path / "deadline-quota-command"
    snapshot_path = tmp_path / "partial-snapshot.json"
    budget_path = tmp_path / "child-total-budget.txt"
    command.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import json
            import os
            import sys
            import time
            from pathlib import Path

            def emit(phase, **details):
                event = {
                    "phase": phase,
                    "timestamp": "2026-10-04T12:00:00+00:00",
                    **details,
                }
                sys.stderr.write("NEXUS_AGY_QUOTA " + json.dumps(event) + "\\n")
                sys.stderr.flush()

            timeout = float(os.environ["NEXUS_AGY_QUOTA_TOTAL_TIMEOUT"])
            Path(os.environ["QUOTA_CHILD_BUDGET_PATH"]).write_text(str(timeout))
            started = time.monotonic()
            while time.monotonic() - started < timeout:
                time.sleep(0.005)
            emit("DEADLINE_EXCEEDED", account=sys.argv[1])
            time.sleep(0.1)
            payload = {
                "checked_at": "2026-10-04T12:00:00+00:00",
                "partial": True,
                "accounts": [{"account": sys.argv[1], "ok": False}],
            }
            snapshot = Path(os.environ["QUOTA_PARTIAL_SNAPSHOT_PATH"])
            snapshot.write_text(json.dumps(payload), encoding="utf-8")
            emit("SAVING_SNAPSHOT", snapshot_path=str(snapshot))
            emit("FINISHED", total=1, ok=0)
            """
        ),
        encoding="utf-8",
    )
    command.chmod(0o755)
    monkeypatch.setenv("QUOTA_CHILD_BUDGET_PATH", str(budget_path))
    monkeypatch.setenv("QUOTA_PARTIAL_SNAPSHOT_PATH", str(snapshot_path))
    monkeypatch.setenv("NEXUS_AGY_QUOTA_TOTAL_TIMEOUT", "2.9")
    monkeypatch.setattr(dispatch, "_quota_refresh_binary", lambda: str(command))
    monkeypatch.setattr(
        dispatch,
        "_load_quota_snapshot",
        lambda *_args: json.loads(snapshot_path.read_text(encoding="utf-8")),
    )
    events: list[dict[str, object]] = []
    started = time.monotonic()

    snapshot = dispatch._refresh_quota_snapshot_for_account(
        "private-account-id",
        timeout=3,
        account_alias_hash="012345abcdef",
        on_phase_hook=lambda **event: events.append(event),
    )
    elapsed = time.monotonic() - started

    child_budget = float(budget_path.read_text(encoding="utf-8"))
    phases = [
        event["quota_preflight_progress"]["phase"]
        for event in events
        if "quota_preflight_progress" in event
    ]
    assert 0 < child_budget < 3
    assert child_budget == pytest.approx(2.25)
    assert elapsed < 3
    assert snapshot["partial"] is True
    assert "DEADLINE_EXCEEDED" in phases
    assert "SAVING_SNAPSHOT" in phases
    assert "FINISHED" in phases


def test_background_spawn_returns_durable_operation_identity(tmp_path: Path, monkeypatch) -> None:
    class FakeProcess:
        pid = 424242

    captured: dict[str, object] = {}

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return FakeProcess()

    class FakeSubprocess:
        DEVNULL = dispatch.subprocess.DEVNULL
        Popen = staticmethod(fake_popen)

    monkeypatch.setattr(dispatch, "subprocess", FakeSubprocess)
    root = tmp_path / "ops"

    record = dispatch._spawn_background_operation(
        prompt="do not persist this prompt",
        cwd=str(tmp_path),
        mode="accept-edits",
        model="gemini-test",
        effort="medium",
        timeout=60,
        max_calls=1,
        pool_wait_timeout=1.0,
        allow=[],
        deny=[],
        temp_command_permissions=False,
        operation_root=root,
        write_paths=[str(tmp_path / "target.txt")],
        provider_stall_seconds=17.0,
        stream_no_progress_seconds=29.0,
        pre_effect_max_seconds=41.0,
        pre_effect_max_tool_events=13,
    )

    assert record["status"] == "QUEUED"
    assert record["pid"] == 424242
    assert record["operation_id"].startswith("agyop_")
    raw = (root / "operations" / record["operation_id"] / "operation.json").read_text()
    assert "do not persist this prompt" not in raw
    assert "--operation-run" in captured["argv"]
    assert captured["argv"][captured["argv"].index("--provider-stall-seconds") + 1] == "17.0"
    assert captured["argv"][captured["argv"].index("--stream-no-progress-seconds") + 1] == "29.0"
    assert captured["argv"][captured["argv"].index("--pre-effect-max-seconds") + 1] == "41.0"
    assert captured["argv"][captured["argv"].index("--pre-effect-max-tool-events") + 1] == "13"
    assert record["liveness_policy"] == {
        "coding_progress_required": True,
        "provider_stall_seconds": 17.0,
        "stream_no_progress_seconds": 29.0,
        "pre_effect_max_seconds": 41.0,
        "pre_effect_max_tool_events": 13,
    }
    assert captured["kwargs"]["start_new_session"] is True
    prompt_path = root / "operations" / record["operation_id"] / ".prompt"
    assert stat.S_IMODE(prompt_path.stat().st_mode) == 0o600


def test_parse_agy_attestation_binds_resolved_model_and_conversation(tmp_path: Path) -> None:
    log = tmp_path / "agy.log"
    log.write_text(
        "\n".join([
            'I0000 model_resolver.go:116] model alias "gemini-3.8-flash" resolved to "gemini-3.8-flash-low"',
            "I0000 model_resolver.go:93] Resolving model gemini-3.8-flash-low",
            "I0000 server.go:1239] Created conversation f67d38d4-f220-4bc0-a216-cef594235952",
        ])
        + "\n",
        encoding="utf-8",
    )
    assert dispatch._parse_agy_attestation(log, requested_model="gemini-3.8-flash") == {
        "observed_provider": "agy",
        "observed_model": "gemini-3.8-flash-low",
        "provider_session_id": "f67d38d4-f220-4bc0-a216-cef594235952",
    }


def test_parse_agy_attestation_fails_closed_without_matching_witnesses(tmp_path: Path) -> None:
    log = tmp_path / "agy.log"
    log.write_text(
        "\n".join([
            'I0000 model_resolver.go:116] model alias "gemini-other" resolved to "gemini-other-low"',
            "I0000 server.go:1239] Created conversation f67d38d4-f220-4bc0-a216-cef594235952",
        ])
        + "\n",
        encoding="utf-8",
    )
    assert dispatch._parse_agy_attestation(log, requested_model="gemini-3.8-flash") == {
        "observed_provider": None,
        "observed_model": None,
        "provider_session_id": None,
    }


def test_parse_agy_attestation_uses_last_matching_attempt(tmp_path: Path) -> None:
    log = tmp_path / "agy.log"
    log.write_text(
        "\n".join([
            'I0000 model_resolver.go:116] model alias "gemini-3.8-flash" resolved to "gemini-3.8-flash-low"',
            "I0000 server.go:1239] Created conversation 11111111-1111-1111-1111-111111111111",
            'I0001 model_resolver.go:116] model alias "gemini-3.8-flash" resolved to "gemini-3.8-flash-low-v2"',
            "I0001 server.go:1239] Created conversation 22222222-2222-2222-2222-222222222222",
        ])
        + "\n",
        encoding="utf-8",
    )
    result = dispatch._parse_agy_attestation(log, requested_model="gemini-3.8-flash")
    assert result["observed_model"] == "gemini-3.8-flash-low-v2"
    assert result["provider_session_id"] == "22222222-2222-2222-2222-222222222222"


def test_background_terminal_receipt_persists_agy_attestation(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "ops"
    journal = dispatch.AgyOperationJournal(root)
    operation_id = dispatch.new_operation_id()
    prompt_path = journal.prompt_path(operation_id)
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model="gemini-3.8-flash",
        effort="low",
        prompt_sha256="0" * 64,
        runtime_revision="a" * 40,
    )
    dispatch._write_private_prompt(prompt_path, "attestation probe")

    def fake_dispatch_run(**kwargs):
        log = Path(os.environ["NEXUS_AGY_ATTESTATION_LOG"])
        log.write_text(
            "\n".join([
                'I0000 model_resolver.go:116] model alias "gemini-3.8-flash" resolved to "gemini-3.8-flash-low"',
                "I0000 server.go:1239] Created conversation f67d38d4-f220-4bc0-a216-cef594235952",
                "W1003 18:22:34.269070     491 rules.go:545] Rule file /repo/AGENTS.md truncated by 706 bytes (original 24638 bytes, limit 24000 bytes)",
            ])
            + "\n",
            encoding="utf-8",
        )
        kwargs["operation_hook"]({
            "phase": "EXECUTING",
            "attempts": 1,
            "rotations": 0,
            "account_alias_hash": "acct",
            "lease_id_hash": "lease",
        })
        return 0

    monkeypatch.setattr(dispatch, "dispatch_run", fake_dispatch_run)
    code = dispatch._run_background_operation(
        operation_id=operation_id,
        prompt_file=str(prompt_path),
        cwd=str(tmp_path),
        mode="plan",
        model="gemini-3.8-flash",
        effort="low",
        timeout=30,
        max_calls=1,
        pool_wait_timeout=1.0,
        allow=[],
        deny=[],
        temp_command_permissions=False,
        operation_root=root,
        heartbeat_interval=0.01,
    )
    record = journal.read(operation_id)
    assert code == 0
    assert record["status"] == "COMPLETED"
    assert record["observed_provider"] == "agy"
    assert record["observed_model"] == "gemini-3.8-flash-low"
    assert record["provider_session_id"] == "f67d38d4-f220-4bc0-a216-cef594235952"
    assert record["input_delivery_state"] == "TRUNCATED"
    assert record["input_delivery_source"] == "AGY_LOG"
    assert record["input_delivery_truncations"] == [
        {
            "file_name": "AGENTS.md",
            "original_bytes": 24638,
            "limit_bytes": 24000,
            "truncated_bytes": 706,
        }
    ]
    assert record["status"] == "COMPLETED"
    assert record["failure_kind"] is None
    assert "NEXUS_AGY_ATTESTATION_LOG" not in os.environ


def test_run_agy_passes_operation_local_attestation_log(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, object] = {}

    from io import StringIO

    class FakeProcess:
        def __init__(self, argv, **kwargs):
            captured["argv"] = argv
            captured["kwargs"] = kwargs
            self.stdout = StringIO("ok")
            self.stderr = StringIO("")
            self.returncode = 0

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            return self.returncode

        def terminate(self):
            self.returncode = -15

        def kill(self):
            self.returncode = -9

    log = tmp_path / "operation" / "agy.log"
    monkeypatch.setenv("NEXUS_AGY_ATTESTATION_LOG", str(log))
    monkeypatch.setattr(dispatch.shutil, "which", lambda name: "/tmp/fake-agy")
    monkeypatch.setattr(dispatch.subprocess, "Popen", FakeProcess)
    code, out, err, timed_out, _ = dispatch.run_agy(
        env={"HOME": str(tmp_path)},
        prompt="identity probe",
        cwd=str(tmp_path),
        mode="plan",
        model="gemini-3.8-flash",
        effort="low",
        timeout=30,
    )
    assert code == 0
    assert out == "ok"
    assert err == ""
    assert timed_out is False
    argv = captured["argv"]
    assert "--log-file" in argv
    assert argv[argv.index("--log-file") + 1] == str(log)
    assert log.parent.is_dir()


def test_cleanup_reconciled_lease_removes_only_exact_stale_receipt(
    tmp_path: Path, monkeypatch
) -> None:
    leases = tmp_path / "leases"
    leases.mkdir()
    monkeypatch.setattr(dispatch, "LEASES_DIR", leases)
    alias_hash = "a" * 12
    lease_hash = "b" * 12
    receipt = leases / f"{alias_hash}.receipt.json"
    receipt.write_text(
        json.dumps({
            "account_alias_hash": alias_hash,
            "lease_id_hash": lease_hash,
            "consumer_id": "agy-operation",
            "claimed_at": 1.0,
            "pid": 4242,
        })
        + "\n",
        encoding="utf-8",
    )
    record = {
        "account_alias_hash": alias_hash,
        "lease_id_hash": lease_hash,
        "pid": 4242,
        "reconciliation": {"provider_alive_after": False},
    }

    result = dispatch._cleanup_reconciled_lease(record)

    assert result == {"result": "LEASE_RECEIPT_REMOVED"}
    assert receipt.exists() is False


def test_cleanup_reconciled_lease_preserves_new_owner_receipt(tmp_path: Path, monkeypatch) -> None:
    leases = tmp_path / "leases"
    leases.mkdir()
    monkeypatch.setattr(dispatch, "LEASES_DIR", leases)
    alias_hash = "a" * 12
    receipt = leases / f"{alias_hash}.receipt.json"
    payload = {
        "account_alias_hash": alias_hash,
        "lease_id_hash": "newleasehash",
        "consumer_id": "new-worker",
        "claimed_at": 2.0,
        "pid": 9999,
    }
    receipt.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    record = {
        "account_alias_hash": alias_hash,
        "lease_id_hash": "oldleasehash",
        "pid": 4242,
        "reconciliation": {"provider_alive_after": False},
    }

    result = dispatch._cleanup_reconciled_lease(record)

    assert result["result"] == "LEASE_IDENTITY_MISMATCH_PRESERVED"
    assert json.loads(receipt.read_text(encoding="utf-8")) == payload


class _WriteScopeClaim:
    def __init__(self, home: Path) -> None:
        self.account_alias_hash = "write-scope"
        self.lease_id_hash = "lease-write"
        self.internal_id = "write-scope-account"
        self.lease = type(
            "Lease",
            (),
            {"execution_env": {"HOME": str(home), "ACCOUNT": "write-scope-account"}},
        )()
        self.released = False

    def release(self) -> None:
        self.released = True


class _WriteScopeCoordinator:
    def __init__(self, home: Path) -> None:
        self.claim = _WriteScopeClaim(home)
        self.acquire_count = 0

    def acquire_claim(self, **_kwargs):
        self.acquire_count += 1
        return self.claim


def test_accept_edits_without_write_scope_fails_before_account_claim(
    tmp_path: Path,
) -> None:
    coordinator = _WriteScopeCoordinator(tmp_path / "home")
    runner_called = False

    def runner(**_kwargs):
        nonlocal runner_called
        runner_called = True
        return 0, "unexpected", "", False, 1

    code = dispatch.dispatch_run(
        prompt="edit something",
        cwd=str(tmp_path),
        mode="accept-edits",
        coordinator=coordinator,
        run_agy_fn=runner,
    )

    assert code == 64
    assert coordinator.acquire_count == 0
    assert runner_called is False


def test_plan_without_write_scope_remains_allowed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    coordinator = _WriteScopeCoordinator(home)

    code = dispatch.dispatch_run(
        prompt="inspect only",
        cwd=str(tmp_path),
        mode="plan",
        coordinator=coordinator,
        run_agy_fn=lambda **_kwargs: (0, "ok", "", False, 1),
    )

    assert code == 0
    assert coordinator.acquire_count == 1
    assert coordinator.claim.released is True


def test_accept_edits_projects_bounded_write_scope_and_restores(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    coordinator = _WriteScopeCoordinator(home)
    settings = home / ".gemini" / "antigravity-cli" / "settings.json"

    def runner(**_kwargs):
        data = json.loads(settings.read_text(encoding="utf-8"))
        assert f"write_file({work})" in data["permissions"]["allow"]
        assert "command(*)" in data["permissions"]["allow"]
        return 0, "ok", "", False, 1

    code = dispatch.dispatch_run(
        prompt="bounded edit",
        cwd=str(work),
        mode="accept-edits",
        write_paths=[str(work)],
        temp_command_permissions=True,
        coordinator=coordinator,
        run_agy_fn=runner,
    )

    assert code == 0
    assert settings.exists() is False
    assert coordinator.claim.released is True


def test_accept_edits_replaces_stale_wildcard_policy_and_restores_exact_bytes(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    target = work / "target.py"
    coordinator = _WriteScopeCoordinator(home)
    settings = home / ".gemini" / "antigravity-cli" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    original = (
        '{\n  "profile": "keep-me",\n  "permissions": {\n'
        '    "allow": ["read_file(*)", "write_file(/stale)", "command(*)"],\n'
        '    "deny": ["command(*)", "read_file(*)", "write_file(*)"],\n'
        '    "ask": ["custom(*)"]\n  }\n}\n'
    ).encode("utf-8")
    settings.write_bytes(original)

    def runner(**_kwargs):
        data = json.loads(settings.read_text(encoding="utf-8"))
        permissions = data["permissions"]
        assert data["profile"] == "keep-me"
        assert permissions["ask"] == ["custom(*)"]
        assert f"write_file({target})" in permissions["allow"]
        assert f"read_file({work.resolve()}/**)" in permissions["allow"]
        assert "command(*)" in permissions["allow"]
        assert "read_file(*)" not in permissions["allow"]
        assert "write_file(/stale)" not in permissions["allow"]
        assert "command(*)" not in permissions["deny"]
        assert "read_file(*)" not in permissions["deny"]
        assert "write_file(*)" not in permissions["deny"]
        for rule in dispatch.TEMP_COMMAND_DENY:
            assert rule in permissions["deny"]
        return 0, "ok", "", False, 1

    code = dispatch.dispatch_run(
        prompt="bounded edit",
        cwd=str(work),
        mode="accept-edits",
        write_paths=[str(target)],
        temp_command_permissions=True,
        coordinator=coordinator,
        run_agy_fn=runner,
    )

    assert code == 0
    assert settings.read_bytes() == original
    assert coordinator.claim.released is True


def test_plan_explicit_deny_replaces_stale_allow_policy_and_restores_exact_bytes(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    coordinator = _WriteScopeCoordinator(home)
    settings = home / ".gemini" / "antigravity-cli" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    original = (
        '{\n  "profile": "keep-me",\n  "permissions": {\n'
        '    "allow": ["read_file(/stale/**)", "write_file(/stale/file.py)", "command(*)"],\n'
        '    "deny": ["command(git push)"],\n'
        '    "ask": ["custom(*)"]\n  }\n}\n'
    ).encode("utf-8")
    settings.write_bytes(original)
    explicit_deny = ["command(*)", "read_file(*)", "write_file(*)"]

    def runner(**_kwargs):
        data = json.loads(settings.read_text(encoding="utf-8"))
        permissions = data["permissions"]
        assert data["profile"] == "keep-me"
        assert permissions["ask"] == ["custom(*)"]
        assert permissions["allow"] == []
        assert permissions["deny"] == explicit_deny
        return 0, "ok", "", False, 1

    code = dispatch.dispatch_run(
        prompt="no-tools packet",
        cwd=str(work),
        mode="plan",
        deny=explicit_deny,
        coordinator=coordinator,
        run_agy_fn=runner,
    )

    assert code == 0
    assert settings.read_bytes() == original
    assert coordinator.claim.released is True


def test_accept_edits_permission_refusal_exit_zero_is_failure(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    target = work / "target.py"
    coordinator = _WriteScopeCoordinator(home)
    events: list[dict[str, object]] = []

    code = dispatch.dispatch_run(
        prompt="bounded edit",
        cwd=str(work),
        mode="accept-edits",
        write_paths=[str(target)],
        temp_command_permissions=True,
        coordinator=coordinator,
        run_agy_fn=lambda **_kwargs: (
            0,
            "Permission denied for read_file(/repo/target.py)",
            "",
            False,
            1,
        ),
        operation_hook=events.append,
    )

    assert code == 1
    assert any(event.get("failure_kind") == "PERMISSION_OR_SCOPE_ERROR" for event in events)
    assert coordinator.claim.released is True


def test_plan_text_with_permission_words_can_still_complete(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    coordinator = _WriteScopeCoordinator(home)

    code = dispatch.dispatch_run(
        prompt="explain a permission error",
        cwd=str(tmp_path),
        mode="plan",
        coordinator=coordinator,
        run_agy_fn=lambda **_kwargs: (
            0,
            "The phrase permission denied for read_file is documentation here.",
            "",
            False,
            1,
        ),
    )

    assert code == 0
    assert coordinator.claim.released is True


def test_plan_stdout_quoting_headless_denial_marker_can_still_complete(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    coordinator = _WriteScopeCoordinator(home)

    code = dispatch.dispatch_run(
        prompt="review prior permission evidence",
        cwd=str(tmp_path),
        mode="plan",
        coordinator=coordinator,
        run_agy_fn=lambda **_kwargs: (
            0,
            'Prior log quoted: Print mode: soft-denying tool confirmation "ViewFile" at step 8.',
            "",
            False,
            1,
        ),
    )

    assert code == 0
    assert coordinator.claim.released is True


def test_accept_edits_rejects_write_path_outside_cwd_before_claim(
    tmp_path: Path,
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    coordinator = _WriteScopeCoordinator(tmp_path / "home")

    code = dispatch.dispatch_run(
        prompt="bad scope",
        cwd=str(work),
        mode="accept-edits",
        write_paths=[str(outside)],
        coordinator=coordinator,
        run_agy_fn=lambda **_kwargs: (0, "unexpected", "", False, 1),
    )

    assert code == 64
    assert coordinator.acquire_count == 0


def test_accept_edits_existing_narrow_write_allow_is_supported(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    coordinator = _WriteScopeCoordinator(home)

    code = dispatch.dispatch_run(
        prompt="legacy narrow scope",
        cwd=str(work),
        mode="accept-edits",
        allow=[f"write_file({work})"],
        coordinator=coordinator,
        run_agy_fn=lambda **_kwargs: (0, "ok", "", False, 1),
    )

    assert code == 0


def test_operation_run_rebinds_current_runtime_revision(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "ops"
    journal = dispatch.AgyOperationJournal(root)
    operation_id = dispatch.new_operation_id()
    prompt_path = journal.prompt_path(operation_id)
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model="gemini-test",
        effort=None,
        prompt_sha256="0" * 64,
        runtime_revision=None,
    )
    dispatch._write_private_prompt(prompt_path, "runtime identity probe")

    monkeypatch.setattr(dispatch, "_runtime_revision", lambda: "b" * 40)

    def fake_dispatch_run(**kwargs):
        kwargs["operation_hook"]({
            "phase": "CLASSIFYING_FAILURE",
            "attempts": 1,
            "rotations": 0,
            "failure_kind": "TIMEOUT",
            "timed_out": True,
            "account_alias_hash": "acct",
            "lease_id_hash": "lease",
        })
        return 1

    monkeypatch.setattr(dispatch, "dispatch_run", fake_dispatch_run)

    code = dispatch._run_background_operation(
        operation_id=operation_id,
        prompt_file=str(prompt_path),
        cwd=str(tmp_path),
        mode="accept-edits",
        model="gemini-test",
        effort=None,
        timeout=30,
        max_calls=1,
        pool_wait_timeout=1.0,
        allow=[],
        deny=[],
        temp_command_permissions=False,
        operation_root=root,
        heartbeat_interval=0.01,
    )

    record = journal.read(operation_id)
    assert code == 1
    assert record["runtime_revision"] == "b" * 40
    assert record["status"] == "OUTCOME_UNKNOWN"


# ---------------------------------------------------------------------------
# SIGTERM terminalization regression — real subprocess, no monkeypatch signal
# ---------------------------------------------------------------------------

_CHILD_SCRIPT = textwrap.dedent("""\
    import os
    import sys
    import time
    from importlib.machinery import SourceFileLoader
    from pathlib import Path

    dispatch_path = sys.argv[1]
    op_root = Path(sys.argv[2])
    operation_id = sys.argv[3]
    ready_file = Path(sys.argv[4])
    snapshot_root = sys.argv[5]

    os.environ["NEXUS_AGY_SNAPSHOT"] = snapshot_root
    dispatch = SourceFileLoader(
        "nexus_agy_dispatch_canonical", dispatch_path
    ).load_module()

    journal = dispatch.AgyOperationJournal(op_root)
    prompt_path = journal.prompt_path(operation_id)
    dispatch._write_private_prompt(prompt_path, "sigterm probe")

    def fake_dispatch_run(**kwargs):
        # Mark the provider call as effect-capable before signalling readiness.
        kwargs["operation_hook"]({
            "phase": "EXECUTING",
            "attempts": 1,
            "rotations": 0,
        })
        ready_file.touch()
        while True:
            time.sleep(0.05)

    dispatch.dispatch_run = fake_dispatch_run

    try:
        dispatch._run_background_operation(
            operation_id=operation_id,
            prompt_file=str(prompt_path),
            cwd=str(op_root),
            mode="plan",
            model="gemini-test",
            effort="medium",
            timeout=30,
            max_calls=1,
            pool_wait_timeout=1.0,
            allow=[],
            deny=[],
            temp_command_permissions=False,
            operation_root=op_root,
            heartbeat_interval=0.01,
        )
    except BaseException:
        pass
""")


def test_sigterm_during_dispatch_persists_supervisor_signal_outcome(
    tmp_path: Path,
) -> None:
    """Real subprocess receives SIGTERM mid-dispatch; durable record must reflect it."""
    op_root = tmp_path / "ops"    # Pre-create the operation in the *parent* process so the child can use it.
    journal = dispatch.AgyOperationJournal(op_root)
    operation_id = dispatch.new_operation_id()
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model="gemini-test",
        effort="medium",
        prompt_sha256="0" * 64,
        runtime_revision="a" * 40,
    )

    ready_file = tmp_path / "ready"
    script_file = tmp_path / "child.py"
    script_file.write_text(_CHILD_SCRIPT, encoding="utf-8")

    child = subprocess.Popen(
        [
            sys.executable,
            str(script_file),
            str(DISPATCH_PATH),
            str(op_root),
            operation_id,
            str(ready_file),
            str(ROOT),
        ],
        cwd=str(tmp_path),
    )

    # Wait for the child to enter the fake dispatch (readiness sentinel).
    deadline = time.monotonic() + 20.0
    while not ready_file.exists():
        if time.monotonic() > deadline:
            child.kill()
            child.wait()
            raise TimeoutError("child never signalled readiness")
        time.sleep(0.05)

    # Send SIGTERM and wait for the child to exit.
    os.kill(child.pid, signal.SIGTERM)
    child.wait(timeout=10)

    record = journal.read(operation_id)
    assert record["status"] == "OUTCOME_UNKNOWN"
    assert record["phase"] == "TERMINAL"
    assert record["finished_at"] is not None
    assert record["failure_kind"] == "SUPERVISOR_SIGNAL:SIGTERM"
    assert record["reconciliation"]["result"] == "SUPERVISOR_SIGNAL_WITH_UNKNOWN_PROVIDER_EFFECT"
    assert record["reconciliation"]["retry_permitted"] is False


# ---------------------------------------------------------------------------
# Unit test: _run_background_operation restores prior SIGTERM/SIGINT handlers
# ---------------------------------------------------------------------------


def test_run_background_operation_restores_signal_handlers_after_normal_completion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Signal handlers installed by _run_background_operation are restored on exit."""
    root = tmp_path / "ops"
    journal = dispatch.AgyOperationJournal(root)
    operation_id = dispatch.new_operation_id()
    prompt_path = journal.prompt_path(operation_id)
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model="gemini-test",
        effort="low",
        prompt_sha256="0" * 64,
        runtime_revision="a" * 40,
    )
    dispatch._write_private_prompt(prompt_path, "handler restore probe")

    # Record the handlers that were in place *before* calling _run_background_operation.
    sentinel_term = signal.getsignal(signal.SIGTERM)
    sentinel_int = signal.getsignal(signal.SIGINT)

    captured_during: dict[str, object] = {}

    def recording_dispatch_run(**kwargs):
        captured_during["term"] = signal.getsignal(signal.SIGTERM)
        captured_during["int"] = signal.getsignal(signal.SIGINT)
        return 0

    monkeypatch.setattr(dispatch, "dispatch_run", recording_dispatch_run)

    dispatch._run_background_operation(
        operation_id=operation_id,
        prompt_file=str(prompt_path),
        cwd=str(tmp_path),
        mode="plan",
        model="gemini-test",
        effort="low",
        timeout=30,
        max_calls=1,
        pool_wait_timeout=1.0,
        allow=[],
        deny=[],
        temp_command_permissions=False,
        operation_root=root,
        heartbeat_interval=0.01,
    )

    # Handlers active during dispatch must differ from the originals (they were replaced).
    assert captured_during["term"] is not sentinel_term
    assert captured_during["int"] is not sentinel_int

    # After return, the original handlers must be restored exactly.
    assert signal.getsignal(signal.SIGTERM) is sentinel_term
    assert signal.getsignal(signal.SIGINT) is sentinel_int


_STARTUP_CHILD_SCRIPT = textwrap.dedent("""\
    import os
    import sys
    import time
    from importlib.machinery import SourceFileLoader
    from pathlib import Path

    dispatch_path = sys.argv[1]
    op_root = Path(sys.argv[2])
    operation_id = sys.argv[3]
    ready_file = Path(sys.argv[4])
    snapshot_root = sys.argv[5]

    os.environ["NEXUS_AGY_SNAPSHOT"] = snapshot_root
    dispatch = SourceFileLoader(
        "nexus_agy_dispatch_startup_probe", dispatch_path
    ).load_module()
    journal = dispatch.AgyOperationJournal(op_root)
    prompt_path = journal.prompt_path(operation_id)
    dispatch._write_private_prompt(prompt_path, "startup sigterm probe")

    def slow_runtime_revision():
        ready_file.touch()
        while True:
            time.sleep(0.05)

    dispatch._runtime_revision = slow_runtime_revision
    dispatch.dispatch_run = lambda **kwargs: 0

    try:
        dispatch._run_background_operation(
            operation_id=operation_id,
            prompt_file=str(prompt_path),
            cwd=str(op_root),
            mode="plan",
            model="gemini-test",
            effort=None,
            timeout=30,
            max_calls=1,
            pool_wait_timeout=1.0,
            allow=[],
            deny=[],
            temp_command_permissions=False,
            operation_root=op_root,
            heartbeat_interval=0.01,
        )
    except BaseException:
        pass
""")


def test_sigterm_during_startup_persists_supervisor_signal_outcome(
    tmp_path: Path,
) -> None:
    """SIGTERM during startup must terminalize before provider dispatch begins."""
    op_root = tmp_path / "startup-ops"
    journal = dispatch.AgyOperationJournal(op_root)
    operation_id = dispatch.new_operation_id()
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model="gemini-test",
        effort=None,
        prompt_sha256="0" * 64,
        runtime_revision="a" * 40,
    )

    ready_file = tmp_path / "startup-ready"
    script_file = tmp_path / "startup-child.py"
    script_file.write_text(_STARTUP_CHILD_SCRIPT, encoding="utf-8")
    child = subprocess.Popen(
        [
            sys.executable,
            str(script_file),
            str(DISPATCH_PATH),
            str(op_root),
            operation_id,
            str(ready_file),
            str(ROOT),
        ],
        cwd=str(tmp_path),
    )

    deadline = time.monotonic() + 20.0
    while not ready_file.exists():
        if time.monotonic() > deadline:
            child.kill()
            child.wait()
            raise TimeoutError("startup child never signalled readiness")
        time.sleep(0.05)

    os.kill(child.pid, signal.SIGTERM)
    child.wait(timeout=10)

    record = journal.read(operation_id)
    assert record["status"] == "FAILED"
    assert record["phase"] == "TERMINAL"
    assert record["finished_at"] is not None
    assert record["failure_kind"] == "SUPERVISOR_SIGNAL_PRE_PROVIDER:SIGTERM"
    assert record["reconciliation"]["result"] == "SUPERVISOR_SIGNAL_BEFORE_PROVIDER"
    assert record["reconciliation"]["retry_permitted"] is False


def test_pre_provider_wrapper_exception_is_not_outcome_unknown(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "wrapper-error-ops"
    journal = dispatch.AgyOperationJournal(root)
    operation_id = dispatch.new_operation_id()
    prompt_path = journal.prompt_path(operation_id)
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model="gemini-test",
        effort=None,
        prompt_sha256="0" * 64,
        runtime_revision="a" * 40,
    )
    dispatch._write_private_prompt(prompt_path, "wrapper exception probe")

    def fail_runtime_revision():
        raise RuntimeError("runtime revision unavailable")

    monkeypatch.setattr(dispatch, "_runtime_revision", fail_runtime_revision)

    with pytest.raises(RuntimeError, match="runtime revision unavailable"):
        dispatch._run_background_operation(
            operation_id=operation_id,
            prompt_file=str(prompt_path),
            cwd=str(tmp_path),
            mode="plan",
            model="gemini-test",
            effort=None,
            timeout=30,
            max_calls=1,
            pool_wait_timeout=1.0,
            allow=[],
            deny=[],
            temp_command_permissions=False,
            operation_root=root,
            heartbeat_interval=0.01,
        )

    record = journal.read(operation_id)
    assert record["status"] == "FAILED"
    assert record["phase"] == "TERMINAL"
    assert record["failure_kind"] == "WRAPPER_EXCEPTION_PRE_PROVIDER:RuntimeError"
    assert record["reconciliation"]["result"] == "WRAPPER_EXCEPTION_BEFORE_PROVIDER"
    assert record["reconciliation"]["retry_permitted"] is False


# ---------------------------------------------------------------------------
# Issue #1342: explicit standalone-clone fallback for linked worktrees
# ---------------------------------------------------------------------------


def _fallback_git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    return proc.stdout.strip()


def _make_fallback_fixture(tmp_path: Path) -> tuple[Path, Path, str]:
    source = tmp_path / "source"
    source.mkdir()
    _fallback_git(source, "init", "-q")
    _fallback_git(source, "config", "user.email", "issue1342@example.invalid")
    _fallback_git(source, "config", "user.name", "Issue 1342")
    (source / "tracked.txt").write_text("one\n", encoding="utf-8")
    _fallback_git(source, "add", "tracked.txt")
    _fallback_git(source, "commit", "-q", "-m", "base")
    (source / "tracked.txt").write_text("two\n", encoding="utf-8")
    _fallback_git(source, "add", "tracked.txt")
    _fallback_git(source, "commit", "-q", "-m", "head")
    _fallback_git(
        source,
        "remote",
        "add",
        "origin",
        "https://github.com/James3014/Nexus-new.git",
    )
    linked = tmp_path / "linked"
    _fallback_git(source, "worktree", "add", "-q", "-b", "linked-test", str(linked), "HEAD")
    return source, linked, _fallback_git(linked, "rev-parse", "HEAD")


def test_linked_worktree_detection_does_not_flag_standalone_repo(tmp_path: Path) -> None:
    source, linked, _sha = _make_fallback_fixture(tmp_path)

    assert dispatch._is_linked_worktree(str(linked)) is True
    assert dispatch._is_linked_worktree(str(source)) is False


def test_linked_worktree_without_explicit_fallback_fails_closed(tmp_path: Path) -> None:
    _source, linked, _sha = _make_fallback_fixture(tmp_path)

    with pytest.raises(dispatch.WorktreeFallbackError, match="WORKTREE_NO_FALLBACK_REQUESTED"):
        dispatch._resolve_cwd_for_dispatch(
            requested_cwd=str(linked),
            fallback_clone_path=None,
        )


def test_explicit_fallback_creates_exact_independent_clone(tmp_path: Path) -> None:
    source, linked, sha = _make_fallback_fixture(tmp_path)
    target = tmp_path / "fallback"

    resolved = Path(
        dispatch._resolve_cwd_for_dispatch(
            requested_cwd=str(linked),
            fallback_clone_path=str(target),
        )
    )

    assert resolved == target.resolve()
    assert (resolved / ".git").is_dir()
    assert _fallback_git(resolved, "rev-parse", "HEAD") == sha
    assert _fallback_git(resolved, "remote", "get-url", "origin") == (
        "https://github.com/James3014/Nexus-new.git"
    )
    assert _fallback_git(resolved, "status", "--porcelain") == ""
    assert (
        Path(_fallback_git(resolved, "rev-parse", "--git-common-dir")).resolve()
        != (source / ".git").resolve()
    )
    assert (linked / "tracked.txt").read_text(encoding="utf-8") == "two\n"


def test_exact_clean_fallback_clone_can_be_reused(tmp_path: Path) -> None:
    _source, linked, _sha = _make_fallback_fixture(tmp_path)
    target = tmp_path / "fallback"
    first = dispatch._prepare_standalone_clone_fallback(
        source_cwd=str(linked),
        fallback_path=str(target),
    )
    marker = target / ".git" / "issue1342-marker"
    marker.write_text("same clone\n", encoding="utf-8")

    second = dispatch._prepare_standalone_clone_fallback(
        source_cwd=str(linked),
        fallback_path=str(target),
    )

    assert first == second
    assert marker.read_text(encoding="utf-8") == "same clone\n"


def test_dirty_existing_fallback_clone_is_rejected(tmp_path: Path) -> None:
    _source, linked, _sha = _make_fallback_fixture(tmp_path)
    target = tmp_path / "fallback"
    dispatch._prepare_standalone_clone_fallback(
        source_cwd=str(linked),
        fallback_path=str(target),
    )
    (target / "tracked.txt").write_text("dirty\n", encoding="utf-8")

    with pytest.raises(dispatch.WorktreeFallbackError, match="FALLBACK_CLONE_DIRTY"):
        dispatch._prepare_standalone_clone_fallback(
            source_cwd=str(linked),
            fallback_path=str(target),
        )


def test_wrong_remote_existing_fallback_clone_is_rejected(tmp_path: Path) -> None:
    _source, linked, _sha = _make_fallback_fixture(tmp_path)
    target = tmp_path / "fallback"
    dispatch._prepare_standalone_clone_fallback(
        source_cwd=str(linked),
        fallback_path=str(target),
    )
    _fallback_git(target, "remote", "set-url", "origin", "https://example.invalid/other.git")

    with pytest.raises(dispatch.WorktreeFallbackError, match="FALLBACK_CLONE_REMOTE_MISMATCH"):
        dispatch._prepare_standalone_clone_fallback(
            source_cwd=str(linked),
            fallback_path=str(target),
        )


def test_wrong_base_existing_fallback_clone_is_rejected(tmp_path: Path) -> None:
    _source, linked, _sha = _make_fallback_fixture(tmp_path)
    target = tmp_path / "fallback"
    dispatch._prepare_standalone_clone_fallback(
        source_cwd=str(linked),
        fallback_path=str(target),
    )
    _fallback_git(target, "checkout", "-q", "HEAD~1")

    with pytest.raises(dispatch.WorktreeFallbackError, match="FALLBACK_CLONE_BASE_MISMATCH"):
        dispatch._prepare_standalone_clone_fallback(
            source_cwd=str(linked),
            fallback_path=str(target),
        )


def test_fallback_path_collision_file_is_rejected(tmp_path: Path) -> None:
    _source, linked, _sha = _make_fallback_fixture(tmp_path)
    target = tmp_path / "fallback"
    target.write_text("collision\n", encoding="utf-8")

    with pytest.raises(
        dispatch.WorktreeFallbackError,
        match="FALLBACK_CLONE_PATH_COLLISION_NOT_DIR",
    ):
        dispatch._prepare_standalone_clone_fallback(
            source_cwd=str(linked),
            fallback_path=str(target),
        )


def test_normal_repo_without_fallback_keeps_original_cwd(tmp_path: Path) -> None:
    source, _linked, _sha = _make_fallback_fixture(tmp_path)

    assert dispatch._resolve_cwd_for_dispatch(
        requested_cwd=str(source),
        fallback_clone_path=None,
    ) == str(source)


def test_write_scope_projects_against_effective_fallback_clone(tmp_path: Path) -> None:
    _source, linked, _sha = _make_fallback_fixture(tmp_path)
    target = tmp_path / "fallback"
    effective = dispatch._resolve_cwd_for_dispatch(
        requested_cwd=str(linked),
        fallback_clone_path=str(target),
    )

    rules = dispatch._project_write_permissions(
        cwd=effective,
        mode="accept-edits",
        write_paths=["scripts/ops/nexus-agy-dispatch"],
        allow_rules=[],
    )

    assert rules == [f"write_file({target.resolve() / 'scripts/ops/nexus-agy-dispatch'})"]
    assert str(linked) not in rules[0]


def test_background_main_binds_operation_to_effective_clone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _source, linked, _sha = _make_fallback_fixture(tmp_path)
    target = tmp_path / "fallback"
    captured: dict[str, object] = {}

    def fake_spawn(**kwargs):
        captured.update(kwargs)
        return {"operation_id": "agyop_" + ("a" * 32)}

    monkeypatch.setattr(dispatch, "_spawn_background_operation", fake_spawn)
    monkeypatch.setattr(dispatch, "_print_operation", lambda record: None)

    rc = dispatch.main([
        "--background",
        "--cwd",
        str(linked),
        "--fallback-clone",
        str(target),
        "--prompt",
        "bounded fallback test",
        "--write-path",
        "scripts/ops/nexus-agy-dispatch",
        "--operation-root",
        str(tmp_path / "operations"),
    ])

    assert rc == 0
    assert Path(str(captured["cwd"])) == target.resolve()
    assert captured["write_paths"] == ["scripts/ops/nexus-agy-dispatch"]


def test_dirty_linked_source_is_rejected_before_fallback_clone(tmp_path: Path) -> None:
    _source, linked, _sha = _make_fallback_fixture(tmp_path)
    (linked / "tracked.txt").write_text("dirty source\n", encoding="utf-8")

    with pytest.raises(dispatch.WorktreeFallbackError, match="FALLBACK_SOURCE_DIRTY"):
        dispatch._prepare_standalone_clone_fallback(
            source_cwd=str(linked),
            fallback_path=str(tmp_path / "fallback"),
        )


def test_fallback_clone_inside_source_is_rejected(tmp_path: Path) -> None:
    _source, linked, _sha = _make_fallback_fixture(tmp_path)

    with pytest.raises(dispatch.WorktreeFallbackError, match="FALLBACK_CLONE_INSIDE_SOURCE"):
        dispatch._prepare_standalone_clone_fallback(
            source_cwd=str(linked),
            fallback_path=str(linked / ".fallback-clone"),
        )


def test_unsupported_effort_for_claude_opus_fails_before_claim(tmp_path: Path) -> None:
    coordinator = _WriteScopeCoordinator(tmp_path / "home")
    events: list[dict[str, object]] = []

    code = dispatch.dispatch_run(
        prompt="run model",
        cwd=str(tmp_path),
        mode="plan",
        model="claude-opus-4-6",
        effort="low",
        coordinator=coordinator,
        operation_hook=events.append,
    )

    assert code == 64
    assert coordinator.acquire_count == 0
    assert any(
        e.get("failure_kind")
        == "DISPATCH_MODEL_CONTRACT_REJECTED:UNSUPPORTED_EFFORT_FOR_MODEL:claude-opus-4-6:low"
        and e.get("provider_effect") is False
        for e in events
    )


def test_provider_exit_invalid_model_selection_classified_as_model_contract_rejected(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    coordinator = _WriteScopeCoordinator(home)
    events: list[dict[str, object]] = []

    code = dispatch.dispatch_run(
        prompt="run model",
        cwd=str(tmp_path),
        mode="plan",
        model="claude-opus-4-6",
        coordinator=coordinator,
        run_agy_fn=lambda **_kwargs: (
            1,
            "",
            'error: invalid model selection (--model "claude-opus-4-6" --effort "low"): --effort is not supported for model "claude-opus-4-6"\n',
            False,
            50,
        ),
        operation_hook=events.append,
    )

    assert code == 1
    assert any(e.get("failure_kind") == "DISPATCH_MODEL_CONTRACT_REJECTED" for e in events)
    assert coordinator.acquire_count == 1
    assert coordinator.claim.released is True


def test_headless_tool_permission_denial_classified_as_failure(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    target = work / "file.txt"
    coordinator = _WriteScopeCoordinator(home)
    events: list[dict[str, object]] = []

    code = dispatch.dispatch_run(
        prompt="make edit",
        cwd=str(work),
        mode="accept-edits",
        write_paths=[str(target)],
        coordinator=coordinator,
        run_agy_fn=lambda **_kwargs: (
            0,
            "",
            'jetski: no output produced — a tool required the "command" permission that headless mode cannot prompt for, so it was auto-denied.\n',
            False,
            100,
        ),
        operation_hook=events.append,
    )

    assert code == 1
    assert any(e.get("failure_kind") == "HEADLESS_TOOL_PERMISSION_DENIED" for e in events)
    assert coordinator.acquire_count == 1
    assert coordinator.claim.released is True


def test_run_agy_timeline_and_baseline_effects(tmp_path: Path, monkeypatch) -> None:
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "-C", str(work), "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(work), "config", "user.email", "test@test.com"], check=True)
    subprocess.run(["git", "-C", str(work), "config", "user.name", "Test"], check=True)
    (work / "tracked.txt").write_text("initial", encoding="utf-8")
    subprocess.run(["git", "-C", str(work), "add", "tracked.txt"], check=True)
    subprocess.run(
        ["git", "-C", str(work), "commit", "-m", "init"], check=True, capture_output=True
    )

    # Create pre-existing dirty file in worktree (donor change)
    (work / "pre_existing_dirty.txt").write_text("dirty before launch", encoding="utf-8")

    # Create fake agy script
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_agy = bin_dir / "agy"
    script = """#!/usr/bin/env python3
import sys, time, os
from pathlib import Path

# Write stderr diagnostics first
sys.stderr.write("[DEBUG] Bootstrap initializing...\\n")
sys.stderr.flush()
time.sleep(0.1)

# Write stdout model stream
sys.stdout.write("Model output streaming line 1\\n")
sys.stdout.flush()
time.sleep(0.1)

# Modify a new file
cwd = Path(os.environ.get("AGY_TEST_CWD", "."))
(cwd / "new_effect.txt").write_text("created by agy\\n", encoding="utf-8")
time.sleep(0.1)
sys.exit(0)
"""
    fake_agy.write_text(script, encoding="utf-8")
    fake_agy.chmod(0o755)

    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    monkeypatch.setenv("AGY_TEST_CWD", str(work))

    events: list[dict[str, object]] = []
    code, out, err, timed_out, wall_ms = dispatch.run_agy(
        env=os.environ.copy(),
        prompt="hello",
        cwd=str(work),
        mode="accept-edits",
        model="gemini-3.8-flash-high",
        effort=None,
        timeout=10,
        operation_hook=events.append,
    )

    assert code == 0
    assert "Model output streaming line 1" in out
    assert "[DEBUG] Bootstrap initializing..." in err

    # Verify first_stream_activity_at and first_effect_at were recorded
    stream_events = [e for e in events if "first_stream_activity_at" in e]
    assert len(stream_events) >= 1

    effect_events = [e for e in events if "first_effect_at" in e]
    assert len(effect_events) >= 1
    assert "time_to_first_effect_ms" in effect_events[0]

    # Verify process state transitions
    running_events = [e for e in events if e.get("provider_process_state") == "RUNNING"]
    assert len(running_events) >= 1
    exited_events = [e for e in events if e.get("provider_process_state") == "EXITED"]
    assert len(exited_events) >= 1


def test_run_agy_ingests_provider_stream_from_attestation_log(tmp_path: Path, monkeypatch) -> None:
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "-C", str(work), "init"], check=True, capture_output=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_agy = bin_dir / "agy"
    fake_agy.write_text(
        "#!"
        + sys.executable
        + "\nimport sys, time\n"
        + "from pathlib import Path\n"
        + "log = Path(sys.argv[sys.argv.index('--log-file') + 1])\n"
        + "log.write_text('I http_helpers.go:315] URL: https://example/v1internal:streamGenerateContent?alt=sse\\n')\n"
        + "time.sleep(0.2)\n",
        encoding="utf-8",
    )
    fake_agy.chmod(0o700)
    log = tmp_path / "agy.log"
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    monkeypatch.setenv("NEXUS_AGY_ATTESTATION_LOG", str(log))

    events: list[dict[str, object]] = []
    code, _out, _err, _timed_out, _wall_ms = dispatch.run_agy(
        env=os.environ.copy(),
        prompt="stream only",
        cwd=str(work),
        mode="plan",
        model=None,
        effort=None,
        timeout=5,
        operation_hook=events.append,
    )

    assert code == 0
    assert any(event.get("first_stream_activity_at") for event in events)
    assert any(event.get("provider_stream_last_activity_at") for event in events)


def test_run_agy_coding_watchdog_classifies_provider_stalled(tmp_path: Path, monkeypatch) -> None:
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "-C", str(work), "init"], check=True, capture_output=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_agy = bin_dir / "agy"
    fake_agy.write_text(
        "#!" + sys.executable + "\nimport time\ntime.sleep(2)\n",
        encoding="utf-8",
    )
    fake_agy.chmod(0o700)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    monkeypatch.setenv("NEXUS_AGY_PROVIDER_STALL_SECONDS", "0.15")
    monkeypatch.setenv("NEXUS_AGY_STREAM_NO_PROGRESS_SECONDS", "5")

    code, _out, err, timed_out, _wall_ms = dispatch.run_agy(
        env=os.environ.copy(),
        prompt="must edit",
        cwd=str(work),
        mode="accept-edits",
        model=None,
        effort=None,
        timeout=5,
        expect_coding_progress=True,
    )

    assert code != 0
    assert timed_out is False
    assert "NEXUS_AGY_NON_PROGRESS:PROVIDER_STALLED" in err
    assert (
        dispatch.classify_failure(code, "", err, timed_out)
        == dispatch.AccountFailureKind.PROVIDER_STALLED
    )


def test_run_agy_coding_watchdog_classifies_stream_without_effect(
    tmp_path: Path, monkeypatch
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "-C", str(work), "init"], check=True, capture_output=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_agy = bin_dir / "agy"
    fake_agy.write_text(
        "#!"
        + sys.executable
        + "\nimport sys, time\n"
        + "from pathlib import Path\n"
        + "log = Path(sys.argv[sys.argv.index('--log-file') + 1])\n"
        + "log.write_text('I http_helpers.go:315] URL: https://example/v1internal:streamGenerateContent?alt=sse\\n')\n"
        + "time.sleep(2)\n",
        encoding="utf-8",
    )
    fake_agy.chmod(0o700)
    log = tmp_path / "agy.log"
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    monkeypatch.setenv("NEXUS_AGY_ATTESTATION_LOG", str(log))
    monkeypatch.setenv("NEXUS_AGY_PROVIDER_STALL_SECONDS", "5")
    monkeypatch.setenv("NEXUS_AGY_STREAM_NO_PROGRESS_SECONDS", "0.15")

    events: list[dict[str, object]] = []
    code, _out, err, timed_out, _wall_ms = dispatch.run_agy(
        env=os.environ.copy(),
        prompt="must edit",
        cwd=str(work),
        mode="accept-edits",
        model=None,
        effort=None,
        timeout=5,
        operation_hook=events.append,
        expect_coding_progress=True,
    )

    assert code != 0
    assert timed_out is False
    assert "NEXUS_AGY_NON_PROGRESS:PROVIDER_STREAM_NO_PROGRESS" in err
    assert any(event.get("first_stream_activity_at") for event in events)
    assert (
        dispatch.classify_failure(code, "", err, timed_out)
        == dispatch.AccountFailureKind.PROVIDER_STREAM_NO_PROGRESS
    )


def test_run_agy_tool_activity_resets_stream_no_progress_watchdog(
    tmp_path: Path, monkeypatch
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "-C", str(work), "init"], check=True, capture_output=True)
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_agy = bin_dir / "agy"
    session_id = "11111111-2222-3333-4444-555555555555"
    fake_agy.write_text(
        "#!"
        + sys.executable
        + "\nimport json, os, sys, time\n"
        + "from pathlib import Path\n"
        + f"session = {session_id!r}\n"
        + "log = Path(sys.argv[sys.argv.index('--log-file') + 1])\n"
        + "log.write_text('I server.go:1263] Created conversation ' + session + '\\n'"
        + " + 'I http_helpers.go:315] URL: https://example/v1internal:streamGenerateContent?alt=sse\\n')\n"
        + "transcript = Path(os.environ['HOME']) / '.gemini' / 'antigravity-cli' / 'brain' / session / '.system_generated' / 'logs' / 'transcript_full.jsonl'\n"
        + "transcript.parent.mkdir(parents=True, exist_ok=True)\n"
        + "time.sleep(0.18)\n"
        + "transcript.write_text(json.dumps({'source':'MODEL','type':'PLANNER_RESPONSE','tool_calls':[{'name':'view_file','args':{}}]}) + '\\n')\n"
        + "time.sleep(0.18)\n"
        + "print('DONE')\n",
        encoding="utf-8",
    )
    fake_agy.chmod(0o700)
    log = tmp_path / "agy.log"
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    monkeypatch.setenv("NEXUS_AGY_ATTESTATION_LOG", str(log))
    env = os.environ.copy()
    env["HOME"] = str(home)

    events: list[dict[str, object]] = []
    code, out, err, timed_out, _wall_ms = dispatch.run_agy(
        env=env,
        prompt="read and reason",
        cwd=str(work),
        mode="accept-edits",
        model=None,
        effort=None,
        timeout=5,
        operation_hook=events.append,
        expect_coding_progress=True,
        provider_stall_seconds=0.5,
        stream_no_progress_seconds=0.25,
    )

    assert code == 0
    assert timed_out is False
    assert "DONE" in out
    assert "NEXUS_AGY_NON_PROGRESS" not in err
    tool_events = [event for event in events if event.get("tool_event_count")]
    assert tool_events
    assert tool_events[-1]["tool_event_count"] == 1
    assert tool_events[-1]["first_tool_activity_at"]
    assert tool_events[-1]["last_progress_activity_at"]


def test_run_agy_pre_effect_tool_event_budget_classifies_thrash(
    tmp_path: Path, monkeypatch
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "-C", str(work), "init"], check=True, capture_output=True)
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_agy = bin_dir / "agy"
    session_id = "22222222-3333-4444-5555-666666666666"
    fake_agy.write_text(
        "#!"
        + sys.executable
        + "\nimport json, os, sys, time\n"
        + "from pathlib import Path\n"
        + f"session = {session_id!r}\n"
        + "log = Path(sys.argv[sys.argv.index('--log-file') + 1])\n"
        + "log.write_text('I server.go:1263] Created conversation ' + session + '\\n'"
        + " + 'I http_helpers.go:315] URL: https://example/v1internal:streamGenerateContent?alt=sse\\n')\n"
        + "transcript = Path(os.environ['HOME']) / '.gemini' / 'antigravity-cli' / 'brain' / session / '.system_generated' / 'logs' / 'transcript_full.jsonl'\n"
        + "transcript.parent.mkdir(parents=True, exist_ok=True)\n"
        + "transcript.write_text(json.dumps({'source':'MODEL','type':'PLANNER_RESPONSE','tool_calls':[{'name':'view_file','args':{}},{'name':'run_command','args':{}},{'name':'view_file','args':{}}]}) + '\\n')\n"
        + "time.sleep(2)\n",
        encoding="utf-8",
    )
    fake_agy.chmod(0o700)
    log = tmp_path / "agy.log"
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    monkeypatch.setenv("NEXUS_AGY_ATTESTATION_LOG", str(log))
    env = os.environ.copy()
    env["HOME"] = str(home)

    events: list[dict[str, object]] = []
    code, _out, err, timed_out, _wall_ms = dispatch.run_agy(
        env=env,
        prompt="bounded coding",
        cwd=str(work),
        mode="accept-edits",
        model=None,
        effort=None,
        timeout=5,
        operation_hook=events.append,
        expect_coding_progress=True,
        provider_stall_seconds=0.5,
        stream_no_progress_seconds=5,
        pre_effect_max_seconds=5,
        pre_effect_max_tool_events=3,
    )

    assert code != 0
    assert timed_out is False
    assert "NEXUS_AGY_NON_PROGRESS:PRE_EFFECT_TOOL_THRASH" in err
    assert any(event.get("tool_event_count") == 3 for event in events)
    assert not any(event.get("first_effect_at") for event in events)
    assert (
        dispatch.classify_failure(code, "", err, timed_out)
        == dispatch.AccountFailureKind.PRE_EFFECT_TOOL_THRASH
    )


def test_run_agy_pre_effect_time_budget_classifies_thrash(tmp_path: Path, monkeypatch) -> None:
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "-C", str(work), "init"], check=True, capture_output=True)
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_agy = bin_dir / "agy"
    session_id = "33333333-4444-5555-6666-777777777777"
    fake_agy.write_text(
        "#!"
        + sys.executable
        + "\nimport json, os, sys, time\n"
        + "from pathlib import Path\n"
        + f"session = {session_id!r}\n"
        + "log = Path(sys.argv[sys.argv.index('--log-file') + 1])\n"
        + "log.write_text('I server.go:1263] Created conversation ' + session + '\\n'"
        + " + 'I http_helpers.go:315] URL: https://example/v1internal:streamGenerateContent?alt=sse\\n')\n"
        + "transcript = Path(os.environ['HOME']) / '.gemini' / 'antigravity-cli' / 'brain' / session / '.system_generated' / 'logs' / 'transcript_full.jsonl'\n"
        + "transcript.parent.mkdir(parents=True, exist_ok=True)\n"
        + "transcript.write_text(json.dumps({'source':'MODEL','type':'PLANNER_RESPONSE','tool_calls':[{'name':'view_file','args':{}}]}) + '\\n')\n"
        + "time.sleep(2)\n",
        encoding="utf-8",
    )
    fake_agy.chmod(0o700)
    log = tmp_path / "agy.log"
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    monkeypatch.setenv("NEXUS_AGY_ATTESTATION_LOG", str(log))
    env = os.environ.copy()
    env["HOME"] = str(home)

    code, _out, err, timed_out, _wall_ms = dispatch.run_agy(
        env=env,
        prompt="bounded coding",
        cwd=str(work),
        mode="accept-edits",
        model=None,
        effort=None,
        timeout=5,
        expect_coding_progress=True,
        provider_stall_seconds=0.5,
        stream_no_progress_seconds=5,
        pre_effect_max_seconds=0.15,
        pre_effect_max_tool_events=100,
    )

    assert code != 0
    assert timed_out is False
    assert "NEXUS_AGY_NON_PROGRESS:PRE_EFFECT_TOOL_THRASH" in err


def test_run_agy_source_effect_before_pre_effect_budget_prevents_false_positive(
    tmp_path: Path, monkeypatch
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "-C", str(work), "init"], check=True, capture_output=True)
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    effect = work / "effect.txt"
    fake_agy = bin_dir / "agy"
    session_id = "44444444-5555-6666-7777-888888888888"
    fake_agy.write_text(
        "#!"
        + sys.executable
        + "\nimport json, os, sys, time\n"
        + "from pathlib import Path\n"
        + f"session = {session_id!r}\n"
        + "log = Path(sys.argv[sys.argv.index('--log-file') + 1])\n"
        + "log.write_text('I server.go:1263] Created conversation ' + session + '\\n'"
        + " + 'I http_helpers.go:315] URL: https://example/v1internal:streamGenerateContent?alt=sse\\n')\n"
        + "transcript = Path(os.environ['HOME']) / '.gemini' / 'antigravity-cli' / 'brain' / session / '.system_generated' / 'logs' / 'transcript_full.jsonl'\n"
        + "transcript.parent.mkdir(parents=True, exist_ok=True)\n"
        + "transcript.write_text(json.dumps({'source':'MODEL','type':'PLANNER_RESPONSE','tool_calls':[{'name':'write_file','args':{}}]}) + '\\n')\n"
        + "time.sleep(0.1)\n"
        + "Path(os.environ['AGY_EFFECT_PATH']).write_text('effect')\n"
        + "time.sleep(0.3)\n",
        encoding="utf-8",
    )
    fake_agy.chmod(0o700)
    log = tmp_path / "agy.log"
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    monkeypatch.setenv("NEXUS_AGY_ATTESTATION_LOG", str(log))
    env = os.environ.copy()
    env["HOME"] = str(home)
    env["AGY_EFFECT_PATH"] = str(effect)

    events: list[dict[str, object]] = []
    code, _out, err, timed_out, _wall_ms = dispatch.run_agy(
        env=env,
        prompt="write once",
        cwd=str(work),
        mode="accept-edits",
        model=None,
        effort=None,
        timeout=5,
        operation_hook=events.append,
        expect_coding_progress=True,
        provider_stall_seconds=0.5,
        stream_no_progress_seconds=5,
        pre_effect_max_seconds=0.2,
        pre_effect_max_tool_events=100,
    )

    assert code == 0
    assert timed_out is False
    assert effect.read_text(encoding="utf-8") == "effect"
    assert "NEXUS_AGY_NON_PROGRESS:PRE_EFFECT_TOOL_THRASH" not in err
    assert any(event.get("first_effect_at") for event in events)


def test_run_agy_plan_mode_exempt_from_pre_effect_budget_even_if_expect_coding_progress_passed(
    tmp_path: Path, monkeypatch
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "-C", str(work), "init"], check=True, capture_output=True)
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_agy = bin_dir / "agy"
    session_id = "55555555-6666-7777-8888-999999999999"
    fake_agy.write_text(
        "#!"
        + sys.executable
        + "\nimport json, os, sys, time\n"
        + "from pathlib import Path\n"
        + f"session = {session_id!r}\n"
        + "log = Path(sys.argv[sys.argv.index('--log-file') + 1])\n"
        + "log.write_text('I server.go:1263] Created conversation ' + session + '\\n'"
        + " + 'I http_helpers.go:315] URL: https://example/v1internal:streamGenerateContent?alt=sse\\n')\n"
        + "transcript = Path(os.environ['HOME']) / '.gemini' / 'antigravity-cli' / 'brain' / session / '.system_generated' / 'logs' / 'transcript_full.jsonl'\n"
        + "transcript.parent.mkdir(parents=True, exist_ok=True)\n"
        + "transcript.write_text(json.dumps({'source':'MODEL','type':'PLANNER_RESPONSE','tool_calls':[{'name':'view_file','args':{}},{'name':'view_file','args':{}}]}) + '\\n')\n"
        + "time.sleep(0.3)\n",
        encoding="utf-8",
    )
    fake_agy.chmod(0o700)
    log = tmp_path / "agy.log"
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    monkeypatch.setenv("NEXUS_AGY_ATTESTATION_LOG", str(log))
    env = os.environ.copy()
    env["HOME"] = str(home)

    code, _out, err, timed_out, _wall_ms = dispatch.run_agy(
        env=env,
        prompt="read-only plan/reviewer",
        cwd=str(work),
        mode="plan",
        model=None,
        effort=None,
        timeout=5,
        expect_coding_progress=True,
        provider_stall_seconds=0.05,
        stream_no_progress_seconds=0.05,
        pre_effect_max_seconds=0.05,
        pre_effect_max_tool_events=1,
    )

    assert code == 0
    assert timed_out is False
    assert "NEXUS_AGY_NON_PROGRESS:PRE_EFFECT_TOOL_THRASH" not in err
    assert "NEXUS_AGY_NON_PROGRESS" not in err


def test_run_agy_drains_previous_transcript_before_session_switch(
    tmp_path: Path, monkeypatch
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "-C", str(work), "init"], check=True, capture_output=True)
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_agy = bin_dir / "agy"
    first_session = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    second_session = "11111111-2222-3333-4444-555555555555"
    fake_agy.write_text(
        "#!"
        + sys.executable
        + "\nimport json, os, sys, time\n"
        + "from pathlib import Path\n"
        + f"first = {first_session!r}\n"
        + f"second = {second_session!r}\n"
        + "log = Path(sys.argv[sys.argv.index('--log-file') + 1])\n"
        + "root = Path(os.environ['HOME']) / '.gemini' / 'antigravity-cli' / 'brain'\n"
        + "first_t = root / first / '.system_generated' / 'logs' / 'transcript_full.jsonl'\n"
        + "second_t = root / second / '.system_generated' / 'logs' / 'transcript_full.jsonl'\n"
        + "first_t.parent.mkdir(parents=True, exist_ok=True)\n"
        + "second_t.parent.mkdir(parents=True, exist_ok=True)\n"
        + "first_t.write_text(json.dumps({'source':'USER','type':'USER_INPUT'}) + '\\n')\n"
        + "with first_t.open('a') as fh: fh.write(json.dumps({'source':'MODEL','type':'PLANNER_RESPONSE','tool_calls':[{'name':'run_command','args':{}}]}) + '\\n')\n"
        + "second_t.write_text('')\n"
        + "log.write_text('I server.go:1263] Created conversation ' + first + '\\n'"
        + " + 'I http_helpers.go:315] URL: https://example/v1internal:streamGenerateContent?alt=sse\\n'"
        + " + 'I server.go:1263] Created conversation ' + second + '\\n')\n"
        + "time.sleep(0.2)\n",
        encoding="utf-8",
    )
    fake_agy.chmod(0o700)
    log = tmp_path / "agy.log"
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    monkeypatch.setenv("NEXUS_AGY_ATTESTATION_LOG", str(log))
    env = os.environ.copy()
    env["HOME"] = str(home)

    events: list[dict[str, object]] = []
    code, _out, _err, _timed_out, _wall_ms = dispatch.run_agy(
        env=env,
        prompt="session switch",
        cwd=str(work),
        mode="plan",
        model=None,
        effort=None,
        timeout=5,
        operation_hook=events.append,
    )

    assert code == 0
    tool_events = [event for event in events if event.get("tool_event_count")]
    assert tool_events
    assert tool_events[-1]["tool_event_count"] == 1
    assert any(event.get("provider_session_id") == second_session for event in events)


def test_run_agy_watchdog_boundary_rechecks_source_effect(tmp_path: Path, monkeypatch) -> None:
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "-C", str(work), "init"], check=True, capture_output=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    effect = work / "effect.txt"
    fake_agy = bin_dir / "agy"
    fake_agy.write_text(
        "#!"
        + sys.executable
        + "\nimport os, sys, time\n"
        + "from pathlib import Path\n"
        + "log = Path(sys.argv[sys.argv.index('--log-file') + 1])\n"
        + "log.write_text('I http_helpers.go:315] URL: https://example/v1internal:streamGenerateContent?alt=sse\\n')\n"
        + "time.sleep(0.16)\n"
        + "Path(os.environ['AGY_EFFECT_PATH']).write_text('effect')\n"
        + "time.sleep(0.12)\n",
        encoding="utf-8",
    )
    fake_agy.chmod(0o700)
    log = tmp_path / "agy.log"
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    monkeypatch.setenv("NEXUS_AGY_ATTESTATION_LOG", str(log))
    monkeypatch.setenv("AGY_EFFECT_PATH", str(effect))

    events: list[dict[str, object]] = []
    code, _out, err, timed_out, _wall_ms = dispatch.run_agy(
        env=os.environ.copy(),
        prompt="write once",
        cwd=str(work),
        mode="accept-edits",
        model=None,
        effort=None,
        timeout=5,
        operation_hook=events.append,
        expect_coding_progress=True,
        provider_stall_seconds=0.5,
        stream_no_progress_seconds=0.15,
    )

    assert code == 0
    assert timed_out is False
    assert effect.read_text(encoding="utf-8") == "effect"
    assert "NEXUS_AGY_NON_PROGRESS" not in err
    assert any(event.get("first_effect_at") for event in events)


def test_run_agy_no_tool_task_is_not_killed_by_coding_watchdog(tmp_path: Path, monkeypatch) -> None:
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "-C", str(work), "init"], check=True, capture_output=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_agy = bin_dir / "agy"
    fake_agy.write_text(
        "#!"
        + sys.executable
        + "\nimport sys, time\n"
        + "from pathlib import Path\n"
        + "log = Path(sys.argv[sys.argv.index('--log-file') + 1])\n"
        + "log.write_text('I http_helpers.go:315] URL: https://example/v1internal:streamGenerateContent?alt=sse\\n')\n"
        + "time.sleep(0.3)\n"
        + "print('PACKET_OK')\n",
        encoding="utf-8",
    )
    fake_agy.chmod(0o700)
    log = tmp_path / "agy.log"
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    monkeypatch.setenv("NEXUS_AGY_ATTESTATION_LOG", str(log))
    monkeypatch.setenv("NEXUS_AGY_PROVIDER_STALL_SECONDS", "0.1")
    monkeypatch.setenv("NEXUS_AGY_STREAM_NO_PROGRESS_SECONDS", "0.1")

    code, out, err, timed_out, _wall_ms = dispatch.run_agy(
        env=os.environ.copy(),
        prompt="review packet",
        cwd=str(work),
        mode="plan",
        model=None,
        effort=None,
        timeout=5,
        expect_coding_progress=False,
    )

    assert code == 0
    assert timed_out is False
    assert "PACKET_OK" in out
    assert "NEXUS_AGY_NON_PROGRESS" not in err


def test_independent_quota_after_effect_never_rotates(tmp_path):
    work = tmp_path / "repo"
    work.mkdir()
    subprocess.run(["git", "init", str(work)], check=True, capture_output=True)
    home = tmp_path / "home"
    home.mkdir()

    class Coordinator(_WriteScopeCoordinator):
        rotation_count = 0

        def rotate_claim(self, **kwargs):
            self.rotation_count += 1
            raise RuntimeError("must not rotate after source effect")

    coordinator = Coordinator(home)
    calls = []
    events = []

    def runner(**kwargs):
        calls.append(True)
        (work / "changed.txt").write_text("partial effect")
        return 1, "", "RESOURCE_EXHAUSTED: quota exhausted", False, 10

    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(work),
        mode="accept-edits",
        write_paths=[str(work / "changed.txt")],
        coordinator=coordinator,
        run_agy_fn=runner,
        operation_hook=events.append,
    )
    assert code != 0
    assert coordinator.rotation_count == 0
    assert len(calls) == 1
    classified = [e for e in events if e.get("phase") == "CLASSIFYING_FAILURE"][-1]
    assert classified["failure_kind"] == "PROVIDER_QUOTA_EXHAUSTED_AFTER_EFFECT"
    assert classified["provider_effect"] is True
    assert classified["reconciliation_required"] is True


def test_independent_headless_denial_only_in_provider_log_is_failure(tmp_path, monkeypatch):
    work = tmp_path / "repo"
    work.mkdir()
    subprocess.run(["git", "init", str(work)], check=True, capture_output=True)
    home = tmp_path / "home"
    home.mkdir()
    binary = tmp_path / "agy"
    binary.write_text(
        "#!" + sys.executable + "\nimport sys\nfrom pathlib import Path\n"
        "p = Path(sys.argv[sys.argv.index('--log-file') + 1])\n"
        "p.write_text('Print mode: soft-denying tool confirmation RunCommand at step 2\\n')\n"
    )
    binary.chmod(0o700)
    monkeypatch.setattr(dispatch.shutil, "which", lambda name: str(binary))
    monkeypatch.setenv("NEXUS_AGY_ATTESTATION_LOG", str(tmp_path / "agy.log"))
    events = []
    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(work),
        mode="accept-edits",
        write_paths=[str(work / "changed.txt")],
        coordinator=_WriteScopeCoordinator(home),
        operation_hook=events.append,
    )
    assert code != 0
    assert any(e.get("failure_kind") == "HEADLESS_TOOL_PERMISSION_DENIED" for e in events)


def test_headless_permission_failure_after_physical_effect_requires_reconciliation(
    tmp_path: Path,
) -> None:
    work = tmp_path / "repo"
    work.mkdir()
    subprocess.run(["git", "init", str(work)], check=True, capture_output=True)
    home = tmp_path / "home"
    home.mkdir()
    target = work / "partial-effect.txt"

    class Coordinator(_WriteScopeCoordinator):
        rotation_count = 0

        def rotate_claim(self, **kwargs):
            self.rotation_count += 1
            raise AssertionError("permission failure after an effect must not rotate")

    coordinator = Coordinator(home)
    events: list[dict[str, object]] = []

    def runner(**_kwargs):
        target.write_text("provider already changed source", encoding="utf-8")
        return (
            0,
            "",
            "tool permission denied: headless mode cannot prompt for confirmation\n",
            False,
            10,
        )

    code = dispatch.dispatch_run(
        prompt="edit then permission denial",
        cwd=str(work),
        mode="accept-edits",
        write_paths=[str(target)],
        coordinator=coordinator,
        run_agy_fn=runner,
        operation_hook=events.append,
    )

    classified = [event for event in events if event.get("phase") == "CLASSIFYING_FAILURE"][-1]
    assert code == 1
    assert target.read_text(encoding="utf-8") == "provider already changed source"
    assert classified["failure_kind"] == "HEADLESS_TOOL_PERMISSION_DENIED"
    assert classified["provider_effect"] is True
    assert classified["reconciliation_required"] is True
    assert coordinator.rotation_count == 0


def test_run_agy_throttles_effect_scans_for_a_long_provider(tmp_path: Path, monkeypatch) -> None:
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "-C", str(work), "init"], check=True, capture_output=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_agy = bin_dir / "agy"
    fake_agy.write_text(
        "#!" + sys.executable + "\nimport time\ntime.sleep(1.05)\n",
        encoding="utf-8",
    )
    fake_agy.chmod(0o700)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    original_observe = dispatch.direct_operation_journal.observed_changed_paths_since
    scan_times: list[float] = []

    def count_observations(cwd: str, baseline: dict[str, object]):
        scan_times.append(time.monotonic())
        return original_observe(cwd, baseline)

    monkeypatch.setattr(
        dispatch.direct_operation_journal,
        "observed_changed_paths_since",
        count_observations,
    )
    code, _out, _err, _timed_out, _wall_ms = dispatch.run_agy(
        env=os.environ.copy(),
        prompt="wait without a source edit",
        cwd=str(work),
        mode="plan",
        model=None,
        effort=None,
        timeout=5,
    )

    assert code == 0
    assert len(scan_times) >= 3
    assert all(later - earlier >= 0.4 for earlier, later in zip(scan_times[:-2], scan_times[1:-1]))


def test_run_agy_final_readback_captures_short_lived_effect_after_first_empty_scan(
    tmp_path: Path, monkeypatch
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "-C", str(work), "init"], check=True, capture_output=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_agy = bin_dir / "agy"
    fake_agy.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import os
            import time
            from pathlib import Path

            time.sleep(0.1)
            Path(os.environ["AGY_SHORT_EFFECT_PATH"]).write_text("short effect")
            """
        ),        encoding="utf-8",
    )
    fake_agy.chmod(0o700)
    effect = work / "short-lived.txt"
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    monkeypatch.setenv("AGY_SHORT_EFFECT_PATH", str(effect))
    original_observe = dispatch.direct_operation_journal.observed_changed_paths_since
    scan_times: list[float] = []

    def force_first_empty_scan(cwd: str, baseline: dict[str, object]):
        scan_times.append(time.monotonic())
        if len(scan_times) == 1:
            return []
        return original_observe(cwd, baseline)

    monkeypatch.setattr(
        dispatch.direct_operation_journal,
        "observed_changed_paths_since",
        force_first_empty_scan,
    )
    events: list[dict[str, object]] = []
    code, _out, _err, _timed_out, _wall_ms = dispatch.run_agy(
        env=os.environ.copy(),
        prompt="make a short-lived source edit",
        cwd=str(work),
        mode="plan",
        model=None,
        effort=None,
        timeout=5,
        operation_hook=events.append,
    )

    assert code == 0
    assert effect.is_file()
    assert len(scan_times) == 2
    assert any(event.get("first_effect_at") for event in events)


def test_independent_baseline_failure_stays_unknown(tmp_path, monkeypatch):
    work = tmp_path / "repo"
    work.mkdir()
    subprocess.run(["git", "init", str(work)], check=True, capture_output=True)
    (work / "donor.txt").write_text("not this provider")
    binary = tmp_path / "agy"
    binary.write_text("#!" + sys.executable + "\nimport time\ntime.sleep(0.15)\n")
    binary.chmod(0o700)
    monkeypatch.setattr(dispatch.shutil, "which", lambda name: str(binary))
    original = dispatch.direct_operation_journal.capture_source_baseline
    calls = []

    def fail_first(cwd):
        calls.append(True)
        if len(calls) == 1:
            raise OSError("baseline unreadable")
        return original(cwd)

    monkeypatch.setattr(dispatch.direct_operation_journal, "capture_source_baseline", fail_first)
    events = []
    dispatch.run_agy(
        env=os.environ.copy(),
        prompt="test",
        cwd=str(work),
        mode="plan",
        model=None,
        effort=None,
        timeout=1,
        operation_hook=events.append,
    )
    assert not any(e.get("first_effect_at") for e in events)
    assert any(e.get("effect_observation_error") for e in events)


def test_run_agy_quota_cleanup_stops_provider_process_group(tmp_path: Path, monkeypatch) -> None:
    from io import StringIO

    stopped_groups: list[int] = []
    process_ref: dict[str, object] = {}

    class FakeProcess:
        pid = 4242

        def __init__(self, argv, **kwargs):
            self.stdout = StringIO("")
            self.stderr = StringIO("quota exceeded\n")
            self.returncode = None
            process_ref["process"] = self

        def poll(self):
            return self.returncode

        def wait(self, timeout=None):
            return self.returncode

        def terminate(self):
            self.returncode = -15

        def kill(self):
            self.returncode = -9

    def stop_group(pgid: int, **_kwargs) -> bool:
        stopped_groups.append(pgid)
        process = process_ref["process"]
        process.returncode = -15
        return True

    monkeypatch.setattr(dispatch.shutil, "which", lambda name: "/tmp/fake-agy")
    monkeypatch.setattr(dispatch.subprocess, "Popen", FakeProcess)
    monkeypatch.setattr(dispatch.os, "getpgid", lambda pid: pid)
    monkeypatch.setattr(dispatch._agy_operation_journal, "_stop_process_group", stop_group)
    monkeypatch.setattr(
        dispatch._agy_operation_journal,
        "_process_group_alive",
        lambda pgid: False,
    )

    code, _out, err, timed_out, _ = dispatch.run_agy(
        env={"HOME": str(tmp_path)},
        prompt="quota group cleanup",
        cwd=str(tmp_path),
        mode="plan",
        model=None,
        effort=None,
        timeout=30,
    )

    assert code == -15
    assert "quota exceeded" in err
    assert timed_out is False
    assert stopped_groups == [4242]


_PROVIDER_CHILD_SCRIPT = textwrap.dedent("""\
    import os
    import subprocess
    import sys
    import time
    from importlib.machinery import SourceFileLoader
    from pathlib import Path

    dispatch_path = sys.argv[1]
    op_root = Path(sys.argv[2])
    operation_id = sys.argv[3]
    ready_file = Path(sys.argv[4])
    child_pid_file = Path(sys.argv[5])
    snapshot_root = sys.argv[6]

    os.environ["NEXUS_AGY_SNAPSHOT"] = snapshot_root
    dispatch = SourceFileLoader(
        "nexus_agy_dispatch_canonical", dispatch_path
    ).load_module()

    journal = dispatch.AgyOperationJournal(op_root)
    prompt_path = journal.prompt_path(operation_id)
    dispatch._write_private_prompt(prompt_path, "sigterm child reaping probe")

    log_path = str(journal.operation_dir(operation_id) / "agy.log")

    def fake_run_agy(**kwargs):
        sub = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", log_path])
        child_pid_file.write_text(str(sub.pid))
        ready_file.touch()
        sub.wait()
        return 0, "", "", False, 100

    def fake_dispatch_run(**kwargs):
        kwargs["operation_hook"]({
            "phase": "EXECUTING",
            "attempts": 1,
            "rotations": 0,
        })
        return fake_run_agy(**kwargs)

    dispatch.dispatch_run = fake_dispatch_run

    try:
        dispatch._run_background_operation(
            operation_id=operation_id,
            prompt_file=str(prompt_path),
            cwd=str(op_root),
            mode="plan",
            model="gemini-test",
            effort="medium",
            timeout=30,
            max_calls=1,
            pool_wait_timeout=1.0,
            allow=[],
            deny=[],
            temp_command_permissions=False,
            operation_root=op_root,
            heartbeat_interval=0.01,
        )
    except BaseException:
        pass
""")


def test_sigterm_to_supervisor_reaps_owned_provider_child(
    tmp_path: Path,
) -> None:
    """Supervisor receiving SIGTERM must reap its owned provider child process."""
    op_root = tmp_path / "ops"
    journal = dispatch.AgyOperationJournal(op_root)
    operation_id = dispatch.new_operation_id()
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model="gemini-test",
        effort="medium",
        prompt_sha256="0" * 64,
        runtime_revision="a" * 40,
    )

    ready_file = tmp_path / "ready"
    child_pid_file = tmp_path / "child.pid"
    script_file = tmp_path / "provider_child.py"
    script_file.write_text(_PROVIDER_CHILD_SCRIPT, encoding="utf-8")

    child = subprocess.Popen(
        [
            sys.executable,
            str(script_file),
            str(DISPATCH_PATH),
            str(op_root),
            operation_id,
            str(ready_file),
            str(child_pid_file),
            str(ROOT),
        ],
        cwd=str(tmp_path),
    )

    deadline = time.monotonic() + 20.0
    while not ready_file.exists() or not child_pid_file.exists():
        if time.monotonic() > deadline:
            child.kill()
            child.wait()
            raise TimeoutError("provider child never signalled readiness")
        time.sleep(0.05)

    provider_pid = int(child_pid_file.read_text().strip())
    assert dispatch._agy_operation_journal._process_alive(provider_pid), (
        "Provider child must be running initially"
    )

    try:
        os.kill(child.pid, signal.SIGTERM)
        child.wait(timeout=10)

        assert not dispatch._agy_operation_journal._process_alive(provider_pid), (
            f"Provider child {provider_pid} is still alive after supervisor SIGTERM!"
        )

        record = journal.read(operation_id)
        assert record["status"] == "OUTCOME_UNKNOWN"
        reconciliation = record.get("reconciliation") or {}
        assert reconciliation.get("provider_alive_after") is False
    finally:
        if dispatch._agy_operation_journal._process_alive(provider_pid):
            try:
                os.kill(provider_pid, signal.SIGKILL)
            except OSError:
                pass


def test_dispatch_run_retains_lease_when_provider_cannot_be_killed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """When provider child remains alive after execution error, lease must not be released."""
    home = tmp_path / "home"
    home.mkdir()
    coordinator = _WriteScopeCoordinator(home)

    def stubborn_runner(*, operation_hook=None, **_kwargs):
        if operation_hook:
            operation_hook(provider_pid=12345)
        return 1, "", "error", False, 10

    orig_alive = dispatch._agy_operation_journal._process_alive
    monkeypatch.setattr(
        dispatch._agy_operation_journal,
        "_process_alive",
        lambda pid: True if pid == 12345 else orig_alive(pid),
    )
    monkeypatch.setattr(
        dispatch._agy_operation_journal,
        "_stop_process",
        lambda pid, **kwargs: False,
    )

    code = dispatch.dispatch_run(
        prompt="stubborn run",
        cwd=str(tmp_path),
        mode="plan",
        coordinator=coordinator,
        run_agy_fn=stubborn_runner,
    )

    assert code != 0
    assert coordinator.claim.released is False, (
        "Lease must NOT be released while provider child is running!"
    )


def test_dispatch_run_retains_lease_when_provider_group_survives_leader(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A dead provider leader must not release the lease while its process group survives."""
    home = tmp_path / "home"
    home.mkdir()
    coordinator = _WriteScopeCoordinator(home)

    def orphaned_group_runner(*, operation_hook=None, **_kwargs):
        if operation_hook:
            operation_hook(provider_pid=12345, provider_pgid=54321)
        return 1, "", "error", False, 10

    orig_alive = dispatch._agy_operation_journal._process_alive
    orig_group_alive = dispatch._agy_operation_journal._process_group_alive
    monkeypatch.setattr(
        dispatch._agy_operation_journal,
        "_process_alive",
        lambda pid: False if pid == 12345 else orig_alive(pid),
    )
    monkeypatch.setattr(
        dispatch._agy_operation_journal,
        "_process_group_alive",
        lambda pgid: True if pgid == 54321 else orig_group_alive(pgid),
    )
    monkeypatch.setattr(
        dispatch._agy_operation_journal,
        "_stop_process_group",
        lambda pgid, **kwargs: False,
    )

    code = dispatch.dispatch_run(
        prompt="orphaned group run",
        cwd=str(tmp_path),
        mode="plan",
        coordinator=coordinator,
        run_agy_fn=orphaned_group_runner,
    )

    assert code != 0
    assert coordinator.claim.released is False, (
        "Lease must NOT be released while the provider process group is still running!"
    )


def test_run_agy_aborts_process_group_when_durable_identity_hook_fails(
    tmp_path: Path,
    monkeypatch,
) -> None:
    fake_agy = tmp_path / "fake-agy"
    fake_agy.write_text("#!/bin/sh\nsleep 60\n", encoding="utf-8")
    fake_agy.chmod(0o755)
    monkeypatch.setattr(dispatch.shutil, "which", lambda _name: str(fake_agy))

    observed: dict[str, int | None] = {}

    def failing_hook(event: dict[str, object]) -> None:
        observed.update(event)
        if isinstance(event.get("provider_pid"), int):
            raise RuntimeError("journal identity write failed")

    with pytest.raises(RuntimeError, match="journal identity write failed"):
        dispatch.run_agy(
            env=os.environ.copy(),
            prompt="identity persistence probe",
            cwd=str(tmp_path),
            mode="plan",
            model=None,
            effort=None,
            timeout=30,
            operation_hook=failing_hook,
        )

    provider_pid = observed.get("provider_pid")
    provider_pgid = observed.get("provider_pgid")
    assert isinstance(provider_pid, int)
    assert isinstance(provider_pgid, int)
    assert provider_pgid == provider_pid
    assert not dispatch._agy_operation_journal._process_alive(provider_pid)
    assert not dispatch._agy_operation_journal._process_group_alive(provider_pgid)


def test_background_operation_stays_nonterminal_while_provider_group_survives(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "ops"
    journal = dispatch.AgyOperationJournal(root)
    operation_id = dispatch.new_operation_id()
    prompt_path = journal.prompt_path(operation_id)
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model="gemini-test",
        effort="medium",
        prompt_sha256="0" * 64,
        runtime_revision="a" * 40,
    )
    dispatch._write_private_prompt(prompt_path, "surviving process group probe")
    monkeypatch.setattr(dispatch, "_runtime_revision", lambda: "a" * 40)

    def fake_dispatch_run(**kwargs):
        kwargs["operation_hook"]({
            "phase": "CLASSIFYING_FAILURE",
            "attempts": 1,
            "rotations": 0,
            "failure_kind": "PROVIDER_ERROR",
            "provider_pid": 12345,
            "provider_pgid": 54321,
        })
        return 1

    monkeypatch.setattr(dispatch, "dispatch_run", fake_dispatch_run)
    orig_alive = dispatch._agy_operation_journal._process_alive
    orig_group_alive = dispatch._agy_operation_journal._process_group_alive
    monkeypatch.setattr(
        dispatch._agy_operation_journal,
        "_process_alive",
        lambda pid: False if pid == 12345 else orig_alive(pid),
    )
    monkeypatch.setattr(
        dispatch._agy_operation_journal,
        "_process_group_alive",
        lambda pgid: True if pgid == 54321 else orig_group_alive(pgid),
    )

    code = dispatch._run_background_operation(
        operation_id=operation_id,
        prompt_file=str(prompt_path),
        cwd=str(tmp_path),
        mode="plan",
        model="gemini-test",
        effort="medium",
        timeout=30,
        max_calls=1,
        pool_wait_timeout=1.0,
        allow=[],
        deny=[],
        temp_command_permissions=False,
        operation_root=root,
        heartbeat_interval=0.01,
    )

    record = journal.read(operation_id)
    assert code == 1
    assert record["status"] == "RUNNING"
    assert record["phase"] == "RECONCILE_REQUIRED"
    assert record["finished_at"] is None
    assert record["reconciliation"]["result"] == "PROVIDER_PROCESS_STILL_RUNNING_AFTER_DISPATCH"
    assert record["reconciliation"]["provider_alive_after"] is True
    assert record["reconciliation"]["retry_permitted"] is False


def test_dispatch_run_does_not_signal_from_bare_provider_pid_or_pgid(
    tmp_path: Path,
    monkeypatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    coordinator = _WriteScopeCoordinator(home)

    def stale_identity_runner(*, operation_hook=None, **_kwargs):
        if operation_hook:
            operation_hook(provider_pid=12345, provider_pgid=54321)
        return 1, "", "error", False, 10

    orig_alive = dispatch._agy_operation_journal._process_alive
    orig_group_alive = dispatch._agy_operation_journal._process_group_alive
    monkeypatch.setattr(
        dispatch._agy_operation_journal,
        "_process_alive",
        lambda pid: True if pid == 12345 else orig_alive(pid),
    )
    monkeypatch.setattr(
        dispatch._agy_operation_journal,
        "_process_group_alive",
        lambda pgid: True if pgid == 54321 else orig_group_alive(pgid),
    )

    def forbidden_signal(*_args, **_kwargs):
        raise AssertionError("dispatch_run must not signal from bare numeric process identity")

    monkeypatch.setattr(dispatch._agy_operation_journal, "_stop_process", forbidden_signal)
    monkeypatch.setattr(dispatch._agy_operation_journal, "_stop_process_group", forbidden_signal)

    code = dispatch.dispatch_run(
        prompt="stale identity run",
        cwd=str(tmp_path),
        mode="plan",
        coordinator=coordinator,
        run_agy_fn=stale_identity_runner,
    )

    assert code != 0
    assert coordinator.claim.released is False


def test_signal_guard_keeps_operation_nonterminal_when_provider_is_unresolved(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "ops"
    journal = dispatch.AgyOperationJournal(root)
    operation_id = dispatch.new_operation_id()
    prompt_path = journal.prompt_path(operation_id)
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model="gemini-test",
        effort="medium",
        prompt_sha256="0" * 64,
        runtime_revision="a" * 40,
    )
    dispatch._write_private_prompt(prompt_path, "unresolved provider probe")
    monkeypatch.setattr(dispatch, "_runtime_revision", lambda: "a" * 40)

    def interrupted_dispatch(**kwargs):
        kwargs["operation_hook"]({
            "phase": "EXECUTING",
            "attempts": 1,
            "rotations": 0,
            "provider_pid": 12345,
            "provider_pgid": 12345,
        })
        raise dispatch._SupervisorSignalError(signal.SIGTERM)

    monkeypatch.setattr(dispatch, "dispatch_run", interrupted_dispatch)
    monkeypatch.setattr(
        dispatch._agy_operation_journal,
        "_stop_operation_processes",
        lambda *_args, **_kwargs: (True, True, True),
    )

    with pytest.raises(dispatch._SupervisorSignalError):
        dispatch._run_background_operation(
            operation_id=operation_id,
            prompt_file=str(prompt_path),
            cwd=str(tmp_path),
            mode="plan",
            model="gemini-test",
            effort="medium",
            timeout=30,
            max_calls=1,
            pool_wait_timeout=1.0,
            allow=[],
            deny=[],
            temp_command_permissions=False,
            operation_root=root,
            heartbeat_interval=0.01,
        )

    record = journal.read(operation_id)
    assert record["status"] == "RUNNING"
    assert record["phase"] == "RECONCILE_REQUIRED"
    assert record["finished_at"] is None
    assert record["failure_kind"] == "SUPERVISOR_SIGNAL:SIGTERM"
    assert record["reconciliation"]["result"] == "SUPERVISOR_SIGNAL_ORPHAN_PROVIDER_UNVERIFIED"
    assert record["reconciliation"]["provider_alive_after"] is True
    assert record["reconciliation"]["retry_permitted"] is False


def test_wrapper_exception_keeps_operation_nonterminal_when_provider_is_unresolved(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "ops"
    journal = dispatch.AgyOperationJournal(root)
    operation_id = dispatch.new_operation_id()
    prompt_path = journal.prompt_path(operation_id)
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model="gemini-test",
        effort="medium",
        prompt_sha256="0" * 64,
        runtime_revision="a" * 40,
    )
    dispatch._write_private_prompt(prompt_path, "wrapper exception probe")
    monkeypatch.setattr(dispatch, "_runtime_revision", lambda: "a" * 40)

    def exploding_dispatch(**kwargs):
        kwargs["operation_hook"]({
            "phase": "EXECUTING",
            "attempts": 1,
            "rotations": 0,
            "provider_pid": 12345,
            "provider_pgid": 12345,
        })
        raise RuntimeError("provider wrapper exploded")

    monkeypatch.setattr(dispatch, "dispatch_run", exploding_dispatch)
    monkeypatch.setattr(
        dispatch._agy_operation_journal,
        "_stop_operation_processes",
        lambda *_args, **_kwargs: (True, True, True),
    )

    with pytest.raises(RuntimeError, match="provider wrapper exploded"):
        dispatch._run_background_operation(
            operation_id=operation_id,
            prompt_file=str(prompt_path),
            cwd=str(tmp_path),
            mode="plan",
            model="gemini-test",
            effort="medium",
            timeout=30,
            max_calls=1,
            pool_wait_timeout=1.0,
            allow=[],
            deny=[],
            temp_command_permissions=False,
            operation_root=root,
            heartbeat_interval=0.01,
        )

    record = journal.read(operation_id)
    assert record["status"] == "RUNNING"
    assert record["phase"] == "RECONCILE_REQUIRED"
    assert record["finished_at"] is None
    assert record["failure_kind"] == "WRAPPER_EXCEPTION:RuntimeError"
    assert record["reconciliation"]["result"] == "WRAPPER_EXCEPTION_ORPHAN_PROVIDER_UNVERIFIED"
    assert record["reconciliation"]["provider_alive_after"] is True
    assert record["reconciliation"]["retry_permitted"] is False


def _make_no_effect_finalization_repo(tmp_path: Path) -> Path:
    root = tmp_path / "source-repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)
    (root / "tracked.txt").write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=root, check=True)
    return root


def _create_outcome_unknown_source_operation(
    journal,
    source_root: Path,
) -> str:
    operation_id = dispatch.new_operation_id()
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(source_root),
        provider="agy",
        model="gemini-test",
        effort="medium",
        prompt_sha256="a" * 64,
        runtime_revision="b" * 40,
    )
    journal.mark_started(operation_id, pid=999_999_998)
    journal.update(
        operation_id,
        account_alias_hash="acct-finalize",
        lease_id_hash="lease-finalize",
    )
    journal.mark_terminal(
        operation_id,
        status="OUTCOME_UNKNOWN",
        exit_code=None,
        failure_kind="TIMEOUT",
        cwd=str(source_root),
        reconciliation={
            "result": "PROVIDER_TURN_MAY_STILL_BE_RUNNING",
            "provider_alive_after": False,
            "retry_permitted": False,
        },
    )
    return operation_id


def test_finalize_no_effect_releases_only_source_retry_fence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_root = _make_no_effect_finalization_repo(tmp_path)
    journal = dispatch.AgyOperationJournal(tmp_path / "operations")
    operation_id = _create_outcome_unknown_source_operation(journal, source_root)
    monkeypatch.setattr(dispatch, "LEASES_DIR", tmp_path / "leases")

    finalized = dispatch._finalize_no_effect_operation(journal, operation_id)

    assert finalized["status"] == "FAILED"
    assert finalized["failure_kind"] == "TIMEOUT"
    reconciliation = finalized["reconciliation"]
    assert reconciliation["result"] == "SOURCE_NO_DURABLE_EFFECT_PROVEN"
    assert reconciliation["reconciliation_scope"] == "SOURCE_ONLY"
    assert reconciliation["retry_permitted"] is True
    assert reconciliation["lease_cleanup"]["result"] == "ALREADY_ABSENT"
    assert reconciliation["source_proof"]["proof_scope"] == "SOURCE_STATE_ONLY"
    assert reconciliation["source_proof"]["observed_changed_paths"] == []

    replay = dispatch._finalize_no_effect_operation(journal, operation_id)
    assert replay == finalized


def test_finalize_no_effect_fails_closed_when_lease_identity_conflicts(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_root = _make_no_effect_finalization_repo(tmp_path)
    journal = dispatch.AgyOperationJournal(tmp_path / "operations")
    operation_id = _create_outcome_unknown_source_operation(journal, source_root)
    leases = tmp_path / "leases"
    leases.mkdir()
    monkeypatch.setattr(dispatch, "LEASES_DIR", leases)
    (leases / "acct-finalize.receipt.json").write_text(
        json.dumps({
            "account_alias_hash": "acct-finalize",
            "lease_id_hash": "different-lease",
            "pid": 999_999_998,
        }),
        encoding="utf-8",
    )

    with pytest.raises(
        dispatch.AgyOperationJournalError,
        match="NO_EFFECT_LEASE_NOT_SAFE",
    ):
        dispatch._finalize_no_effect_operation(journal, operation_id)

    blocked = journal.read(operation_id)
    assert blocked["status"] == "OUTCOME_UNKNOWN"
    assert blocked["reconciliation"]["retry_permitted"] is False


def test_finalize_no_effect_cli_projects_receipt(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    source_root = _make_no_effect_finalization_repo(tmp_path)
    operation_root = tmp_path / "operations"
    journal = dispatch.AgyOperationJournal(operation_root)
    operation_id = _create_outcome_unknown_source_operation(journal, source_root)
    monkeypatch.setattr(dispatch, "LEASES_DIR", tmp_path / "leases")

    assert (
        dispatch.main([
            "--finalize-no-effect",
            operation_id,
            "--operation-root",
            str(operation_root),
        ])
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "FAILED"
    assert payload["reconciliation"]["result"] == "SOURCE_NO_DURABLE_EFFECT_PROVEN"
    assert payload["reconciliation"]["retry_permitted"] is True


def test_contradictory_command_permission_fails_closed_before_claim(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    target = work / "file.py"
    coordinator = _WriteScopeCoordinator(home)
    events: list[dict[str, object]] = []

    code = dispatch.dispatch_run(
        prompt="contradictory command permission",
        cwd=str(work),
        mode="accept-edits",
        write_paths=[str(target)],
        temp_command_permissions=True,
        deny=["command(*)"],
        coordinator=coordinator,
        run_agy_fn=lambda **_kwargs: (0, "ok", "", False, 1),
        operation_hook=events.append,
    )

    assert code == 64
    assert coordinator.acquire_count == 0
    assert any(
        "CONTRADICTORY_PERMISSION_PROFILE:command(*)" in str(event.get("failure_kind"))
        for event in events
    )


def test_contradictory_write_permission_fails_closed_before_claim(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    target = work / "file.py"
    coordinator = _WriteScopeCoordinator(home)
    events: list[dict[str, object]] = []

    code = dispatch.dispatch_run(
        prompt="contradictory write permission",
        cwd=str(work),
        mode="accept-edits",
        write_paths=[str(target)],
        deny=["write_file(*)"],
        coordinator=coordinator,
        run_agy_fn=lambda **_kwargs: (0, "ok", "", False, 1),
        operation_hook=events.append,
    )

    assert code == 64
    assert coordinator.acquire_count == 0
    assert any(
        "CONTRADICTORY_PERMISSION_PROFILE:write_file(*)" in str(event.get("failure_kind"))
        for event in events
    )


def test_contradictory_read_permission_fails_closed_before_claim(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    target = work / "file.py"
    coordinator = _WriteScopeCoordinator(home)
    events: list[dict[str, object]] = []

    code = dispatch.dispatch_run(
        prompt="contradictory read permission",
        cwd=str(work),
        mode="accept-edits",
        write_paths=[str(target)],
        deny=["read_file(*)"],
        coordinator=coordinator,
        run_agy_fn=lambda **_kwargs: (0, "ok", "", False, 1),
        operation_hook=events.append,
    )

    assert code == 64
    assert coordinator.acquire_count == 0
    assert any(
        "CONTRADICTORY_PERMISSION_PROFILE:read_file(*)" in str(event.get("failure_kind"))
        for event in events
    )


def test_contradictory_exact_rule_in_both_allow_and_deny_fails_closed(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    target = work / "file.py"
    coordinator = _WriteScopeCoordinator(home)
    events: list[dict[str, object]] = []

    code = dispatch.dispatch_run(
        prompt="rule in allow and deny",
        cwd=str(work),
        mode="accept-edits",
        write_paths=[str(target)],
        allow=["command(ls)"],
        deny=["command(ls)"],
        coordinator=coordinator,
        run_agy_fn=lambda **_kwargs: (0, "ok", "", False, 1),
        operation_hook=events.append,
    )

    assert code == 64
    assert coordinator.acquire_count == 0
    assert any(
        "CONTRADICTORY_PERMISSION_PROFILE:rule present in both allow and deny:command(ls)"
        in str(event.get("failure_kind"))
        for event in events
    )


def test_permission_profile_preflight_and_journal_projection(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    target = work / "target.py"
    coordinator = _WriteScopeCoordinator(home)
    events: list[dict[str, object]] = []

    code = dispatch.dispatch_run(
        prompt="bounded edit",
        cwd=str(work),
        mode="accept-edits",
        write_paths=[str(target)],
        temp_command_permissions=True,
        coordinator=coordinator,
        run_agy_fn=lambda **_kwargs: (0, "all good", "", False, 1),
        operation_hook=events.append,
    )

    assert code == 0
    assert coordinator.acquire_count == 1
    profile_events = [e for e in events if e.get("permission_profile_kind") == "CODING_BOUNDED"]
    assert len(profile_events) >= 1
    sha256 = profile_events[0].get("permission_profile_sha256")
    assert isinstance(sha256, str) and len(sha256) == 64
    effective_perms = profile_events[0].get("effective_permissions")
    assert isinstance(effective_perms, dict)
    assert f"write_file({target.resolve()})" in effective_perms["allow"]
    assert "command(*)" in effective_perms["allow"]
    assert "command(git push)" in effective_perms["deny"]


def test_permission_profile_preflight_fails_on_tampered_settings(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = {"HOME": str(home)}

    with pytest.raises(RuntimeError, match="PERMISSION_PREFLIGHT_CONTRADICTION"):
        dispatch.install_temp_permissions(
            env,
            allow_rules=["read_file(/tmp/**)"],
            deny_rules=["read_file(*)"],
            mode="accept-edits",
        )


@pytest.mark.parametrize(
    "marker,expected_kind",
    [
        ("Blocked by active deny rules for read_file(/repo/foo)", "PERMISSION_OR_SCOPE_ERROR"),
        ("tool execution permission block: denied", "PERMISSION_OR_SCOPE_ERROR"),
        ("Operation not permitted while accessing file", "PERMISSION_OR_SCOPE_ERROR"),
        ("blocked by the active security/deny rules", "PERMISSION_OR_SCOPE_ERROR"),
        (
            "print mode: soft-denying tool confirmation for command",
            "HEADLESS_TOOL_PERMISSION_DENIED",
        ),
        ("headless mode cannot prompt for confirmation", "HEADLESS_TOOL_PERMISSION_DENIED"),
        ("auto-denied tool call", "HEADLESS_TOOL_PERMISSION_DENIED"),
    ],
)
def test_accept_edits_semantic_refusal_variants(
    tmp_path: Path,
    marker: str,
    expected_kind: str,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    target = work / "target.py"
    coordinator = _WriteScopeCoordinator(home)
    events: list[dict[str, object]] = []

    code = dispatch.dispatch_run(
        prompt="bounded edit",
        cwd=str(work),
        mode="accept-edits",
        write_paths=[str(target)],
        temp_command_permissions=True,
        coordinator=coordinator,
        run_agy_fn=lambda **_kwargs: (0, marker, "", False, 1),
        operation_hook=events.append,
    )

    assert code == 1
    assert any(event.get("failure_kind") == expected_kind for event in events)
    assert coordinator.claim.released is True


def test_background_terminal_receipt_persists_permission_profile(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "ops"
    journal = dispatch.AgyOperationJournal(root)
    operation_id = dispatch.new_operation_id()
    prompt_path = journal.prompt_path(operation_id)
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model="gemini-3.8-flash",
        effort="low",
        prompt_sha256="0" * 64,
        runtime_revision="a" * 40,
    )
    dispatch._write_private_prompt(prompt_path, "edit probe")

    def fake_dispatch_run(**kwargs):
        kwargs["operation_hook"]({
            "phase": "EXECUTING",
            "attempts": 1,
            "rotations": 0,
            "account_alias_hash": "acct",
            "lease_id_hash": "lease",
            "permission_profile_sha256": "f" * 64,
            "permission_profile_kind": "CODING_BOUNDED",
            "effective_permissions": {
                "allow": ["read_file(/tmp/**)", "write_file(/tmp/file.py)"],
                "deny": ["command(git push)"],
            },
        })
        return 0

    monkeypatch.setattr(dispatch, "dispatch_run", fake_dispatch_run)
    code = dispatch._run_background_operation(
        operation_id=operation_id,
        prompt_file=str(prompt_path),
        cwd=str(tmp_path),
        mode="accept-edits",
        model="gemini-3.8-flash",
        effort="low",
        timeout=30,
        max_calls=1,
        pool_wait_timeout=1.0,
        allow=[],
        deny=[],
        temp_command_permissions=False,
        operation_root=root,
        heartbeat_interval=0.01,
    )
    record = journal.read(operation_id)
    assert code == 0
    assert record["status"] == "COMPLETED"
    assert record["permission_profile_kind"] == "CODING_BOUNDED"
    assert record["permission_profile_sha256"] == "f" * 64
    assert record["effective_permissions"] == {
        "allow": ["read_file(/tmp/**)", "write_file(/tmp/file.py)"],
        "deny": ["command(git push)"],
    }


def test_plan_mode_no_tool_packet_completes_cleanly(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    coordinator = _WriteScopeCoordinator(home)
    events: list[dict[str, object]] = []

    code = dispatch.dispatch_run(
        prompt="analyze architecture without tools",
        cwd=str(work),
        mode="plan",
        deny=["command(*)", "write_file(*)"],
        coordinator=coordinator,
        run_agy_fn=lambda **_kwargs: (
            0,
            "Analysis complete. No mutations requested.",
            "",
            False,
            1,
        ),
        operation_hook=events.append,
    )

    assert code == 0
    assert coordinator.acquire_count == 1
    assert coordinator.claim.released is True
    profile_events = [e for e in events if e.get("permission_profile_kind") == "NO_TOOL_PACKET"]
    assert len(profile_events) >= 1
    assert not any(event.get("failure_kind") for event in events)


def test_plan_mode_text_mentioning_permission_denied_in_model_response_completes_cleanly(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    coordinator = _WriteScopeCoordinator(home)
    events: list[dict[str, object]] = []

    code = dispatch.dispatch_run(
        prompt="explain permission denied errors",
        cwd=str(work),
        mode="plan",
        coordinator=coordinator,
        run_agy_fn=lambda **_kwargs: (
            0,
            "When a user encounters permission denied, it typically means permissions are missing.",
            "",
            False,
            1,
        ),
        operation_hook=events.append,
    )

    assert code == 0
    assert coordinator.acquire_count == 1
    assert not any(event.get("failure_kind") for event in events)


def test_temp_command_deny_includes_git_mutation_commands() -> None:
    expected_mutations = [
        "command(git checkout)",
        "command(git restore)",
        "command(git stash)",
        "command(git reset)",
        "command(git commit)",
        "command(git branch)",
        "command(git merge)",
        "command(git rebase)",
        "command(git cherry-pick)",
        "command(git revert)",
        "command(git clean)",
        "command(git push)",
        "command(git reset --hard)",
    ]
    for cmd in expected_mutations:
        assert cmd in dispatch.TEMP_COMMAND_DENY


def test_read_only_git_commands_not_in_deny() -> None:
    read_only_cmds = [
        "command(git diff)",
        "command(git log)",
        "command(git status)",
        "command(git show)",
        "command(git rev-parse)",
    ]
    for cmd in read_only_cmds:
        assert cmd not in dispatch.TEMP_COMMAND_DENY


def test_command_scope_g0_transient_mutation_red_fixture(tmp_path: Path) -> None:
    """Witness incident G0 reproduction:

    Pre-existing uncommitted dirty file exists outside write scope.
    The worker edits both the allowed file and the out-of-scope dirty file,
    attempting to bypass scope or restore changes, exiting with returncode 0.
    Must fail closed (exit 1), classify as SCOPE_VIOLATION_UNAUTHORIZED_MUTATION,
    and halt without rotating accounts.
    """
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=work, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=work, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=work, check=True)

    base_file = work / "base.txt"
    base_file.write_text("initial base\n", encoding="utf-8")
    subprocess.run(["git", "add", "base.txt"], cwd=work, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=work, check=True)

    dirty_sentinel = work / "uncommitted_outside.txt"
    dirty_sentinel.write_text("pre-existing uncommitted\n", encoding="utf-8")

    target = work / "in_scope_target.txt"
    target.write_text("before\n", encoding="utf-8")

    coordinator = _WriteScopeCoordinator(home)
    events: list[dict[str, object]] = []

    def mock_runner(**_kwargs):
        target.write_text("after modified\n", encoding="utf-8")
        dirty_sentinel.write_text("mutated by worker\n", encoding="utf-8")
        return 0, "completed task\nnow let me restore my changes", "", False, 10

    code = dispatch.dispatch_run(
        prompt="perform bounded edit",
        cwd=str(work),
        mode="accept-edits",
        write_paths=[str(target)],
        temp_command_permissions=True,
        coordinator=coordinator,
        run_agy_fn=mock_runner,
        operation_hook=events.append,
    )

    assert code == 1
    assert coordinator.acquire_count == 1
    assert coordinator.claim.released is True

    failure_events = [e for e in events if e.get("phase") == "CLASSIFYING_FAILURE"]
    assert len(failure_events) >= 1
    assert failure_events[-1].get("failure_kind") == "SCOPE_VIOLATION_UNAUTHORIZED_MUTATION"
    assert failure_events[-1].get("reconciliation_required") is True


def test_write_scope_clean_completion_verified_in_scope(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=work, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=work, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=work, check=True)

    base_file = work / "base.txt"
    base_file.write_text("initial base\n", encoding="utf-8")
    subprocess.run(["git", "add", "base.txt"], cwd=work, check=True)
    subprocess.run(["git", "commit", "-qm", "initial"], cwd=work, check=True)

    target = work / "target.txt"
    target.write_text("initial\n", encoding="utf-8")

    coordinator = _WriteScopeCoordinator(home)
    events: list[dict[str, object]] = []

    def mock_runner(**_kwargs):
        target.write_text("updated in scope\n", encoding="utf-8")
        return 0, "edited target successfully", "", False, 5

    code = dispatch.dispatch_run(
        prompt="edit target",
        cwd=str(work),
        mode="accept-edits",
        write_paths=[str(target)],
        temp_command_permissions=True,
        coordinator=coordinator,
        run_agy_fn=mock_runner,
        operation_hook=events.append,
    )

    assert code == 0
    assert coordinator.acquire_count == 1
    assert not any(event.get("failure_kind") for event in events)


def test_scope_violation_persisted_in_operation_journal(tmp_path: Path) -> None:
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=work, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=work, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=work, check=True)

    tracked = work / "tracked.txt"
    tracked.write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=work, check=True)
    subprocess.run(["git", "commit", "-qm", "base"], cwd=work, check=True)

    journal = dispatch.AgyOperationJournal(tmp_path / "operations")
    op_id = dispatch.new_operation_id()
    journal.create(
        operation_id=op_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(work),
        provider="agy",
        model="claude-sonnet-4-6",
        effort="medium",
        prompt_sha256="f" * 64,
        runtime_revision="c" * 40,
    )
    journal.update(op_id, write_paths=["tracked.txt"])
    journal.mark_started(op_id, pid=os.getpid())

    out_of_scope = work / "unauthorized.txt"
    out_of_scope.write_text("unauthorized data\n", encoding="utf-8")

    terminal = journal.mark_terminal(
        op_id,
        status="COMPLETED",
        exit_code=0,
        cwd=str(work),
    )

    assert terminal["status"] == "FAILED"
    assert terminal["failure_kind"] == "SCOPE_VIOLATION_UNAUTHORIZED_MUTATION"
    assert terminal["scope_validation_state"] == "VIOLATION_OUT_OF_SCOPE"
    assert "unauthorized.txt" in terminal["scope_violations"]

    read_record = journal.read(op_id)
    assert read_record["status"] == "FAILED"
    assert read_record["scope_validation_state"] == "VIOLATION_OUT_OF_SCOPE"

    public_view = dispatch.direct_operation_journal.public_operation_view(read_record)
    assert public_view["write_paths"] == ["tracked.txt"]
    assert public_view["scope_validation_state"] == "VIOLATION_OUT_OF_SCOPE"
    assert public_view["scope_violations"] == ["unauthorized.txt"]


def test_canonicalize_agy_model_resolves_claude_opus() -> None:
    assert dispatch.canonicalize_agy_model("claude-opus-4-6") == "claude-opus-4-6-thinking"
    assert dispatch.canonicalize_agy_model("claude-opus") == "claude-opus-4-6-thinking"
    assert dispatch.canonicalize_agy_model("claude-3-opus") == "claude-opus-4-6-thinking"
    assert dispatch.canonicalize_agy_model("gemini-3.8-flash") == "gemini-3.8-flash"
    assert dispatch.canonicalize_agy_model(None) is None


def test_parse_agy_attestation_matches_canonical_model(tmp_path: Path) -> None:
    log = tmp_path / "agy.log"
    log.write_text(
        "\n".join([
            'I0000 model_resolver.go:116] model alias "claude-opus-4-6-thinking" resolved to "claude-opus-4-6-thinking"',
            "I0000 server.go:1239] Created conversation aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        ])
        + "\n",
        encoding="utf-8",
    )
    res = dispatch._parse_agy_attestation(log, requested_model="claude-opus-4-6")
    assert res["observed_model"] == "claude-opus-4-6-thinking"
    assert res["provider_session_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_quota_preflight_progress_projects_admission_state(tmp_path: Path, monkeypatch) -> None:
    op_root = tmp_path / "ops"
    journal = dispatch.AgyOperationJournal(op_root)
    op_id = dispatch.new_operation_id()
    journal.create(
        operation_id=op_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model="gemini-3.8-flash",
        effort="medium",
        prompt_sha256="abc",
        runtime_revision="r" * 40,
    )
    events: list[dict[str, object]] = []

    now_iso = datetime.now(timezone.utc).isoformat()
    snapshot = {
        "checked_at": now_iso,
        "accounts": [
            {
                "account": "test-acct",
                "ok": True,
                "checked_at": now_iso,
                "groups": {
                    "Gemini Models": {
                        "weekly": {"status": "known", "remaining_pct": 80.0, "reset_at": None}
                    }
                },
            }
        ],
    }
    monkeypatch.setattr(dispatch, "_load_quota_snapshot", lambda: snapshot)

    class FakeClaim:
        internal_id = "test-acct"
        account_alias_hash = "abcdef012345"
        lease_id_hash = "123456abcdef"
        lease = type("L", (), {"execution_env": {}})()

    class FakeCoordinator:
        def acquire_claim(self, **kwargs):
            return FakeClaim()

        def close(self):
            pass

    monkeypatch.setattr(dispatch, "run_agy", lambda **kwargs: (0, "ok", "", False, 100))

    code = dispatch.dispatch_run(
        prompt="hello",
        cwd=str(tmp_path),
        mode="plan",
        model="gemini-3.8-flash",
        coordinator=FakeCoordinator(),
        operation_hook=lambda ev: events.append(ev),
    )
    assert code == 0
    admitted = [
        ev["quota_preflight_progress"]
        for ev in events
        if ev.get("quota_preflight_progress", {}).get("phase") == "PREFLIGHT_ADMITTED"
    ]
    assert len(admitted) == 1
    assert admitted[0]["admission_state"] == "KNOWN_ELIGIBLE"
    assert admitted[0]["probe_state"] == "PROBE_OK"
    assert admitted[0]["quota_state"] == "weekly"
    assert admitted[0]["account_alias_hash"] == "abcdef012345"


def test_cleanup_reconciled_lease_accepts_completed_terminal_exit_without_provider_alive_after(
    tmp_path: Path,
    monkeypatch,
) -> None:
    leases = tmp_path / "leases"
    monkeypatch.setattr(dispatch, "LEASES_DIR", leases)
    record = {
        "status": "COMPLETED",
        "phase": "TERMINAL",
        "exit_code": 0,
        "provider_process_state": "EXITED",
        "has_unresolved_external_effect": False,
        "account_alias_hash": "a" * 12,
        "lease_id_hash": "b" * 12,
        "pid": 4242,
        "reconciliation": {},
    }

    result = dispatch._cleanup_reconciled_lease(record)

    assert result == {"result": "ALREADY_ABSENT"}


def test_cleanup_reconciled_lease_completed_terminal_exit_removes_exact_receipt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    leases = tmp_path / "leases"
    leases.mkdir()
    monkeypatch.setattr(dispatch, "LEASES_DIR", leases)
    alias_hash = "a" * 12
    lease_hash = "b" * 12
    receipt = leases / f"{alias_hash}.receipt.json"
    receipt.write_text(
        json.dumps({
            "account_alias_hash": alias_hash,
            "lease_id_hash": lease_hash,
            "pid": 4242,
        })
        + "\n",
        encoding="utf-8",
    )
    record = {
        "status": "COMPLETED",
        "phase": "TERMINAL",
        "exit_code": 0,
        "provider_process_state": "EXITED",
        "has_unresolved_external_effect": False,
        "account_alias_hash": alias_hash,
        "lease_id_hash": lease_hash,
        "pid": 4242,
        "reconciliation": {},
    }

    result = dispatch._cleanup_reconciled_lease(record)

    assert result == {"result": "LEASE_RECEIPT_REMOVED"}
    assert receipt.exists() is False


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"status": "FAILED"}, "NOT_SAFE_TO_CLEAN"),
        ({"phase": "RECONCILE_REQUIRED"}, "NOT_SAFE_TO_CLEAN"),
        ({"exit_code": 1}, "NOT_SAFE_TO_CLEAN"),
        ({"provider_process_state": "RUNNING"}, "NOT_SAFE_TO_CLEAN"),
        ({"has_unresolved_external_effect": True}, "NOT_SAFE_TO_CLEAN"),
    ],
)
def test_cleanup_reconciled_lease_completed_terminal_fallback_fails_closed(
    tmp_path: Path,
    monkeypatch,
    changes: dict,
    expected: str,
) -> None:
    monkeypatch.setattr(dispatch, "LEASES_DIR", tmp_path / "leases")
    record = {
        "status": "COMPLETED",
        "phase": "TERMINAL",
        "exit_code": 0,
        "provider_process_state": "EXITED",
        "has_unresolved_external_effect": False,
        "account_alias_hash": "a" * 12,
        "lease_id_hash": "b" * 12,
        "pid": 4242,
        "reconciliation": {},
        **changes,
    }

    assert dispatch._cleanup_reconciled_lease(record)["result"] == expected


def test_reconcile_completed_terminal_persists_provider_absence_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    operation_root = tmp_path / "operations"
    journal = dispatch.AgyOperationJournal(operation_root)
    operation_id = dispatch.new_operation_id()
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model="gemini-test",
        effort="medium",
        prompt_sha256="a" * 64,
        runtime_revision="b" * 40,
    )
    journal.update(
        operation_id,
        status="COMPLETED",
        phase="TERMINAL",
        exit_code=0,
        provider_process_state="EXITED",
        has_unresolved_external_effect=False,
        account_alias_hash="a" * 12,
        lease_id_hash="b" * 12,
        pid=4242,
    )
    monkeypatch.setattr(dispatch, "LEASES_DIR", tmp_path / "leases")

    reconciled = dispatch._reconcile_operation(journal, operation_id)

    assert reconciled["status"] == "COMPLETED"
    assert reconciled["phase"] == "TERMINAL"
    assert reconciled["reconciliation"]["provider_alive_after"] is False
    assert reconciled["reconciliation"]["lease_cleanup"]["result"] == "ALREADY_ABSENT"


def test_normalize_account_hash() -> None:
    # 12-char hex string is preserved and lowercased
    assert dispatch._normalize_account_hash("fd84db4038d7") == "fd84db4038d7"
    assert dispatch._normalize_account_hash("FD84DB4038D7") == "fd84db4038d7"
    # Alias is hashed with SHA-256 and truncated to 12 hex chars
    import hashlib
    expected_google_08 = hashlib.sha256(b"google-08").hexdigest()[:12]
    assert dispatch._normalize_account_hash("google-08") == expected_google_08


def test_dispatch_run_forwards_exclude_accounts_to_lease_coordinator(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured_exclude_hashes: list[set[str]] = []

    class FakeClaim:
        internal_id = "test-acct"
        account_alias_hash = "abcdef012345"
        lease_id_hash = "123456abcdef"
        lease = type("L", (), {"execution_env": {}})()

    class FakeAccount:
        alias = "google-08"

    class FakeManager:
        _use_real_manager = False
        _accounts = [FakeAccount()]

    class FakeCoordinator:
        manager = FakeManager()

        def acquire_claim(self, **kwargs):
            captured_exclude_hashes.append(kwargs.get("exclude_hashes", set()))
            return FakeClaim()

        def close(self):
            pass

    monkeypatch.setattr(dispatch, "run_agy", lambda **kwargs: (0, "ok", "", False, 100))

    code = dispatch.dispatch_run(
        prompt="hello",
        cwd=str(tmp_path),
        mode="plan",
        model="gemini-3.8-flash",
        coordinator=FakeCoordinator(),
        exclude_accounts=["google-08", "fd84db4038d7"],
    )
    assert code == 0
    assert len(captured_exclude_hashes) == 1
    import hashlib
    expected_google_08 = hashlib.sha256(b"google-08").hexdigest()[:12]
    assert captured_exclude_hashes[0] == {expected_google_08, "fd84db4038d7"}


def test_main_cli_parses_and_forwards_exclude_account(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured_dispatch_run_kwargs = {}

    def fake_dispatch_run(**kwargs):
        captured_dispatch_run_kwargs.update(kwargs)
        return 0

    monkeypatch.setattr(dispatch, "dispatch_run", fake_dispatch_run)

    rc = dispatch.main([
        "--prompt",
        "test exclude",
        "--cwd",
        str(tmp_path),
        "--exclude-account",
        "google-08",
        "--exclude-account",
        "fd84db4038d7",
    ])
    assert rc == 0
    assert captured_dispatch_run_kwargs.get("exclude_accounts") == ["google-08", "fd84db4038d7"]

def test_resolve_excluded_account_hashes_rejects_unknown_alias() -> None:
    class Account:
        alias = "google-08"

    class Manager:
        _use_real_manager = False
        _accounts = [Account()]

    with pytest.raises(ValueError, match="UNKNOWN_EXCLUDED_ACCOUNT_ALIAS:google-080"):
        dispatch._resolve_excluded_account_hashes(["google-080"], manager=Manager())


def test_background_spawn_persists_normalized_exclusion_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeProcess:
        pid = 424242

    captured: dict[str, object] = {}

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        return FakeProcess()

    monkeypatch.setattr(dispatch.subprocess, "Popen", fake_popen)
    root = tmp_path / "ops"

    record = dispatch._spawn_background_operation(
        prompt="bounded exclusion evidence",
        cwd=str(tmp_path),
        mode="plan",
        model="gemini-3.8-flash",
        effort="low",
        timeout=60,
        max_calls=1,
        pool_wait_timeout=1.0,
        allow=[],
        deny=[],
        temp_command_permissions=False,
        operation_root=root,
        exclude_accounts=["FD84DB4038D7"],
    )

    assert record["excluded_account_hashes"] == ["fd84db4038d7"]
    assert dispatch.public_operation_view(record)["excluded_account_hashes"] == [
        "fd84db4038d7"
    ]
    argv = captured["argv"]
    assert argv[argv.index("--exclude-account") + 1] == "fd84db4038d7"


def test_foreground_hcom_operation_persists_and_forwards_exclusions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib

    expected_hash = hashlib.sha256(b"google-08").hexdigest()[:12]
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        dispatch,
        "_resolve_excluded_account_hashes",
        lambda accounts, **_kwargs: {expected_hash},
    )

    def fake_dispatch_hcom_collab(**kwargs):
        captured.update(kwargs)
        return 0

    monkeypatch.setattr(dispatch, "dispatch_hcom_collab", fake_dispatch_hcom_collab)

    operation_root = tmp_path / "operations"
    code = dispatch._run_foreground_hcom_operation(
        cwd=str(tmp_path),
        hcom_args=[],
        model="gemini-3.8-flash",
        pool_wait_timeout=1.0,
        operation_root=operation_root,
        exclude_accounts=["google-08"],
    )

    assert code == 0
    assert captured["exclude_accounts"] == [expected_hash]
    records = list((operation_root / "operations").glob("*/operation.json"))
    assert len(records) == 1
    record = json.loads(records[0].read_text(encoding="utf-8"))
    assert record["excluded_account_hashes"] == [expected_hash]
    assert dispatch.public_operation_view(record)["excluded_account_hashes"] == [
        expected_hash
    ]


def test_rotation_success_clears_recovered_failure_kind(tmp_path: Path) -> None:
    work = tmp_path / "repo"
    work.mkdir()
    subprocess.run(["git", "init", str(work)], check=True, capture_output=True)
    home = tmp_path / "home"
    home.mkdir()

    class Coordinator(_WriteScopeCoordinator):
        def __init__(self, root: Path) -> None:
            super().__init__(root)
            self.rotated_claim = _WriteScopeClaim(root)
            self.rotated_claim.account_alias_hash = "write-scope-2"
            self.rotated_claim.lease_id_hash = "lease-write-2"
            self.rotated_claim.internal_id = "write-scope-account-2"
            self.rotation_count = 0

        def rotate_claim(self, **kwargs):
            self.rotation_count += 1
            kwargs["current_claim"].release()
            return self.rotated_claim

    coordinator = Coordinator(home)
    calls = 0
    events: list[dict[str, object]] = []

    def runner(**_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return 1, "", "RESOURCE_EXHAUSTED: quota exhausted", False, 10
        return 0, "ok", "", False, 10

    code = dispatch.dispatch_run(
        prompt="rotate then succeed",
        cwd=str(work),
        mode="plan",
        coordinator=coordinator,
        run_agy_fn=runner,
        operation_hook=events.append,
    )

    classified = [event for event in events if event.get("phase") == "CLASSIFYING_FAILURE"]
    executing = [event for event in events if event.get("phase") == "EXECUTING"]
    folded: dict[str, object] = {}
    for event in events:
        folded.update(event)

    assert code == 0
    assert calls == 2
    assert coordinator.rotation_count == 1
    assert len(classified) == 1
    assert classified[0]["failure_kind"] == "PROVIDER_QUOTA_EXHAUSTED_PRE_EFFECT"
    assert len(executing) == 2
    assert executing[1]["failure_kind"] is None
    assert folded["attempts"] == 2
    assert folded["rotations"] == 1
    assert folded["failure_kind"] is None


def test_rotation_second_failure_projects_terminal_failure_kind(tmp_path: Path) -> None:
    work = tmp_path / "repo"
    work.mkdir()
    subprocess.run(["git", "init", str(work)], check=True, capture_output=True)
    home = tmp_path / "home"
    home.mkdir()

    class Coordinator(_WriteScopeCoordinator):
        def __init__(self, root: Path) -> None:
            super().__init__(root)
            self.rotated_claim = _WriteScopeClaim(root)
            self.rotated_claim.account_alias_hash = "write-scope-2"
            self.rotated_claim.lease_id_hash = "lease-write-2"
            self.rotated_claim.internal_id = "write-scope-account-2"
            self.rotation_count = 0

        def rotate_claim(self, **kwargs):
            self.rotation_count += 1
            kwargs["current_claim"].release()
            return self.rotated_claim

    coordinator = Coordinator(home)
    calls = 0
    events: list[dict[str, object]] = []

    def runner(**_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return 1, "", "RESOURCE_EXHAUSTED: quota exhausted", False, 10
        return 2, "", "syntax failure", False, 10

    code = dispatch.dispatch_run(
        prompt="rotate then fail",
        cwd=str(work),
        mode="plan",
        coordinator=coordinator,
        run_agy_fn=runner,
        operation_hook=events.append,
    )

    classified = [event for event in events if event.get("phase") == "CLASSIFYING_FAILURE"]
    folded: dict[str, object] = {}
    for event in events:
        folded.update(event)

    assert code == 2
    assert calls == 2
    assert coordinator.rotation_count == 1
    assert [event["failure_kind"] for event in classified] == [
        "PROVIDER_QUOTA_EXHAUSTED_PRE_EFFECT",
        "SYNTAX_OR_IMPLEMENTATION_ERROR",
    ]
    assert folded["attempts"] == 2
    assert folded["rotations"] == 1
    assert folded["failure_kind"] == "SYNTAX_OR_IMPLEMENTATION_ERROR"
