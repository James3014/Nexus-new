"""Regression tests for the canonical Agy dispatch wrapper."""

from __future__ import annotations

import os
import stat
import subprocess
from datetime import datetime, timezone
from importlib.machinery import SourceFileLoader
from pathlib import Path

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
