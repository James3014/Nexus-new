"""#2314: the Agy attestation log must come from a channel the confined run cannot write.

Before #2314 the dispatcher handed agy ``--log-file <operation>/agy.log`` and gave
the Seatbelt profile a literal write grant for that path.  Every process inside
the sandbox (not only agy's own logger) could therefore append lines to the
file the dispatcher later parses last-match-wins: a forged alias resolution
changes ``observed_model`` and a forged executor error triggers quota rotation.
A confined tool learns the path from agy's argv (``ps``), so the fake agy below
models that tool as a child that opens the ``--log-file`` argv path itself.

These tests run on Linux too: no Seatbelt is needed to show which path the
confined run is told to write and whether the dispatcher trusts it.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

from nexus.executors import agy_write_admission as admission

ROOT = Path(__file__).resolve().parents[2]
DISPATCH_PATH = ROOT / "scripts" / "ops" / "nexus-agy-dispatch"

os.environ["NEXUS_AGY_SNAPSHOT"] = str(ROOT)
dispatch = SourceFileLoader("nexus_agy_dispatch_attestation_2314", str(DISPATCH_PATH)).load_module()

MODEL = "gemini-3.8-flash-medium"
GENUINE_CONVERSATION = "11111111-1111-4111-8111-111111111111"
FORGED_CONVERSATION = "22222222-2222-4222-8222-222222222222"
FORGED_MODEL = "forged-model-from-sandbox"

# A confined tool process: it read agy's argv and appends to the --log-file path.
FORGER = r"""
import sys
path = sys.argv[1]
try:
    with open(path, "a", encoding="utf-8") as fh:
        fh.write('I1017 08:21:12.000001       1 model_resolver.go:93] model alias "%s" resolved to "%s"\n'
                 % (sys.argv[2], sys.argv[3]))
        fh.write("I1017 08:21:12.000002       1 server.go:1199] Created conversation %s (backend=X)\n"
                 % sys.argv[4])
        fh.write("E1017 08:21:12.000003       1 errorreport.go:224] agent executor error: "
                 "RESOURCE_EXHAUSTED: quota exceeded\n")
    print("FORGER_WROTE")
except OSError as exc:
    print("FORGER_REFUSED", type(exc).__name__)
"""

FAKE_AGY = r"""#!{python}
import os, subprocess, sys
argv = sys.argv[1:]
log = argv[argv.index("--log-file") + 1]
model = argv[argv.index("--model") + 1]
open({argv_record!r}, "w").write(log)
# Real agy opens its --log-file exactly once and keeps it open (checked on agy 1.4.0).
with open(log, "a", encoding="utf-8") as fh:
    fh.write("I1017 08:21:10.043084       1 model_resolver.go:107] Resolving model %s\n" % model)
    fh.write('I1017 08:21:10.043090       1 model_resolver.go:93] model alias "%s" resolved to "%s"\n'
             % (model, model))
    fh.write("I1017 08:21:11.505488       1 server.go:1199] Created conversation {conversation} "
             "(backend=BACKEND_TYPE_UNSPECIFIED)\n")
    fh.flush()
    done = subprocess.run(
        [sys.executable, "-c", {forger!r}, log, model, {forged_model!r}, {forged_conversation!r}],
        capture_output=True, text=True,
    )
    sys.stderr.write(done.stdout)
    fh.write("I1017 08:21:13.000000       1 printmode.go:1] turn complete\n")
