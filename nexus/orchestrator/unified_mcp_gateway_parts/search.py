"""Workspace search helpers of the unified MCP gateway (G1 split, Issue #2437).

Moved from ``nexus/orchestrator/unified_mcp_gateway.py`` with AST-identical bodies (only
``ruff format`` layout changed); the gateway re-exports every name, so
``unified_mcp_gateway.X`` keeps resolving.
"""

from __future__ import annotations

import os
import select
import signal
import subprocess
import time
from pathlib import Path

MAX_RESULT_BYTES = 1024 * 1024
MAX_SEARCH_RESULTS = 200
MAX_SEARCH_FILE_BYTES = 1024 * 1024
MAX_SEARCH_TOTAL_BYTES = 64 * 1024 * 1024
MAX_SEARCH_FILES = 10000
MAX_SEARCH_SECONDS = 3
MAX_SEARCH_LINE_BYTES = 4096
MAX_SEARCH_STDERR_BYTES = 64 * 1024


def _bounded_text(value: str, field: str) -> str:
    if len(value.encode("utf-8")) > MAX_RESULT_BYTES:
        raise RuntimeError(f"{field} exceeds {MAX_RESULT_BYTES} bytes")
    return value


def _bounded_match_line(line: str) -> tuple[str, bool]:
    """Deterministically cap one search match line so a single oversized line
    cannot blow through the response byte budget.

    Returns ``(bounded_line, truncated)`` where ``truncated`` is true when the
    line was trimmed to ``MAX_SEARCH_LINE_BYTES`` and must surface as a global
    truncation flag.
    """
    encoded = line.encode("utf-8")
    if len(encoded) <= MAX_SEARCH_LINE_BYTES:
        return line, False
    return encoded[:MAX_SEARCH_LINE_BYTES].decode("utf-8", errors="ignore"), True


def _git_ls_files(*, root: Path, relative: str) -> list[str]:
    """List Git-tracked and non-ignored untracked files under one relative path.

    Parsing is NUL-safe: the ``-z`` flag emits each path name verbatim (newlines
    and surrounding whitespace preserved) and non-UTF-8 names survive via
    ``os.fsdecode`` surrogateescape.
    """
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "--deduplicate",
            "-z",
            "--",
            relative,
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=MAX_SEARCH_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.decode("utf-8", errors="replace").strip() or "git ls-files failed"
        )
    paths: list[str] = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        paths.append(os.fsdecode(raw))
    return paths


def _search_candidate_files(*, root: Path, target: Path) -> list[Path]:
    """Return the ordered candidate files for a literal search target.

    A single regular file scans only that file.  A directory resolves to the
    Git-tracked and non-ignored untracked file list so the search never runs an
    unbounded whole-filesystem recursion.
    """
    root_resolved = root.resolve()
    target_resolved = target.resolve()
    try:
        target_resolved.relative_to(root_resolved)
    except ValueError:
        return []
    if not target_resolved.is_symlink() and target_resolved.is_file():
        return [target_resolved]
    try:
        relative = str(target_resolved.relative_to(root_resolved)) or "."
    except ValueError:
        return []
    candidates: list[Path] = []
    for raw in _git_ls_files(root=root_resolved, relative=relative):
        raw_path = root_resolved / raw
        if raw_path.is_symlink():
            continue
        resolved = raw_path.resolve()
        try:
            resolved.relative_to(root_resolved)
        except ValueError:
            continue
        candidates.append(resolved)
    candidates.sort(key=lambda path: path.relative_to(root_resolved).as_posix())
    return candidates


def _searchable_file(*, root: Path, candidate: Path) -> bool:
    """Re-validate one candidate file before reading it."""
    if candidate.is_symlink():
        return False
    if ".git" in candidate.parts:
        return False
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    if not candidate.is_file():
        return False
    try:
        if candidate.stat().st_size > MAX_SEARCH_FILE_BYTES:
            return False
    except OSError:
        return False
    return True


def _display_search_path(path: Path, *, root: Path) -> str:
    """Render a canonical-relative path safely when its name bytes are not UTF-8.

    Non-UTF-8 filename bytes are escaped deterministically (e.g. ``caf\xe9.txt``)
    so the displayed path never contains surrogate code points, survives UTF-8
    re-encoding, and stays JSON-serializable.
    """
    relative = path.relative_to(root)
    raw = os.fsencode(relative)
    return raw.decode("utf-8", errors="backslashreplace")


def _literal_matches_in_file(
    *, root: Path, candidate: Path, pattern: str
) -> tuple[list[str], bool]:
    """Literal substring match over one UTF-8 file, skipping unreadable or
    binary content.  Output lines use ``relative/path.py:line:content`` and
    ``truncated`` is true when any matching line was capped."""
    try:
        raw = candidate.read_bytes()
    except OSError:
        return [], False
    if b"\x00" in raw:
        return [], False
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return [], False
    relative = _display_search_path(candidate, root=root)
    found: list[str] = []
    truncated = False
    for lineno, line in enumerate(text.split("\n"), start=1):
        if pattern not in line:
            continue
        if line.endswith("\r"):
            line = line[:-1]
        bounded, line_truncated = _bounded_match_line(f"{relative}:{lineno}:{line}")
        truncated = truncated or line_truncated
        found.append(bounded)
    return found, truncated


