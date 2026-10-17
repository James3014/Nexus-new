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


def test_accept_edits_profile_has_no_write_grant_for_the_attestation_log(
    tmp_path, monkeypatch
):
    """The boundary no longer gets ``agy.log`` as a literal write grant."""
    from nexus.executors import agy_dispatch_boundary as boundary_mod

    if not admission.seatbelt_available():
        monkeypatch.setattr(boundary_mod, "seatbelt_available", lambda: True)
    monkeypatch.setattr(
        boundary_mod, "_prepare_run_home_keychain", lambda run_home: admission.KEYCHAIN_NOT_APPLICABLE
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
    log.write_text(
        f'I1017 08:21:10.1       1 model_resolver.go:93] model alias "{MODEL}" resolved to "{MODEL}"\n'
        f"I1017 08:21:11.1       1 server.go:1199] Created conversation {GENUINE_CONVERSATION}\n"
        f'I1017 08:21:12.1       1 model_resolver.go:93] model alias "{MODEL}" resolved to "{FORGED_MODEL}"\n',
        encoding="utf-8",
    )
    attestation = dispatch._parse_agy_attestation(log, requested_model=MODEL)
    assert attestation["observed_model"] is None
    assert attestation["provider_session_id"] is None
    assert attestation["attestation_failure"] == "AGY_ATTESTATION_TAMPER_SUSPECT"


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
