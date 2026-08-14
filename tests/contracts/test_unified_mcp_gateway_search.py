"""Contract tests for the bounded ``nexus_search`` literal-search backends.

Covers ripgrep selection, the standard-library fallback, resource limits, file
skips, deterministic ordering, and the requirement that a genuine ripgrep
execution error is never masked by a silent fallback.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

repo_root = str(Path(__file__).resolve().parents[2])
if repo_root in sys.path:
    sys.path.remove(repo_root)
sys.path.insert(0, repo_root)

from nexus.orchestrator import unified_mcp_gateway as gateway_module  # noqa: E402
from nexus.orchestrator.unified_mcp_gateway import (  # noqa: E402
    MAX_SEARCH_FILE_BYTES,
    MAX_SEARCH_LINE_BYTES,
    MAX_SEARCH_RESULTS,
    GatewayInputError,
    UnifiedMCPGateway,
    _bounded_rg_matches,
    _display_search_path,
    _git_ls_files,
    _python_literal_search,
    _run_rg_literal_search,
)


class _StubService:
    def lifecycle_status(self):
        return {"active_targets": 0, "actionable_count": 0}

    def list_actionable_tasks(self, *, include_details=False):
        return {"actionable_count": 0, "details_included": include_details, "tasks": []}


@pytest.fixture
def search_root(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    return tmp_path


def _gateway() -> UnifiedMCPGateway:
    return UnifiedMCPGateway(service=_StubService())


def _write_fake_executable(body: str, tmp_path: Path) -> str:
    """Write an executable fake rg script that accepts arbitrary argv."""
    fake = tmp_path / "fake-rg"
    fake.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
    fake.chmod(0o755)
    return str(fake)


def test_search_uses_ripgrep_backend_when_rg_is_available(monkeypatch):
    rg = shutil.which("rg")
    if rg is None:
        pytest.skip("rg is not installed on this host")
    monkeypatch.setattr(gateway_module.shutil, "which", lambda name: rg if name == "rg" else None)
    payload = _gateway()._search({"pattern": "def _search", "path": "nexus/orchestrator/unified_mcp_gateway.py"})
    assert payload["schema"] == "nexus.workspace_search.v1"
    assert payload["backend"] == "ripgrep"
    assert payload["matches"]
    assert payload["truncated"] is False
    assert payload["path"] == "nexus/orchestrator/unified_mcp_gateway.py"
    assert all(not line.startswith("/") for line in payload["matches"])


def test_search_uses_python_fallback_when_rg_is_missing(monkeypatch):
    monkeypatch.setattr(gateway_module.shutil, "which", lambda name: None)
    payload = _gateway()._search({"pattern": "def _search", "path": "nexus/orchestrator/unified_mcp_gateway.py"})
    assert payload["schema"] == "nexus.workspace_search.v1"
    assert payload["backend"] == "python"
    assert payload["matches"]
    assert payload["truncated"] is False
    assert all(not line.startswith("/") for line in payload["matches"])


def test_search_fallback_is_not_used_for_general_rg_failure(monkeypatch):
    def fail(*_args, **_kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(gateway_module, "_run_rg_literal_search", fail)
    monkeypatch.setattr(gateway_module.shutil, "which", lambda name: "/usr/bin/rg")
    with pytest.raises(OSError, match="permission denied"):
        _gateway()._search({
            "pattern": "needle",
            "path": "nexus/orchestrator/unified_mcp_gateway.py",
        })


def test_search_falls_back_when_rg_launch_raises_file_not_found(monkeypatch):
    monkeypatch.setattr(gateway_module.shutil, "which", lambda name: "/nonexistent/rg-binary")
    payload = _gateway()._search({"pattern": "def _search", "path": "nexus/orchestrator/unified_mcp_gateway.py"})
    assert payload["backend"] == "python"
    assert payload["matches"]


def test_search_does_not_mask_general_rg_execution_error(monkeypatch, tmp_path):
    fake = tmp_path / "fake-rg"
    fake.write_text("#!/bin/sh\necho 'rg exploded' >&2\nexit 2\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setattr(gateway_module.shutil, "which", lambda name: str(fake) if name == "rg" else None)
    with pytest.raises(RuntimeError, match="rg exploded"):
        _gateway()._search({"pattern": "needle", "path": "nexus/orchestrator/unified_mcp_gateway.py"})


def test_fallback_searches_single_file(search_root):
    (search_root / "a.txt").write_text("alpha beta\ngamma\n", encoding="utf-8")
    matches, truncated = _python_literal_search(root=search_root, target=search_root / "a.txt", pattern="beta")
    assert truncated is False
    assert matches == ["a.txt:1:alpha beta"]


def test_fallback_searches_directory(search_root):
    (search_root / "dir").mkdir()
    (search_root / "dir" / "one.py").write_text("needle here\n", encoding="utf-8")
    (search_root / "dir" / "two.py").write_text("no match\nneedle two\n", encoding="utf-8")
    matches, truncated = _python_literal_search(root=search_root, target=search_root / "dir", pattern="needle")
    assert truncated is False
    assert matches == ["dir/one.py:1:needle here", "dir/two.py:2:needle two"]


def test_fallback_uses_literal_substring_semantics(search_root):
    (search_root / "f.txt").write_text("a.b\naxb\n", encoding="utf-8")
    matches, truncated = _python_literal_search(root=search_root, target=search_root / "f.txt", pattern="a.b")
    assert truncated is False
    assert matches == ["f.txt:1:a.b"]


def test_fallback_no_matches_returns_empty_without_error(search_root):
    (search_root / "f.txt").write_text("nothing here\n", encoding="utf-8")
    matches, truncated = _python_literal_search(root=search_root, target=search_root / "f.txt", pattern="zzz")
    assert matches == []
    assert truncated is False


def test_fallback_caps_at_max_search_results_across_files(search_root):
    (search_root / "many").mkdir()
    for index in range(MAX_SEARCH_RESULTS + 25):
        (search_root / "many" / f"f{index:03d}.txt").write_text("needle\n", encoding="utf-8")
    matches, truncated = _python_literal_search(root=search_root, target=search_root / "many", pattern="needle")
    assert truncated is True
    assert len(matches) == MAX_SEARCH_RESULTS
    assert len(set(matches)) == MAX_SEARCH_RESULTS


def test_fallback_caps_at_max_search_results_within_one_file(search_root):
    (search_root / "big.txt").write_text("needle\n" * (MAX_SEARCH_RESULTS + 25), encoding="utf-8")
    matches, truncated = _python_literal_search(root=search_root, target=search_root / "big.txt", pattern="needle")
    assert truncated is True
    assert len(matches) == MAX_SEARCH_RESULTS


def test_fallback_skips_symlink_binary_nonutf8_oversized_ignored(search_root):
    (search_root / "dir").mkdir()
    (search_root / "dir" / "ok.txt").write_text("needle ok\n", encoding="utf-8")
    os.symlink(search_root / "dir" / "ok.txt", search_root / "dir" / "link.txt")
    (search_root / "dir" / "nul.bin").write_bytes(b"needle\x00binary\n")
    (search_root / "dir" / "latin1.txt").write_bytes("needle café\n".encode("latin-1"))
    (search_root / "dir" / "huge.txt").write_bytes(b"needle\n" * (MAX_SEARCH_FILE_BYTES // 6 + 10))
    (search_root / "dir" / "ignored.txt").write_text("needle ignored\n", encoding="utf-8")
    matches, truncated = _python_literal_search(root=search_root, target=search_root / "dir", pattern="needle")
    assert truncated is False
    assert matches == ["dir/ok.txt:1:needle ok"]


def test_fallback_result_order_is_deterministic(search_root):
    (search_root / "d").mkdir()
    for name in ("b.txt", "a.txt", "c.txt"):
        (search_root / "d" / name).write_text("needle\n", encoding="utf-8")
    first, _ = _python_literal_search(root=search_root, target=search_root / "d", pattern="needle")
    second, _ = _python_literal_search(root=search_root, target=search_root / "d", pattern="needle")
    assert first == ["d/a.txt:1:needle", "d/b.txt:1:needle", "d/c.txt:1:needle"]
    assert first == second


def test_fallback_output_is_relative_not_absolute(search_root):
    (search_root / "f.txt").write_text("needle\n", encoding="utf-8")
    matches, truncated = _python_literal_search(root=search_root, target=search_root / "f.txt", pattern="needle")
    assert truncated is False
    assert matches == ["f.txt:1:needle"]
    assert all(not line.startswith("/") for line in matches)


def test_bounded_rg_matches_caps_at_max_results():
    lines = [f"f.py:{index}:needle" for index in range(1, MAX_SEARCH_RESULTS + 25)]
    matches, truncated = _bounded_rg_matches(lines)
    assert len(matches) == MAX_SEARCH_RESULTS
    assert truncated is True


def test_rg_backend_enforces_global_result_limit_during_process_execution(tmp_path):
    fake = _write_fake_executable(
        "import sys\n"
        f"for i in range({MAX_SEARCH_RESULTS + 25}):\n"
        '    sys.stdout.write("f.py:" + str(i) + ":needle\\n")\n',
        tmp_path,
    )
    matches, truncated = _run_rg_literal_search(executable=fake, root=tmp_path, relative=".", pattern="needle")
    assert truncated is True
    assert len(matches) == MAX_SEARCH_RESULTS


def test_rg_backend_enforces_global_output_byte_limit(tmp_path):
    fake = _write_fake_executable(
        "import sys\n"
        "line = 'n' * 6000\n"
        "for i in range(300):\n"
        '    sys.stdout.write("f.py:" + str(i) + ":" + line + "\\n")\n',
        tmp_path,
    )
    matches, truncated = _run_rg_literal_search(executable=fake, root=tmp_path, relative=".", pattern="n")
    assert truncated is True
    assert 0 < len(matches) < MAX_SEARCH_RESULTS


def test_rg_backend_enforces_deadline_and_reaps_process(tmp_path):
    pidfile = tmp_path / "child-pid"
    fake = _write_fake_executable(
        "import os, time\n"
        + "open(%r, 'w').write(str(os.getpid()))\n" % str(pidfile)
        + "time.sleep(60)\n",
        tmp_path,
    )
    matches, truncated = _run_rg_literal_search(executable=fake, root=tmp_path, relative=".", pattern="x")
    assert truncated is True
    assert matches == []
    pid = int(pidfile.read_text())
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        pytest.fail("search left a live child process behind")


def test_rg_backend_long_line_sets_truncated(tmp_path):
    fake = _write_fake_executable(
        f'import sys\nsys.stdout.write("f.py:1:" + "x" * ({MAX_SEARCH_LINE_BYTES + 100}) + "\\n")\n',
        tmp_path,
    )
    matches, truncated = _run_rg_literal_search(executable=fake, root=tmp_path, relative=".", pattern="x")
    assert truncated is True
    assert len(matches) == 1
    assert len(matches[0].encode("utf-8")) <= MAX_SEARCH_LINE_BYTES


def test_rg_backend_nonzero_error_is_not_masked(tmp_path):
    fake = _write_fake_executable("import sys\nsys.stderr.write('boom')\nsys.exit(2)\n", tmp_path)
    with pytest.raises(RuntimeError, match="boom"):
        _run_rg_literal_search(executable=fake, root=tmp_path, relative=".", pattern="x")


def test_direct_symlink_file_target_is_rejected(monkeypatch, search_root):
    (search_root / "real.txt").write_text("needle\n", encoding="utf-8")
    os.symlink(search_root / "real.txt", search_root / "link.txt")
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", search_root.resolve())
    with pytest.raises(GatewayInputError, match="search path cannot traverse symlinks"):
        _gateway()._search({"pattern": "needle", "path": "link.txt"})


def test_intermediate_symlink_directory_is_rejected(monkeypatch, search_root):
    (search_root / "real_dir").mkdir()
    (search_root / "real_dir" / "target.txt").write_text("needle\n", encoding="utf-8")
    os.symlink(search_root / "real_dir", search_root / "link_dir")
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", search_root.resolve())
    with pytest.raises(GatewayInputError, match="search path cannot traverse symlinks"):
        _gateway()._search({"pattern": "needle", "path": "link_dir/target.txt"})


def test_regular_direct_file_still_searches(monkeypatch, search_root):
    (search_root / "plain.txt").write_text("needle here\n", encoding="utf-8")
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", search_root.resolve())
    monkeypatch.setattr(gateway_module.shutil, "which", lambda name: None)
    payload = _gateway()._search({"pattern": "needle", "path": "plain.txt"})
    assert payload["backend"] == "python"
    assert payload["matches"] == ["plain.txt:1:needle here"]
    assert payload["truncated"] is False


def test_git_ls_files_nul_parsing_preserves_newline_filename(search_root):
    (search_root / "dir").mkdir()
    (search_root / "dir" / "weird\nname.txt").write_text("needle\n", encoding="utf-8")
    (search_root / "dir" / "plain.txt").write_text("needle\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=search_root, check=True)
    paths = _git_ls_files(root=search_root, relative="dir")
    assert "dir/weird\nname.txt" in paths
    assert "dir/plain.txt" in paths


def test_git_ls_files_nul_parsing_preserves_leading_and_trailing_spaces(search_root):
    (search_root / "dir").mkdir()
    (search_root / "dir" / "  spaced.txt  ").write_text("needle\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=search_root, check=True)
    paths = _git_ls_files(root=search_root, relative="dir")
    assert "dir/  spaced.txt  " in paths


def test_git_ls_files_non_utf8_filename_does_not_crash_search(monkeypatch, search_root):
    class _FakeResult:
        returncode = 0
        stdout = b"dir/caf\xe9.txt\x00dir/plain.txt\x00"
        stderr = b""

    monkeypatch.setattr(gateway_module.subprocess, "run", lambda *args, **kwargs: _FakeResult())
    paths = _git_ls_files(root=search_root, relative="dir")
    assert "dir/caf\udce9.txt" in paths
    assert "dir/plain.txt" in paths


def test_python_long_matching_line_sets_truncated_true(search_root):
    (search_root / "long.txt").write_text(
        "needle " + "x" * (MAX_SEARCH_LINE_BYTES + 100) + "\n", encoding="utf-8"
    )
    matches, truncated = _python_literal_search(root=search_root, target=search_root / "long.txt", pattern="needle")
    assert truncated is True
    assert len(matches) == 1
    assert len(matches[0].encode("utf-8")) <= MAX_SEARCH_LINE_BYTES


def test_rg_long_matching_line_sets_truncated_true(tmp_path):
    fake = _write_fake_executable(
        f'import sys\nsys.stdout.write("f.py:1:" + "x" * ({MAX_SEARCH_LINE_BYTES + 100}) + "\\n")\n',
        tmp_path,
    )
    matches, truncated = _run_rg_literal_search(executable=fake, root=tmp_path, relative=".", pattern="x")
    assert truncated is True
    assert len(matches) == 1
    assert len(matches[0].encode("utf-8")) <= MAX_SEARCH_LINE_BYTES


def _write_non_utf8_file(root: Path, name_bytes: bytes, content: bytes) -> bool:
    """Create a file whose name bytes are not valid UTF-8.  Returns False when
    the host filesystem rejects such a name so the test can skip."""
    raw_path = os.fsencode(root.resolve()) + b"/" + name_bytes
    try:
        fd = os.open(raw_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    except OSError:
        return False
    try:
        os.write(fd, content)
    except OSError:
        return False
    finally:
        os.close(fd)
    return True


def _non_utf8_search_payload(monkeypatch, search_root):
    (search_root / "dir").mkdir(exist_ok=True)
    if not _write_non_utf8_file(search_root / "dir", b"caf\xe9.txt", b"needle here\n"):
        pytest.skip("filesystem rejects non-UTF-8 filename")
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", search_root.resolve())
    monkeypatch.setattr(gateway_module.shutil, "which", lambda name: None)
    payload = _gateway()._search({"pattern": "needle", "path": "dir"})
    assert payload["backend"] == "python"
    assert payload["matches"]
    return payload


def _has_surrogate(value: str) -> bool:
    return any(0xD800 <= ord(ch) <= 0xDFFF for ch in value)


def test_non_utf8_filename_full_search_does_not_crash(monkeypatch, search_root):
    payload = _non_utf8_search_payload(monkeypatch, search_root)
    assert not any(_has_surrogate(line) for line in payload["matches"])


def test_non_utf8_filename_response_is_utf8_serializable(monkeypatch, search_root):
    payload = _non_utf8_search_payload(monkeypatch, search_root)
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    assert isinstance(encoded, bytes)
    for line in payload["matches"]:
        value = line.encode("utf-8")
        assert isinstance(value, bytes)


def test_non_utf8_filename_match_uses_deterministic_escape(monkeypatch, search_root):
    payload = _non_utf8_search_payload(monkeypatch, search_root)
    assert payload["matches"][0].startswith("dir/caf\\xe9.txt:")
    first, _ = _python_literal_search(root=search_root.resolve(), target=search_root / "dir", pattern="needle")
    assert first == payload["matches"]


def test_large_stderr_rg_error_is_not_masked(tmp_path):
    fake = _write_fake_executable(
        "import sys\n"
        "sys.stderr.write('RG_FATAL_MARKER\\n')\n"
        f"sys.stderr.write('x' * {gateway_module.MAX_SEARCH_STDERR_BYTES})\n"
        "sys.exit(2)\n",
        tmp_path,
    )
    with pytest.raises(RuntimeError, match="RG_FATAL_MARKER"):
        _run_rg_literal_search(executable=fake, root=tmp_path, relative=".", pattern="x")


def test_stdout_eof_does_not_prevent_stderr_drain(tmp_path):
    fake = _write_fake_executable(
        "import os, sys\n"
        "sys.stdout.write('f.py:1:needle\\n')\n"
        "os.close(1)\n"
        "sys.stderr.write('DRAIN_MARKER ' + 'y' * (200 * 1024))\n"
        "sys.exit(2)\n",
        tmp_path,
    )
    with pytest.raises(RuntimeError, match="DRAIN_MARKER"):
        _run_rg_literal_search(executable=fake, root=tmp_path, relative=".", pattern="needle")


def test_stderr_is_bounded_but_fully_drained(tmp_path):
    fake = _write_fake_executable(
        "import sys\n"
        "sys.stderr.write('BOUND_MARKER\\n')\n"
        "sys.stderr.write('z' * %d)\n"
        "sys.exit(2)\n"
        % (gateway_module.MAX_SEARCH_STDERR_BYTES),
        tmp_path,
    )
    with pytest.raises(RuntimeError, match="BOUND_MARKER") as excinfo:
        _run_rg_literal_search(executable=fake, root=tmp_path, relative=".", pattern="x")
    assert "[stderr truncated]" in str(excinfo.value)


def test_line_truncation_does_not_mask_nonzero_rg_exit(tmp_path):
    fake = _write_fake_executable(
        "import sys\n"
        f"sys.stdout.write('f.py:1:' + 'q' * {MAX_SEARCH_LINE_BYTES + 200} + '\\n')\n"
        "sys.stderr.write('real rg failure\\n')\n"
        "sys.exit(2)\n",
        tmp_path,
    )
    with pytest.raises(RuntimeError, match="real rg failure"):
        _run_rg_literal_search(executable=fake, root=tmp_path, relative=".", pattern="q")


def test_forced_limit_termination_allows_expected_signal_exit(tmp_path):
    fake = _write_fake_executable(
        "import sys, time\n"
        f"for i in range({MAX_SEARCH_RESULTS + 5}):\n"
        '    sys.stdout.write("f.py:" + str(i) + ":needle\\n")\n'
        "sys.stdout.flush()\n"
        "time.sleep(60)\n",
        tmp_path,
    )
    matches, truncated = _run_rg_literal_search(executable=fake, root=tmp_path, relative=".", pattern="needle")
    assert truncated is True
    assert len(matches) == MAX_SEARCH_RESULTS


def test_forced_limit_process_is_reaped_after_signal(tmp_path):
    # Proves the force path reaps the child (only SIGTERM/SIGKILL return codes
    # are accepted, and no child is left alive after a forced result limit).
    pidfile = tmp_path / "child-pid"
    fake = _write_fake_executable(
        "import os, sys, time\n"
        + "open(%r, 'w').write(str(os.getpid()))\n" % str(pidfile)
        + f"for i in range({MAX_SEARCH_RESULTS + 5}):\n"
        + "    sys.stdout.write(\"f.py:\" + str(i) + \":needle\\n\")\n"
        + "sys.stdout.flush()\n"
        + "time.sleep(60)\n",
        tmp_path,
    )
    matches, truncated = _run_rg_literal_search(executable=fake, root=tmp_path, relative=".", pattern="needle")
    assert truncated is True
    assert len(matches) == MAX_SEARCH_RESULTS
    pid = int(pidfile.read_text())
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    else:
        pytest.fail("forced result-limit search left a live child process behind")


def test_display_search_path_handles_surrogate_without_filesystem_support(tmp_path):
    root = tmp_path
    path = root / "dir" / "caf\udce9.txt"

    displayed = _display_search_path(path, root=root)

    assert displayed == r"dir/caf\xe9.txt"
    assert not any(0xD800 <= ord(ch) <= 0xDFFF for ch in displayed)
    assert displayed.encode("utf-8")
    assert json.dumps(
        {"match": displayed},
        ensure_ascii=False,
    ).encode("utf-8")


def test_both_pipes_eof_before_clean_exit_is_not_terminated(tmp_path):
    fake = _write_fake_executable(
        "import os, sys, time\n"
        "sys.stdout.write('f.py:1:needle\\n')\n"
        "sys.stdout.flush()\n"
        "os.close(1)\n"
        "os.close(2)\n"
        "time.sleep(0.2)\n"
        "sys.exit(0)\n",
        tmp_path,
    )
    matches, truncated = _run_rg_literal_search(executable=fake, root=tmp_path, relative=".", pattern="needle")
    assert matches == ["f.py:1:needle"]
    assert truncated is False


def test_both_pipes_eof_before_no_match_exit_is_not_terminated(tmp_path):
    fake = _write_fake_executable(
        "import os, sys, time\n"
        "sys.stdout.flush()\n"
        "sys.stderr.flush()\n"
        "os.close(1)\n"
        "os.close(2)\n"
        "time.sleep(0.2)\n"
        "sys.exit(1)\n",
        tmp_path,
    )
    matches, truncated = _run_rg_literal_search(executable=fake, root=tmp_path, relative=".", pattern="needle")
    assert matches == []
    assert truncated is False


def test_both_pipes_eof_before_error_exit_reports_error(tmp_path):
    fake = _write_fake_executable(
        "import os, sys, time\n"
        "sys.stderr.write('DELAYED_ERROR\\n')\n"
        "sys.stderr.flush()\n"
        "sys.stdout.flush()\n"
        "os.close(1)\n"
        "os.close(2)\n"
        "time.sleep(0.2)\n"
        "sys.exit(2)\n",
        tmp_path,
    )
    with pytest.raises(RuntimeError, match="DELAYED_ERROR"):
        _run_rg_literal_search(executable=fake, root=tmp_path, relative=".", pattern="needle")


def test_unforced_signal_exit_is_an_error(tmp_path):
    fake = _write_fake_executable(
        "import os, signal\n"
        "os.kill(os.getpid(), signal.SIGTERM)\n",
        tmp_path,
    )
    with pytest.raises(RuntimeError):
        _run_rg_literal_search(executable=fake, root=tmp_path, relative=".", pattern="needle")


def test_natural_exit_never_calls_terminate_or_kill(monkeypatch, tmp_path):
    calls = []
    real_helper = gateway_module._terminate_and_reap_search_process

    def recording_helper(process):
        calls.append(process)
        return real_helper(process)

    monkeypatch.setattr(gateway_module, "_terminate_and_reap_search_process", recording_helper)
    fake = _write_fake_executable(
        "import os, sys, time\n"
        "sys.stdout.write('f.py:1:needle\\n')\n"
        "sys.stdout.flush()\n"
        "os.close(1)\n"
        "os.close(2)\n"
        "time.sleep(0.2)\n"
        "sys.exit(0)\n",
        tmp_path,
    )
    matches, truncated = _run_rg_literal_search(executable=fake, root=tmp_path, relative=".", pattern="needle")
    assert matches == ["f.py:1:needle"]
    assert truncated is False
    assert calls == []



class _ReapFailureProcess:
    """A fake Popen that never leaves the running state so cleanup must fail."""

    class _Stream:
        def __init__(self, fd):
            self._fd = fd

        def fileno(self):
            return self._fd

        def read(self):
            return b""

        def close(self):
            os.close(self._fd)

    def __init__(self):
        self.stdout_r, _ = os.pipe()
        self.stderr_r, _ = os.pipe()
        self.stdout = self._Stream(self.stdout_r)
        self.stderr = self._Stream(self.stderr_r)
        self.returncode = None
        self.terminate_called = False
        self.kill_called = False
        self.wait_calls = 0

    def poll(self):
        return None

    def terminate(self):
        self.terminate_called = True

    def kill(self):
        self.kill_called = True

    def wait(self, timeout=None):
        self.wait_calls += 1
        raise subprocess.TimeoutExpired("fake-search-process", timeout=None)


def test_rg_process_reap_failure_fails_closed(monkeypatch, tmp_path):
    proc = _ReapFailureProcess()
    monkeypatch.setattr(gateway_module.subprocess, "Popen", lambda *args, **kwargs: proc)
    with pytest.raises(RuntimeError, match="search process cleanup failed"):
        _run_rg_literal_search(executable="/nonexistent/rg", root=tmp_path, relative=".", pattern="x")
    assert proc.terminate_called is True
    assert proc.kill_called is True
    assert proc.wait_calls >= 2


class _TailReadForbiddenFailureProcess:
    """A fake child that never exits while its streams forbid blocking reads.

    ``wait`` always times out so the cleanup ladder must escalate to sigkill and
    then fail closed; ``terminate``/``kill`` are recorded; ``.read()`` must
    never be reached and so raises immediately.
    """

    class _Stream:
        def __init__(self, fd):
            self._fd = fd
            self.closed = False

        def fileno(self):
            return self._fd

        def close(self):
            self.closed = True
            try:
                os.close(self._fd)
            except OSError:
                pass

        def read(self):
            raise AssertionError("blocking read must not be called")

    def __init__(self):
        self.stdout_r, _ = os.pipe()
        self.stderr_r, _ = os.pipe()
        self.stdout = self._Stream(self.stdout_r)
        self.stderr = self._Stream(self.stderr_r)
        self.returncode = None
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls = 0

    def poll(self):
        return None

    def terminate(self):
        self.terminate_calls += 1

    def kill(self):
        self.kill_calls += 1

    def wait(self, timeout=None):
        self.wait_calls += 1
        raise subprocess.TimeoutExpired("fake-search-process", timeout=timeout)


def test_cleanup_failure_does_not_perform_blocking_tail_read(monkeypatch, tmp_path):
    proc = _TailReadForbiddenFailureProcess()
    monkeypatch.setattr(gateway_module.subprocess, "Popen", lambda *args, **kwargs: proc)
    with pytest.raises(RuntimeError, match="search process cleanup failed"):
        _run_rg_literal_search(executable="/nonexistent/rg", root=tmp_path, relative=".", pattern="x")
    assert proc.terminate_calls == 1
    assert proc.kill_calls == 1
    assert proc.wait_calls >= 2
    assert proc.stdout.closed is True
    assert proc.stderr.closed is True