def _python_literal_search(
    *,
    root: Path,
    target: Path,
    pattern: str,
) -> tuple[list[str], bool]:
    """Standard-library literal search fallback used when ripgrep is absent.

    Enforces the named search resource limits and returns ``(matches, truncated)``
    where the match lines are always canonical-root-relative.
    """
    root_resolved = root.resolve()
    candidates = _search_candidate_files(root=root_resolved, target=target)
    deadline = time.monotonic() + MAX_SEARCH_SECONDS
    matches: list[str] = []
    output_bytes = 0
    scanned = 0
    total_bytes = 0
    truncated = False
    for candidate in candidates:
        if len(matches) >= MAX_SEARCH_RESULTS:
            truncated = True
            break
        if scanned >= MAX_SEARCH_FILES:
            truncated = True
            break
        if time.monotonic() >= deadline:
            truncated = True
            break
        scanned += 1
        if not _searchable_file(root=root_resolved, candidate=candidate):
            continue
        try:
            size = candidate.stat().st_size
        except OSError:
            continue
        if total_bytes + size > MAX_SEARCH_TOTAL_BYTES:
            truncated = True
            break
        total_bytes += size
        file_matches, file_truncated = _literal_matches_in_file(
            root=root_resolved, candidate=candidate, pattern=pattern
        )
        truncated = truncated or file_truncated
        for matched in file_matches:
            if len(matches) >= MAX_SEARCH_RESULTS:
                truncated = True
                break
            matched_bytes = len(matched.encode("utf-8"))
            if output_bytes + matched_bytes > MAX_RESULT_BYTES:
                truncated = True
                break
            matches.append(matched)
            output_bytes += matched_bytes
        if truncated:
            break
    return matches, truncated


def _bounded_rg_matches(lines: list[str]) -> tuple[list[str], bool]:
    """Apply the same result and byte caps to ripgrep output lines."""
    matches: list[str] = []
    truncated = bool(len(lines) > MAX_SEARCH_RESULTS)
    output_bytes = 0
    for line in lines:
        if len(matches) >= MAX_SEARCH_RESULTS:
            truncated = True
            break
        bounded, line_truncated = _bounded_match_line(line)
        truncated = truncated or line_truncated
        matched_bytes = len(bounded.encode("utf-8"))
        if output_bytes + matched_bytes > MAX_RESULT_BYTES:
            truncated = True
            break
        matches.append(bounded)
        output_bytes += matched_bytes
    return matches, truncated


def _terminate_and_reap_search_process(process: subprocess.Popen) -> str:
    """Force a search child to exit and reap it, failing closed on refusal.

    Returns one of ``already_exited``, ``sigterm``, or ``sigkill`` describing
    the action actually taken so the caller only accepts a return code when it
    matches the signal this helper really sent.  terminate -> wait(0.5) ->
    kill -> wait(1.0) bounds the total wait; if the process still refuses to
    die the second wait timeout raises so a leaked child can never pass as a
    successful cleanup.

    If the child exits between ``poll`` and ``terminate``/``kill``
    (``ProcessLookupError``) it is reaped with a bounded ``wait`` and reported
    as ``already_exited`` rather than falsely claiming a signal was sent.
    """
    if process.poll() is not None:
        process.wait()
        return "already_exited"
    try:
        process.terminate()
    except ProcessLookupError:
        process.wait()
        return "already_exited"
    try:
        process.wait(timeout=0.5)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except ProcessLookupError:
            process.wait()
            return "already_exited"
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            raise RuntimeError("search process cleanup failed") from None
        return "sigkill"
    return "sigterm"


