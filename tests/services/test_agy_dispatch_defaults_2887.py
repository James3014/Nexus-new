from __future__ import annotations

import json
import os
import signal
import sys
import time
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
os.environ["NEXUS_AGY_SNAPSHOT"] = str(ROOT)
dispatch = SourceFileLoader(
    "nexus_agy_dispatch_defaults_2887", str(ROOT / "scripts/ops/nexus-agy-dispatch")
).load_module()


class FakeClaim:
    def __init__(self, name: str, root: Path) -> None:
        home = root / name
        home.mkdir()
        self.internal_id = name
        self.account_alias_hash = f"hash-{name}"
        self.lease_id_hash = f"lease-{name}"
        self.lease = SimpleNamespace(
            execution_env={"ACCOUNT": name, "HOME": str(home)}, consumer_id="consumer"
        )
        self.released = False

    def release(self) -> None:
        self.released = True


class FakeCoordinator:
    def __init__(self, root: Path) -> None:
        self.claims = [FakeClaim(name, root) for name in ("a", "b", "c")]
        self.exclusions: list[set[str]] = []
        self.retired: list[tuple[str, str]] = []

    def acquire_claim(self, *, exclude_hashes, **_kwargs):
        self.exclusions.append(set(exclude_hashes))
        return next(c for c in self.claims if c.account_alias_hash not in exclude_hashes)

    def rotate_claim(self, *, current_claim, failure_kind, **kwargs):
        self.retired.append((current_claim.internal_id, failure_kind.value))
        current_claim.release()
        return self.acquire_claim(**kwargs)


@pytest.fixture(autouse=True)
def isolated_dispatch(monkeypatch, tmp_path):
    monkeypatch.delenv("NEXUS_AGY_PROVIDER_STALL_SECONDS", raising=False)
    monkeypatch.setattr(
        dispatch,
        "_apply_dynamic_availability",
        lambda _model: ({}, {"family": "unknown", "snapshot_fresh": True}),
    )
    monkeypatch.setattr(dispatch, "OPERATION_ROOT", tmp_path / "operations")
    monkeypatch.setattr(dispatch, "_runtime_revision", lambda: None)


@pytest.mark.parametrize(
    ("mode", "allow", "kind", "timeout", "stall"),
    [
        ("plan", [], "NO_TOOL_PACKET", 300, 45.0),
        ("plan", ["read_file(docs/**)"], "READ_ONLY_RESEARCH", 600, 45.0),
        ("accept-edits", [], "CODING_BOUNDED", 900, 90.0),
    ],
)
@pytest.mark.parametrize("explicit", [False, True])
def test_parser_resolves_limits_by_profile(tmp_path, mode, allow, kind, timeout, stall, explicit):
    argv = ["--mode", mode]
    for rule in allow:
        argv += ["--allow", rule]
    if explicit:
        argv += ["--timeout", "321", "--provider-stall-seconds", "17"]
    args = dispatch._build_parser().parse_args(argv)
    _, actual_kind, _ = dispatch.build_effective_permission_profile(
        cwd=str(tmp_path), mode=args.mode, allow_rules=args.allow, write_paths=["result.txt"]
    )
    assert actual_kind == kind
    limits = dispatch._resolve_dispatch_limits(kind, args.timeout, args.provider_stall_seconds)
    assert limits == {
        "timeout_seconds": 321 if explicit else timeout,
        "timeout_source": "explicit" if explicit else f"default:{kind}",
        "provider_stall_seconds": 17.0 if explicit else stall,
        "provider_stall_source": "explicit" if explicit else f"default:{kind}",
        "empty_output_min_bytes": 1,
    }


def test_read_only_stall_minimum(monkeypatch):
    monkeypatch.setenv("NEXUS_AGY_PROVIDER_STALL_SECONDS", "40")
    limits = dispatch._resolve_dispatch_limits("NO_TOOL_PACKET", None, None)
    assert limits["provider_stall_seconds"] == 30
    assert (
        dispatch._resolve_dispatch_limits("CODING_BOUNDED", None, None)["provider_stall_seconds"]
        == 40
    )


def _summary(capsys):
    return next(
        json.loads(line.removeprefix("NEXUS_AGY_DISPATCH "))
        for line in capsys.readouterr().err.splitlines()
        if line.startswith("NEXUS_AGY_DISPATCH ")
    )