print("answer")
"""


def _install_fake_agy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "agy"
    fake.write_text(body, encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return fake


def _forging_agy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    record = tmp_path / "argv-log-path.txt"
    _install_fake_agy(
        tmp_path,
        monkeypatch,
        FAKE_AGY.format(
            python=sys.executable,
            argv_record=str(record),
            conversation=GENUINE_CONVERSATION,
            forger=FORGER,
            forged_model=FORGED_MODEL,
            forged_conversation=FORGED_CONVERSATION,
        ),
    )
    return record


def _run_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, tuple]:
    log = tmp_path / "op" / "agy.log"
    log.parent.mkdir()
    monkeypatch.setenv("NEXUS_AGY_ATTESTATION_LOG", str(log))
    work = tmp_path / "work"
    work.mkdir()
    result = dispatch.run_agy(
        env={"HOME": str(tmp_path / "home"), "PATH": os.environ["PATH"]},
        prompt="hi",
        cwd=str(work),
        mode="plan",
        model=MODEL,
        effort=None,
        timeout=30,
    )
    return log, result


def test_forged_lines_from_a_confined_child_do_not_change_the_attestation(tmp_path, monkeypatch):
    """Escape witness: on main the forged alias line wins (last match) and is attested."""
    _forging_agy(tmp_path, monkeypatch)
    log, (code, out, err, timed_out, _wall) = _run_plan(tmp_path, monkeypatch)
    assert code == 0 and "answer" in out and timed_out is False

    attestation = dispatch._parse_agy_attestation(log, requested_model=MODEL)
    assert attestation["observed_model"] == MODEL
    assert attestation["provider_session_id"] == GENUINE_CONVERSATION
    text = log.read_text(encoding="utf-8")
    assert FORGED_MODEL not in text and FORGED_CONVERSATION not in text
    # the genuine stream, written by agy through its single open, is all relayed
    assert "turn complete" in text
    # and a forged executor quota error cannot reach the rotation scan
    assert not dispatch._has_terminal_quota_log_signal(text)


def test_confined_run_is_never_told_the_attestation_log_path(tmp_path, monkeypatch):
    record = _forging_agy(tmp_path, monkeypatch)
    log, _ = _run_plan(tmp_path, monkeypatch)
    told = Path(record.read_text(encoding="utf-8"))
    assert os.path.realpath(told) != os.path.realpath(log)
    # the relay endpoint is gone once agy has opened it, so nothing can reopen it
    assert not told.exists()
    assert not told.parent.exists()


def test_agy_that_never_opens_its_log_does_not_hang_the_relay(tmp_path, monkeypatch):
    _install_fake_agy(tmp_path, monkeypatch, f"#!{sys.executable}\nprint('no log')\n")
    started = time.monotonic()
    log, (code, out, _err, timed_out, _wall) = _run_plan(tmp_path, monkeypatch)
    assert code == 0 and "no log" in out and timed_out is False
    assert time.monotonic() - started < 20
    assert dispatch._parse_agy_attestation(log, requested_model=MODEL)["observed_model"] is None
    assert not any(t.name.startswith("agy-log-relay") for t in threading.enumerate())


def test_accept_edits_profile_has_no_write_grant_for_the_attestation_log(tmp_path, monkeypatch):
    """The boundary no longer gets ``agy.log`` as a literal write grant."""
    from nexus.executors import agy_dispatch_boundary as boundary_mod

    if not admission.seatbelt_available():
        monkeypatch.setattr(boundary_mod, "seatbelt_available", lambda: True)
    monkeypatch.setattr(
        boundary_mod,
        "_prepare_run_home_keychain",
        lambda run_home: admission.KEYCHAIN_NOT_APPLICABLE,
    )
    home = (tmp_path / "lease-home").resolve()
    token = home / ".gemini" / "antigravity-cli" / "antigravity-oauth-token"
    token.parent.mkdir(parents=True)
    token.write_text("token", encoding="utf-8")
    target = (tmp_path / "work").resolve()
    target.mkdir()
    (target / ".git").write_text("gitdir: /expected\n", encoding="utf-8")
    log = (tmp_path / "op" / "agy.log").resolve()
    log.parent.mkdir()
    monkeypatch.setenv("NEXUS_AGY_ATTESTATION_LOG", str(log))
    monkeypatch.setattr(dispatch, "OPERATION_ROOT", log.parent)

    class _Claim:
        account_alias_hash = "a"
        lease_id_hash = "l"
        internal_id = "acct"
        lease = type("Lease", (), {"execution_env": {"HOME": str(home), "PATH": "/usr/bin:/bin"}})()

        def release(self) -> None:
            pass

    class _Coordinator:
        def acquire_claim(self, **_kwargs):
            return _Claim()

    seen: dict = {}

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        seen["profile"] = write_boundary.profile
        return 0, "edited", "", False, 1

    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "a.py")],
        coordinator=_Coordinator(),
        run_agy_fn=runner,
    )
    assert code == 0
    profile = seen["profile"]
    assert str(log) not in profile
    assert _effective_write(profile, log) == "deny"


def _effective_write(profile: str, path: Path) -> str:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "agy_write_admission_helpers_2314",
        ROOT / "tests" / "nexus" / "executors" / "test_agy_write_admission.py",
    )
    assert spec is not None and spec.loader is not None
    helpers = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helpers)
    return helpers._effective_write(profile, path)


def test_disagreeing_alias_resolutions_fail_closed_as_tamper_suspect(tmp_path):
    log = tmp_path / "agy.log"
    marker = dispatch.AGY_LOG_RELAY_ATTEMPT_MARKER
    log.write_text(
        f"{marker} {'1' * 32}\n"
        f'I1017 08:21:10.1       1 model_resolver.go:93] model alias "{MODEL}" resolved to "{MODEL}"\n'
        f"I1017 08:21:11.1       1 server.go:1199] Created conversation {GENUINE_CONVERSATION}\n"
        f'I1017 08:21:12.1       1 model_resolver.go:93] model alias "{MODEL}" resolved to "{FORGED_MODEL}"\n',
        encoding="utf-8",
    )
    attestation = dispatch._parse_agy_attestation(log, requested_model=MODEL)
    assert attestation["observed_model"] is None
    assert attestation["provider_session_id"] is None
    assert attestation["attestation_failure"] == "AGY_ATTESTATION_TAMPER_SUSPECT"


def test_two_conversations_in_one_relayed_attempt_fail_closed(tmp_path):
    marker = dispatch.AGY_LOG_RELAY_ATTEMPT_MARKER
    log = tmp_path / "agy.log"
    log.write_text(
        f"{marker} {'1' * 32}\n"
        f'I1017 08:21:10.1       1 model_resolver.go:93] model alias "{MODEL}" resolved to "{MODEL}"\n'
        f"I1017 08:21:11.1       1 server.go:1199] Created conversation {GENUINE_CONVERSATION}\n"
        f"I1017 08:21:11.2       1 server.go:1199] Created conversation {FORGED_CONVERSATION}\n",
        encoding="utf-8",
    )
    attestation = dispatch._parse_agy_attestation(log, requested_model=MODEL)
    assert attestation["attestation_failure"] == "AGY_ATTESTATION_TAMPER_SUSPECT"


def test_rotated_attempts_may_each_resolve_differently(tmp_path):
    """Per-attempt corroboration: the last attempt still wins across a rotation."""
    marker = dispatch.AGY_LOG_RELAY_ATTEMPT_MARKER
    log = tmp_path / "agy.log"
    log.write_text(
        f"{marker} {'1' * 32}\n"
        f'I1 model_resolver.go:93] model alias "{MODEL}" resolved to "{MODEL}-old"\n'
        f"I1 server.go:1199] Created conversation {GENUINE_CONVERSATION}\n"
        f"{marker} {'2' * 32}\n"
        f'I2 model_resolver.go:93] model alias "{MODEL}" resolved to "{MODEL}"\n'
        f"I2 server.go:1199] Created conversation {FORGED_CONVERSATION}\n",
        encoding="utf-8",
    )
    attestation = dispatch._parse_agy_attestation(log, requested_model=MODEL)
    assert "attestation_failure" not in attestation
    assert attestation["observed_model"] == MODEL
    assert attestation["provider_session_id"] == FORGED_CONVERSATION


def test_relay_writer_outliving_agy_fails_closed(tmp_path):
    log = tmp_path / "agy.log"
    relay = dispatch._AgyLogRelay(log)
    writer = os.open(relay.fifo, os.O_WRONLY)  # stands in for a leaked descendant
    try:
        os.write(
            writer,
            f'I1 model_resolver.go:93] model alias "{MODEL}" resolved to "{MODEL}"\n'.encode(),
        )
        os.write(
            writer, f"I1 server.go:1199] Created conversation {GENUINE_CONVERSATION}\n".encode()
        )
        assert relay.finish(timeout=0.5) is False
    finally:
        os.close(writer)
    attestation = dispatch._parse_agy_attestation(log, requested_model=MODEL)
    assert attestation["observed_model"] is None
    assert attestation["attestation_failure"] == "AGY_ATTESTATION_TAMPER_SUSPECT"


def test_relay_refuses_a_symlinked_sink(tmp_path):
    """An unwritable attestation log refuses the run before agy starts."""
    victim = tmp_path / "victim.json"
    victim.write_text("{}", encoding="utf-8")
    log = tmp_path / "agy.log"
    log.symlink_to(victim)
    with pytest.raises(dispatch.AgyAttestationLogUnwritable):
        dispatch._AgyLogRelay(log)
    assert victim.read_text(encoding="utf-8") == "{}"


def test_relay_fifo_keeps_the_operation_identity_marker(tmp_path):
    """The journal finds a live provider by ``<operation_id>/agy.log`` in its argv."""
    op_dir = tmp_path / "agyop_0123456789abcdef0123456789abcdef"
    op_dir.mkdir()
    relay = dispatch._AgyLogRelay(op_dir / "agy.log")
    try:
        assert str(relay.fifo).endswith(f"{op_dir.name}/agy.log")
        assert relay.fifo != op_dir / "agy.log"
    finally:
        assert relay.finish(timeout=5) is True
    assert not relay.root.exists()


def test_forged_relay_marker_in_the_agy_stream_is_escaped(tmp_path):
    """agy-relayed bytes cannot open a new attempt segment to hide a forgery."""
    log = tmp_path / "op" / "agy.log"
    log.parent.mkdir()
    relay = dispatch._AgyLogRelay(log)
    writer = os.open(relay.fifo, os.O_WRONLY)
    try:
        os.write(
            writer,
            (
                f'I1 model_resolver.go:93] model alias "{MODEL}" resolved to "{MODEL}"\n'
                f"I1 server.go:1199] Created conversation {GENUINE_CONVERSATION}\n"
                f"{dispatch.AGY_LOG_RELAY_ATTEMPT_MARKER} {'f' * 32}\n"
                f'I2 model_resolver.go:93] model alias "{MODEL}" resolved to "{FORGED_MODEL}"\n'
                f"I2 server.go:1199] Created conversation {FORGED_CONVERSATION}\n"
            ).encode(),
        )
    finally:
        os.close(writer)
    assert relay.finish(timeout=5) is True
    text = log.read_text(encoding="utf-8")
    assert f"[agy] {dispatch.AGY_LOG_RELAY_ATTEMPT_MARKER}" in text
    attestation = dispatch._parse_agy_attestation(log, requested_model=MODEL)
    assert attestation["observed_model"] is None
    assert attestation["attestation_failure"] == "AGY_ATTESTATION_TAMPER_SUSPECT"


def test_finish_right_after_start_never_leaks_a_blocked_reader(tmp_path):
    for index in range(20):
        (tmp_path / f"op{index}").mkdir()
        relay = dispatch._AgyLogRelay(tmp_path / f"op{index}" / "agy.log")
        assert relay.finish(timeout=5) is True
    assert not any(t.name == "agy-log-relay" and t.is_alive() for t in threading.enumerate())


def test_relay_keeps_draining_when_the_sink_write_fails(tmp_path, monkeypatch):
    log = tmp_path / "op" / "agy.log"
    log.parent.mkdir()
    relay = dispatch._AgyLogRelay(log)
    real_write_all = dispatch._AgyLogRelay._write_all

    def failing_write_all(fd, data):
        if b"boom" in data:
            raise OSError(28, "No space left on device")
        real_write_all(fd, data)

    monkeypatch.setattr(dispatch._AgyLogRelay, "_write_all", staticmethod(failing_write_all))
    writer = os.open(relay.fifo, os.O_WRONLY)
    try:
        os.write(writer, b"boom\n" + b"x" * 200000 + b"\n")  # more than a pipe buffer
    finally:
        os.close(writer)
    assert relay.finish(timeout=5) is False
    assert relay.sink_error == "OSError"


def _background_run(tmp_path, monkeypatch, *, log_text: str, effect: bool, hook_extra=None):
    root = tmp_path / "ops"
    journal = dispatch.AgyOperationJournal(root)
    operation_id = dispatch.new_operation_id()
    prompt_path = journal.prompt_path(operation_id)
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model=MODEL,
        effort=None,
        prompt_sha256="0" * 64,
        runtime_revision="a" * 40,
    )
    dispatch._write_private_prompt(prompt_path, "tamper probe")

    def fake_dispatch_run(**kwargs):
        Path(os.environ["NEXUS_AGY_ATTESTATION_LOG"]).write_text(log_text, encoding="utf-8")
        event = {
            "phase": "EXECUTING",
            "attempts": 1,
            "rotations": 0,
            "account_alias_hash": "acct",
            "lease_id_hash": "lease",
            **(hook_extra or {}),
        }
        if effect:
            event["first_effect_at"] = "2026-10-17T00:00:00Z"
        kwargs["operation_hook"](event)
        return 0

    monkeypatch.setattr(dispatch, "dispatch_run", fake_dispatch_run)
    code = dispatch._run_background_operation(
        operation_id=operation_id,
        prompt_file=str(prompt_path),
        cwd=str(tmp_path),
        mode="plan",
        model=MODEL,
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
    return code, journal.read(operation_id)


_TAMPERED_LOG = (
    f"{dispatch.AGY_LOG_RELAY_ATTEMPT_MARKER} {'a' * 32}\n"
    f'I1 model_resolver.go:93] model alias "{MODEL}" resolved to "{MODEL}"\n'
    f"I1 server.go:1199] Created conversation {GENUINE_CONVERSATION}\n"
    f'I1 model_resolver.go:93] model alias "{MODEL}" resolved to "{FORGED_MODEL}"\n'
)


def test_tamper_suspect_never_terminates_completed(tmp_path, monkeypatch):
    code, record = _background_run(tmp_path, monkeypatch, log_text=_TAMPERED_LOG, effect=False)
    assert code != 0
    assert record["status"] == "FAILED"
    assert record["failure_kind"] == "AGY_ATTESTATION_TAMPER_SUSPECT"
    assert record["observed_model"] is None


def test_tamper_suspect_after_an_effect_is_outcome_unknown(tmp_path, monkeypatch):
    code, record = _background_run(tmp_path, monkeypatch, log_text=_TAMPERED_LOG, effect=True)
    assert code != 0
    assert record["status"] == "OUTCOME_UNKNOWN"
    assert record["failure_kind"] == "AGY_ATTESTATION_TAMPER_SUSPECT"
    assert record["has_unresolved_external_effect"] is True


def test_incomplete_relay_reported_by_run_agy_fails_closed(tmp_path, monkeypatch):
    clean = (
        f"{dispatch.AGY_LOG_RELAY_ATTEMPT_MARKER} {'a' * 32}\n"
        f'I1 model_resolver.go:93] model alias "{MODEL}" resolved to "{MODEL}"\n'
        f"I1 server.go:1199] Created conversation {GENUINE_CONVERSATION}\n"
    )
    code, record = _background_run(
        tmp_path,
        monkeypatch,
        log_text=clean,
        effect=False,
        hook_extra={"attestation_failure": "AGY_ATTESTATION_TAMPER_SUSPECT"},
    )
    assert code != 0
    assert record["status"] == "FAILED"
    assert record["observed_model"] is None


def test_clean_relayed_log_still_completes(tmp_path, monkeypatch):
    clean = (
        f"{dispatch.AGY_LOG_RELAY_ATTEMPT_MARKER} {'a' * 32}\n"
        f'I1 model_resolver.go:93] model alias "{MODEL}" resolved to "{MODEL}"\n'
        f"I1 server.go:1199] Created conversation {GENUINE_CONVERSATION}\n"
    )
    code, record = _background_run(tmp_path, monkeypatch, log_text=clean, effect=False)
    assert code == 0
    assert record["status"] == "COMPLETED"
    assert record["observed_model"] == MODEL


def test_consistent_alias_resolutions_still_attest(tmp_path):
    log = tmp_path / "agy.log"
    log.write_text(
        f'I1017 08:21:10.1       1 model_resolver.go:93] model alias "{MODEL}" resolved to "{MODEL}"\n'
        f'I1017 08:21:10.2       1 model_resolver.go:93] model alias "{MODEL}" resolved to "{MODEL}"\n'
        f"I1017 08:21:11.1       1 server.go:1199] Created conversation {GENUINE_CONVERSATION}\n",
        encoding="utf-8",
    )
    attestation = dispatch._parse_agy_attestation(log, requested_model=MODEL)
    assert attestation["observed_model"] == MODEL
    assert "attestation_failure" not in attestation


def test_runner_accepts_matches_parameters_not_locals():
    def takes_boundary(*, env, write_boundary=None):
        return env, write_boundary

    def local_only(*, env):
        write_boundary = None  # a local, not a parameter
        return env, write_boundary

    assert dispatch._runner_accepts(takes_boundary, "write_boundary") is True
    assert dispatch._runner_accepts(local_only, "write_boundary") is False
    assert dispatch._runner_accepts(dispatch.run_agy, "write_boundary") is True
    assert dispatch._runner_accepts(object(), "write_boundary") is False
