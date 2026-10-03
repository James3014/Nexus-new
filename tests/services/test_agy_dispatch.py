"""Regression tests for the canonical Agy dispatch wrapper."""

from __future__ import annotations

import json
import os
import signal
import stat
import subprocess
import sys
import textwrap
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
    env.update(
        {
            "NEXUS_AGY_REPO_ROOT": str(ROOT),
            "NEXUS_AGY_SNAPSHOT": str(ROOT),
            "NEXUS_AGY_DISPATCH_TARGET": str(target),
        }
    )

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
        kwargs["operation_hook"](
            {
                "phase": "CLASSIFYING_FAILURE",
                "attempts": 1,
                "rotations": 0,
                "failure_kind": "TIMEOUT",
                "timed_out": True,
                "account_alias_hash": "acct",
                "lease_id_hash": "lease",
            }
        )
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
    )

    assert record["status"] == "QUEUED"
    assert record["pid"] == 424242
    assert record["operation_id"].startswith("agyop_")
    raw = (root / "operations" / record["operation_id"] / "operation.json").read_text()
    assert "do not persist this prompt" not in raw
    assert "--operation-run" in captured["argv"]
    assert captured["kwargs"]["start_new_session"] is True
    prompt_path = root / "operations" / record["operation_id"] / ".prompt"
    assert stat.S_IMODE(prompt_path.stat().st_mode) == 0o600


def test_parse_agy_attestation_binds_resolved_model_and_conversation(tmp_path: Path) -> None:
    log = tmp_path / "agy.log"
    log.write_text(
        "\n".join(
            [
                'I0000 model_resolver.go:116] model alias "gemini-3.8-flash" resolved to "gemini-3.8-flash-low"',
                "I0000 model_resolver.go:93] Resolving model gemini-3.8-flash-low",
                "I0000 server.go:1239] Created conversation f67d38d4-f220-4bc0-a216-cef594235952",
            ]
        )
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
        "\n".join(
            [
                'I0000 model_resolver.go:116] model alias "gemini-other" resolved to "gemini-other-low"',
                "I0000 server.go:1239] Created conversation f67d38d4-f220-4bc0-a216-cef594235952",
            ]
        )
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
        "\n".join(
            [
                'I0000 model_resolver.go:116] model alias "gemini-3.8-flash" resolved to "gemini-3.8-flash-low"',
                "I0000 server.go:1239] Created conversation 11111111-1111-1111-1111-111111111111",
                'I0001 model_resolver.go:116] model alias "gemini-3.8-flash" resolved to "gemini-3.8-flash-low-v2"',
                "I0001 server.go:1239] Created conversation 22222222-2222-2222-2222-222222222222",
            ]
        )
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
            "\n".join(
                [
                    'I0000 model_resolver.go:116] model alias "gemini-3.8-flash" resolved to "gemini-3.8-flash-low"',
                    "I0000 server.go:1239] Created conversation f67d38d4-f220-4bc0-a216-cef594235952",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        kwargs["operation_hook"](
            {
                "phase": "EXECUTING",
                "attempts": 1,
                "rotations": 0,
                "account_alias_hash": "acct",
                "lease_id_hash": "lease",
            }
        )
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
        json.dumps(
            {
                "account_alias_hash": alias_hash,
                "lease_id_hash": lease_hash,
                "consumer_id": "agy-operation",
                "claimed_at": 1.0,
                "pid": 4242,
            }
        )
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
        kwargs["operation_hook"](
            {
                "phase": "CLASSIFYING_FAILURE",
                "attempts": 1,
                "rotations": 0,
                "failure_kind": "TIMEOUT",
                "timed_out": True,
                "account_alias_hash": "acct",
                "lease_id_hash": "lease",
            }
        )
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
    op_root = tmp_path / "ops"
    # Pre-create the operation in the *parent* process so the child can use it.
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