@pytest.mark.parametrize("allow", [[], ["read_file(docs/**)"]])
@pytest.mark.parametrize("second_output", ["valid answer " * 12, " \n \n"])
def test_empty_output_rotates_once_without_consuming_max_calls(
    tmp_path, capsys, allow, second_output
):
    coordinator = FakeCoordinator(tmp_path)
    calls = []
    events = []

    def runner(*, env, timeout, provider_stall_seconds, **_kwargs):
        calls.append(env["ACCOUNT"])
        assert 0 < timeout <= (600 if allow else 300)
        assert provider_stall_seconds == 45
        return 0, " \n " if len(calls) == 1 else second_output, "", False, 1

    code = dispatch.dispatch_run(
        prompt="read-only task",
        cwd=str(tmp_path),
        allow=allow,
        max_calls=1,
        coordinator=coordinator,
        run_agy_fn=runner,
        operation_hook=events.append,
    )
    summary = _summary(capsys)
    assert calls == ["a", "b"]
    assert coordinator.exclusions == [set(), {"hash-a"}]
    assert coordinator.retired == []  # acquire_claim only: nothing retired
    assert all(c.released for c in coordinator.claims[:2])
    assert not coordinator.claims[2].released
    assert summary["empty_output_failovers"] == 1
    assert summary["attempts"] == 2
    assert summary["rotations"] == 1
    kind = "READ_ONLY_RESEARCH" if allow else "NO_TOOL_PACKET"
    assert summary["timeout_seconds"] == (600 if allow else 300)
    assert summary["timeout_source"] == f"default:{kind}"
    assert summary["provider_stall_seconds"] == 45
    assert summary["provider_stall_source"] == f"default:{kind}"
    assert any(e.get("empty_output_failovers") == 1 for e in events)
    if second_output.strip():
        assert code == 0
        assert summary["status"] == "completed"
    else:
        assert code == 1
        assert summary["status"] == "failed"
        assert summary["failure_kind"] == "AGY_EMPTY_OUTPUT"


@pytest.mark.parametrize("output", ["x", "界", "OK-2467"])
def test_threshold_counts_stripped_utf8_bytes(tmp_path, capsys, output):
    coordinator = FakeCoordinator(tmp_path)
    code = dispatch.dispatch_run(
        prompt="read",
        cwd=str(tmp_path),
        coordinator=coordinator,
        run_agy_fn=lambda **_kwargs: (0, f" \n{output}\n ", "", False, 1),
    )
    assert code == 0
    assert _summary(capsys)["empty_output_failovers"] == 0
    assert len(coordinator.exclusions) == 1


def test_empty_output_failover_never_retires_or_cools_down_the_account(tmp_path, capsys):
    """The blank-answer failover must release the healthy account and lease another
    one through acquire_claim only: rotate_claim / retire_failed_claim and every
    pool-manager cooldown write are forbidden (Gemini r1 BLOCKER on #2894)."""

    class Manager:
        def mark_account_bad(self, *_a, **_k):
            raise AssertionError("empty output must not persist a cooldown")

        def mark_family_unavailable(self, *_a, **_k):
            raise AssertionError("empty output must not retire a model family")

        def quarantine_account(self, *_a, **_k):
            raise AssertionError("empty output must not quarantine")

    order: list[str] = []

    class Coordinator(FakeCoordinator):
        manager = Manager()

        def acquire_claim(self, *, exclude_hashes, **kwargs):
            claim = super().acquire_claim(exclude_hashes=exclude_hashes, **kwargs)
            order.append(f"lease:{claim.internal_id}")
            return claim

        def rotate_claim(self, **_kwargs):
            raise AssertionError("empty output must not go through rotate_claim")

        def retire_failed_claim(self, *_a, **_k):
            raise AssertionError("empty output must not retire the claim")

    coordinator = Coordinator(tmp_path)
    for fake in coordinator.claims:
        original_release = fake.release

        def _release(_orig=original_release, _name=fake.internal_id):
            order.append(f"release:{_name}")
            _orig()

        fake.release = _release
    calls = []

    def runner(*, env, **_kwargs):
        calls.append(env["ACCOUNT"])
        return 0, "" if len(calls) == 1 else "answer " * 20, "", False, 1

    assert (
        dispatch.dispatch_run(
            prompt="read",
            cwd=str(tmp_path),
            coordinator=coordinator,
            run_agy_fn=runner,
            max_calls=1,
        )
        == 0
    )
    assert calls == ["a", "b"]
    assert coordinator.retired == []
    # The healthy account is released exactly once, before the next lease.
    assert order == ["lease:a", "release:a", "lease:b", "release:b"]
    summary = _summary(capsys)
    assert summary["empty_output_failovers"] == 1
    assert summary["rotations"] == 1


