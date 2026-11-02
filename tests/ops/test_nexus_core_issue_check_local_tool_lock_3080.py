"""Concurrent local runs share one Core tool install directory per pin (#3080)."""

from __future__ import annotations

import importlib.machinery
import importlib.util
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "nexus-core-issue-check-local"
PIN = "c" * 40


def _load_module():
    loader = importlib.machinery.SourceFileLoader("nexus_core_issue_check_local_3080", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def test_a_second_run_waits_for_an_install_in_progress_and_reuses_it(tmp_path, monkeypatch):
    """While one run installs the tool, a second run neither removes that install nor
    installs again: it waits, then reuses the completed install."""
    module = _load_module()
    first_installing = threading.Event()
    release_first = threading.Event()
    installs: list[str] = []

    def fake_run(cmd, *, cwd, env, code, timeout):
        installs.append(threading.current_thread().name)
        if threading.current_thread().name == "first":
            certify = Path(env["UV_TOOL_BIN_DIR"]) / "nexus-certify"
            certify.parent.mkdir(parents=True, exist_ok=True)
            certify.write_text("#!/bin/sh\n")
            first_installing.set()
            assert release_first.wait(10)
            return
        raise module.LocalCheckError(code, "second install attempted")

    monkeypatch.setattr(module, "_run", fake_run)
    results: dict[str, object] = {}

    def call(name: str) -> None:
        try:
            results[name] = module.ensure_tool(tmp_path / "cache", PIN, timeout=5)
        except module.LocalCheckError as exc:  # recorded, asserted below
            results[name] = exc

    first = threading.Thread(target=call, args=("first",), name="first", daemon=True)
    second = threading.Thread(target=call, args=("second",), name="second", daemon=True)
    first.start()
    assert first_installing.wait(10)
    second.start()
    # Give the second run time to reach the install directory while the first is mid-install.
    time.sleep(0.5)
    release_first.set()
    first.join(10)
    second.join(10)
    assert not first.is_alive() and not second.is_alive()

    certify = tmp_path / "cache" / "tools" / PIN / "bin" / "nexus-certify"
    assert results == {"first": certify, "second": certify}
    assert installs == ["first"]
    assert (tmp_path / "cache" / "tools" / PIN / ".nexus-core-tool-ready").read_text() == PIN + "\n"


def test_the_lock_file_sits_outside_the_install_directory(tmp_path, monkeypatch):
    """Removing an unfinished install never removes the lock other runs wait on."""
    module = _load_module()

    def fake_run(cmd, *, cwd, env, code, timeout):
        certify = Path(env["UV_TOOL_BIN_DIR"]) / "nexus-certify"
        certify.parent.mkdir(parents=True, exist_ok=True)
        certify.write_text("#!/bin/sh\n")

    monkeypatch.setattr(module, "_run", fake_run)
    stale = tmp_path / "cache" / "tools" / PIN / "bin" / "nexus-certify"
    stale.parent.mkdir(parents=True)
    stale.write_text("#!/bin/sh\nexit 7\n")

    module.ensure_tool(tmp_path / "cache", PIN, timeout=5)

    assert (tmp_path / "cache" / "tools" / f"{PIN}.lock").is_file()
    assert not (tmp_path / "cache" / "tools" / PIN / f"{PIN}.lock").exists()