def _run_rg_literal_search(
    *,
    executable: str,
    root: Path,
    relative: str,
    pattern: str,
) -> tuple[list[str], bool]:
    """Run one literal ripgrep search under hard process-level resource limits.

    Reads stdout and stderr in bounded binary chunks (never ``communicate()``
    or a whole ``stdout.read()``) with ``select``-bounded reads so
    ``MAX_SEARCH_SECONDS`` is enforced while the process runs, and counts raw
    streamed bytes so ``MAX_RESULT_BYTES`` caps the process output itself.  The
    stderr pipe is drained simultaneously (never left to backpressure) and
    retained only up to ``MAX_SEARCH_STDERR_BYTES`` for error reporting.

    The process is never force-terminated just because its pipes reached EOF:
    a normally exiting child that outlives its last output gets a bounded
    natural ``wait`` for its own exit.  Only a result limit, an output-byte
    limit, or the deadline may force termination, and the caller only accepts
    a forced exit whose return code matches the signal the helper actually
    sent.  A returning ``_terminate_and_reap_search_process`` of
    ``already_exited`` is classified by the natural return-code rules instead.
    A genuine ripgrep failure (exit code outside the normal 0=matches /
    1=no-matches contract, an unforced signal exit, or a cleanup failure)
    raises ``RuntimeError`` and is never masked by the Python fallback or by a
    truncated-read state.
    """
    process = subprocess.Popen(
        [
            executable,
            "-n",
            "--fixed-strings",
            "--no-heading",
            "--color",
            "never",
            "--with-filename",
            "--max-count",
            str(MAX_SEARCH_RESULTS),
            "--",
            pattern,
            relative,
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    stdout_fd = process.stdout.fileno()  # pyright: ignore[reportOptionalMemberAccess]
    stderr_fd = process.stderr.fileno()  # pyright: ignore[reportOptionalMemberAccess]
    deadline = time.monotonic() + MAX_SEARCH_SECONDS
    matches: list[str] = []
    raw_output_bytes = 0
    truncated = False
    rejected_match_line = False
    line_buffer = bytearray()
    stderr_bytes = bytearray()
    stderr_overflow = False
    forced_termination = False
    termination_reason: str | None = None
    termination_method: str | None = None
    stdout_open = True
    stderr_open = True
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                returncode = process.poll()
                if returncode is not None:
                    process.wait()
                    break
                truncated = True
                forced_termination = True
                termination_reason = "deadline"
                break
            if len(matches) >= MAX_SEARCH_RESULTS:
                truncated = True
                forced_termination = True
                termination_reason = "result_limit"
                break
            if raw_output_bytes > MAX_RESULT_BYTES:
                truncated = True
                forced_termination = True
                termination_reason = "output_byte_limit"
                break
            active_fds: list[int] = []
            if stdout_open:
                active_fds.append(stdout_fd)
            if stderr_open:
                active_fds.append(stderr_fd)
            if not active_fds:
                natural_remaining = max(0.0, deadline - time.monotonic())
                try:
                    process.wait(timeout=natural_remaining)
                except subprocess.TimeoutExpired:
                    truncated = True
                    forced_termination = True
                    termination_reason = "deadline"
                break
            readable, _, _ = select.select(active_fds, [], [], min(remaining, 0.1))
            if not readable:
                continue
            for fd in readable:
                if fd == stdout_fd:
                    try:
                        chunk = os.read(stdout_fd, 64 * 1024)
                    except OSError:
                        chunk = b""
                    if not chunk:
                        stdout_open = False
                        continue
                    raw_output_bytes += len(chunk)
                    if raw_output_bytes > MAX_RESULT_BYTES:
                        truncated = True
                        forced_termination = True
                        termination_reason = "output_byte_limit"
                        break
                    line_buffer.extend(chunk)
                    while b"\n" in line_buffer:
                        raw_line, _, rest = line_buffer.partition(b"\n")
                        line_buffer = bytearray(rest)
                        if rejected_match_line:
                            continue
                        if len(matches) >= MAX_SEARCH_RESULTS:
                            truncated = True
                            rejected_match_line = True
                            continue
                        bounded, line_truncated = _bounded_match_line(
                            raw_line.decode("utf-8", errors="replace")
                        )
                        truncated = truncated or line_truncated
                        matches.append(bounded)
                else:
                    try:
                        chunk = os.read(stderr_fd, 64 * 1024)
                    except OSError:
                        chunk = b""
                    if not chunk:
                        stderr_open = False
                        continue
                    room = MAX_SEARCH_STDERR_BYTES - len(stderr_bytes)
                    if room > 0:
                        stderr_bytes.extend(chunk[:room])
                    if len(chunk) > room:
                        stderr_overflow = True
            if termination_reason is not None:
                break
        if line_buffer and not truncated:
            bounded, line_truncated = _bounded_match_line(
                bytes(line_buffer).decode("utf-8", errors="replace")
            )
            truncated = truncated or line_truncated
            if len(matches) >= MAX_SEARCH_RESULTS:
                truncated = True
            else:
                matches.append(bounded)
        if forced_termination:
            termination_method = _terminate_and_reap_search_process(process)
        else:
            assert process.returncode is not None
    finally:
        for cleanup_stream in (process.stdout, process.stderr):
            try:
                cleanup_stream.close()  # pyright: ignore[reportOptionalMemberAccess]
            except Exception:
                pass

    stderr_text = stderr_bytes.decode("utf-8", errors="replace")
    if stderr_overflow:
        stderr_text += "[stderr truncated]"
    stderr_text = stderr_text.strip()

    returncode = process.returncode
    if forced_termination:
        if termination_method == "already_exited":
            if returncode not in (0, 1):
                raise RuntimeError(stderr_text or f"search failed (exit {returncode})")
        elif termination_method == "sigterm":
            if returncode != -signal.SIGTERM:
                raise RuntimeError(stderr_text or "search process exited unexpectedly")
        elif termination_method == "sigkill":
            if returncode != -signal.SIGKILL:
                raise RuntimeError(stderr_text or "search process exited unexpectedly")
        else:  # pragma: no cover - defensive; helper only returns documented values
            raise RuntimeError("search process cleanup failed")
    elif returncode not in (0, 1):
        raise RuntimeError(stderr_text or f"search failed (exit {returncode})")
    return matches, truncated