def test_empty_output_obeys_total_deadline(tmp_path, monkeypatch, capsys):
    coordinator = FakeCoordinator(tmp_path)
    now = [0.0]
    monkeypatch.setattr(dispatch, "_monotonic", lambda: now[0])

    def runner(**_kwargs):
        now[0] = 297
        return 0, "", "", False, 297000

    code = dispatch.dispatch_run(
        prompt="read",
        cwd=str(tmp_path),
        coordinator=coordinator,
        run_agy_fn=runner,
    )
    assert code == 124
    summary = _summary(capsys)
    assert summary["failure_kind"] == "TIMEOUT"
    assert summary["empty_output_failovers"] == 0
    assert len(coordinator.exclusions) == 1


def test_coding_empty_output_is_not_retried(tmp_path, monkeypatch, capsys):
    coordinator = FakeCoordinator(tmp_path)

    class Boundary:
        def __init__(self, source_env, **_kwargs):
            self.env = source_env

        def cleanup(self):
            pass

        def sweep(self):
            return True

    monkeypatch.setattr(dispatch, "_write_boundary_available", lambda: True)
    monkeypatch.setattr(
        dispatch,
        "_agy_dispatch_boundary",
        lambda: SimpleNamespace(
            prepare_accept_edits_boundary=Boundary,
        ),
    )

    def runner(*, write_boundary, **_kwargs):
        return 0, "", "", False, 1

    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(tmp_path),
        mode="accept-edits",
        write_paths=["result.txt"],
        coordinator=coordinator,
        run_agy_fn=runner,
    )
    assert code == 0
    summary = _summary(capsys)
    assert summary["attempts"] == 1
    assert summary["empty_output_failovers"] == 0
    assert summary["timeout_seconds"] == 900


@pytest.mark.parametrize("explicit", [False, True])
def test_background_preserves_limit_sources(tmp_path, monkeypatch, capsys, explicit):
    spawned = []
    monkeypatch.setattr(
        dispatch,
        "subprocess",
        SimpleNamespace(
            DEVNULL=dispatch.subprocess.DEVNULL,
            Popen=lambda argv, **_kwargs: spawned.append(argv) or SimpleNamespace(pid=os.getpid()),
        ),
    )
    record = dispatch._spawn_background_operation(
        prompt="read",
        cwd=str(tmp_path),
        mode="plan",
        model=None,
        effort=None,
        timeout=123 if explicit else None,
        provider_stall_seconds=17 if explicit else None,
        max_calls=1,
        pool_wait_timeout=None,
        allow=[],
        deny=[],
        temp_command_permissions=False,
        operation_root=tmp_path / "operations",
    )
    assert ("--timeout" in spawned[0]) is explicit
    assert ("--provider-stall-seconds" in spawned[0]) is explicit
    assert record["timeout_seconds"] == (123 if explicit else 300)
    assert record["timeout_source"] == ("explicit" if explicit else "default:NO_TOOL_PACKET")
    assert record["liveness_policy"]["provider_stall_seconds"] == (17 if explicit else 45)
    assert record["empty_output_failovers"] == 0
    dispatch._print_operation(record)
    summary = json.loads(capsys.readouterr().out)
    assert summary["timeout_seconds"] == record["timeout_seconds"]
    assert summary["timeout_source"] == record["timeout_source"]
    assert summary["provider_stall_seconds"] == record["provider_stall_seconds"]
    assert summary["provider_stall_source"] == record["provider_stall_source"]
    assert summary["empty_output_failovers"] == 0


def test_read_only_provider_start_watchdog(tmp_path, monkeypatch):
    fake_agy = tmp_path / "fake-agy"
    fake_agy.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(10)\n")
    fake_agy.chmod(0o700)
    monkeypatch.setattr(dispatch.shutil, "which", lambda _name: str(fake_agy))
    # This test owns the fake child's group; no host process-table scan is needed.
    monkeypatch.setattr(
        dispatch._agy_operation_journal,
        "_stop_process_group",
        lambda pgid, **_kwargs: os.killpg(pgid, signal.SIGTERM),
    )
    monkeypatch.setattr(
        dispatch._agy_operation_journal, "_process_group_alive", lambda _pgid: False
    )
    code, _, err, timed_out, wall_ms = dispatch.run_agy(
        env=os.environ.copy(),
        prompt="read",
        cwd=str(tmp_path),
        mode="plan",
        model=None,
        effort=None,
        timeout=15,
        provider_stall_seconds=0.1,
    )
    assert code != 0
    assert "NEXUS_AGY_NON_PROGRESS:PROVIDER_STALLED" in err
    assert not timed_out
    assert wall_ms < 3000


@pytest.mark.parametrize("second_output", ["answer " * 20, ""])
def test_background_journal_records_empty_output_failover(tmp_path, monkeypatch, second_output):
    coordinator = FakeCoordinator(tmp_path)
    journal = dispatch.AgyOperationJournal(tmp_path / "operations")
    operation_id = dispatch.new_operation_id()
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model=None,
        effort=None,
        prompt_sha256="a" * 64,
        runtime_revision=None,
    )
    prompt = journal.prompt_path(operation_id)
    dispatch._write_private_prompt(prompt, "read")
    actual_dispatch = dispatch.dispatch_run

    def runner(*, env, **_kwargs):
        return 0, "" if env["ACCOUNT"] == "a" else second_output, "", False, 1

    monkeypatch.setattr(
        dispatch,
        "dispatch_run",
        lambda **kwargs: actual_dispatch(
            **kwargs,
            coordinator=coordinator,
            run_agy_fn=runner,
        ),
    )
    monkeypatch.setattr(dispatch, "_parse_agy_attestation", lambda *_a, **_kw: {})
    code = dispatch._run_background_operation(
        operation_id=operation_id,
        prompt_file=str(prompt),
        cwd=str(tmp_path),
        mode="plan",
        model=None,
        effort=None,
        timeout=None,
        max_calls=1,
        pool_wait_timeout=None,
        allow=[],
        deny=[],
        temp_command_permissions=False,
        operation_root=tmp_path / "operations",
    )
    record = journal.read(operation_id)
    assert code == (0 if second_output else 1)
    assert record["status"] == ("COMPLETED" if second_output else "FAILED")
    assert record["empty_output_failovers"] == 1
    assert record["timeout_seconds"] == 300
    assert record["timeout_source"] == "default:NO_TOOL_PACKET"
    assert record["provider_stall_seconds"] == 45
    assert record["failure_kind"] == (None if second_output else "AGY_EMPTY_OUTPUT")


def test_empty_output_kind_never_marks_the_shared_pool_account_bad():
    kind = dispatch._DispatchFailureKind.EMPTY_OUTPUT
    assert dispatch.is_agy_rotation_eligible(kind) is False

    class Manager:
        def mark_account_bad(self, *_a, **_k):
            raise AssertionError("dispatch-local empty output must never persist a cooldown")

    class Pool:
        manager = Manager()

        def retire_failed_claim(self, claim, failure_kind, **kwargs):
            return dispatch.CrossProcessLeaseCoordinator.retire_failed_claim(
                self, claim, failure_kind, **kwargs
            )

    claim = SimpleNamespace(
        released=False, account_alias_hash="hash-a", lease=SimpleNamespace(execution_env={})
    )
    # An un-released claim with the dispatch-local kind: returns before any pool write.
    Pool().retire_failed_claim(claim, kind)


def test_background_child_seeds_limits_before_first_event(tmp_path, monkeypatch):
    # Codex review of #2894: a heartbeat written before dispatch_run's first event used to
    # overwrite the parent's recorded limits with nulls. The child now seeds them itself.
    journal = dispatch.AgyOperationJournal(tmp_path / "operations")
    operation_id = dispatch.new_operation_id()
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model=None,
        effort=None,
        prompt_sha256="a" * 64,
        runtime_revision=None,
        initial_fields={
            **dispatch._resolve_dispatch_limits("NO_TOOL_PACKET", None, None),
            "empty_output_failovers": 0,
        },
    )
    prompt = journal.prompt_path(operation_id)
    dispatch._write_private_prompt(prompt, "read")
    observed = {}

    def slow_dispatch(**_kwargs):
        time.sleep(0.3)  # several heartbeats pass before any dispatch event
        observed["mid_run"] = journal.read(operation_id)
        return 0

    monkeypatch.setattr(dispatch, "dispatch_run", slow_dispatch)
    monkeypatch.setattr(dispatch, "_parse_agy_attestation", lambda *_a, **_kw: {})
    dispatch._run_background_operation(
        operation_id=operation_id,
        prompt_file=str(prompt),
        cwd=str(tmp_path),
        mode="plan",
        model=None,
        effort=None,
        timeout=None,
        max_calls=1,
        pool_wait_timeout=None,
        allow=[],
        deny=[],
        temp_command_permissions=False,
        operation_root=tmp_path / "operations",
        heartbeat_interval=0.05,
    )
    mid = observed["mid_run"]
    assert mid["timeout_seconds"] == 300
    assert mid["timeout_source"] == "default:NO_TOOL_PACKET"
    assert mid["provider_stall_seconds"] == 45
    assert mid["empty_output_failovers"] == 0


@pytest.mark.parametrize("busy", [True, False])
def test_empty_output_pool_failure_reports_pool_status(tmp_path, monkeypatch, capsys, busy):
    # Gemini r2 on #2894: the empty-output re-lease exit used status "failed" and sent no
    # hook event; it now matches the quota-rotation pool exit.
    coordinator = FakeCoordinator(tmp_path)
    real_acquire = dispatch._acquire_claim_queued
    leases = []

    def acquire(*args, **kwargs):
        leases.append(1)
        if len(leases) > 1:
            raise dispatch._PoolClaimFailure(busy=busy, waited_seconds=0.0, recovery={})
        return real_acquire(*args, **kwargs)

    monkeypatch.setattr(dispatch, "_acquire_claim_queued", acquire)
    events = []
    code = dispatch.dispatch_run(
        prompt="read",
        cwd=str(tmp_path),
        coordinator=coordinator,
        run_agy_fn=lambda **_kwargs: (0, " \n", "", False, 1),
        operation_hook=events.append,
    )
    assert code == 75
    summary = _summary(capsys)
    assert summary["status"] == ("pool_busy" if busy else "pool_exhausted")
    assert summary["failure_kind"] == ("AGY_ACCOUNT_POOL_BUSY" if busy else "AGY_EMPTY_OUTPUT")
    assert "pool_queue" in events[-1]
    assert events[-1].get("failure_kind") == ("AGY_ACCOUNT_POOL_BUSY" if busy else None)


def test_terminal_empty_output_forwards_short_answer(tmp_path, capsys):
    # A raised --empty-output-min-bytes can reject a short but real answer; the caller
    # still gets the text, as on every other terminal exit.
    coordinator = FakeCoordinator(tmp_path)
    code = dispatch.dispatch_run(
        prompt="read",
        cwd=str(tmp_path),
        coordinator=coordinator,
        empty_output_min_bytes=100,
        run_agy_fn=lambda **_kwargs: (0, "short answer", "provider note", False, 1),
    )
    assert code == 1
    captured = capsys.readouterr()
    assert captured.out.count("short answer") == 1
    assert "provider note" in captured.err


def test_background_invalid_contract_marks_limits_unresolved(tmp_path, monkeypatch):
    # The parent and the child seed record the same "unresolved" labels as the
    # foreground contract-rejection path, not "default:INVALID".
    with pytest.raises(ValueError):
        dispatch.build_effective_permission_profile(
            cwd=str(tmp_path),
            mode="plan",
            write_paths=[],
            allow_rules=[],
            deny_rules=[],
            temp_command_permissions=True,
        )
    monkeypatch.setattr(
        dispatch,
        "subprocess",
        SimpleNamespace(
            DEVNULL=dispatch.subprocess.DEVNULL,
            Popen=lambda argv, **_kwargs: SimpleNamespace(pid=os.getpid()),
        ),
    )
    record = dispatch._spawn_background_operation(
        prompt="read",
        cwd=str(tmp_path),
        mode="plan",
        model=None,
        effort=None,
        timeout=None,
        provider_stall_seconds=None,
        max_calls=1,
        pool_wait_timeout=None,
        allow=[],
        deny=[],
        temp_command_permissions=True,
        operation_root=tmp_path / "operations",
    )
    assert record["timeout_source"] == "unresolved"
    assert record["provider_stall_source"] == "unresolved"
    assert record["timeout_seconds"] is None
    assert record["liveness_policy"]["provider_stall_seconds"] > 0

    observed = {}

    def slow_dispatch(**_kwargs):
        time.sleep(0.3)
        observed["mid_run"] = dispatch.AgyOperationJournal(tmp_path / "operations").read(
            record["operation_id"]
        )
        return 0

    monkeypatch.setattr(dispatch, "dispatch_run", slow_dispatch)
    monkeypatch.setattr(dispatch, "_parse_agy_attestation", lambda *_a, **_kw: {})
    journal = dispatch.AgyOperationJournal(tmp_path / "operations")
    dispatch._run_background_operation(
        operation_id=record["operation_id"],
        prompt_file=str(journal.prompt_path(record["operation_id"])),
        cwd=str(tmp_path),
        mode="plan",
        model=None,
        effort=None,
        timeout=None,
        max_calls=1,
        pool_wait_timeout=None,
        allow=[],
        deny=[],
        temp_command_permissions=True,
        operation_root=tmp_path / "operations",
        heartbeat_interval=0.05,
    )
    assert observed["mid_run"]["timeout_source"] == "unresolved"
    assert observed["mid_run"]["provider_stall_source"] == "unresolved"
