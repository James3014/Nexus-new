"""Run legacy command strings without a shell (#2635 SEC-007).

Several legacy paths accepted a command *string* from repo files, plans or
model output and ran it with ``shell=True``. That lets any ``;``, ``|``,
``$(...)`` or redirect inside the string execute. This helper keeps the
string interface but never invokes a shell:

* the string is tokenized with POSIX quoting rules (single quotes, double
  quotes, backslash); newline, CR and NUL are refused;
* ``a && b`` chains are supported: segments run in order and the chain stops
  at the first non-zero exit, as a shell would;
* leading ``NAME=value`` words are passed as environment variables;
* every other unquoted shell operator (``;``, ``|``, ``||``, ``>``, ``<``,
  ``&``, parentheses) and an unquoted ``#`` comment are refused fail-closed
  with exit code 2 and nothing runs; a quoted ``'&&'`` stays a literal;
* no variable, glob, tilde or command substitution happens: ``$HOME`` or
  ``*.py`` reach the program literally.
"""

from __future__ import annotations

import ctypes
import errno
import os
import re
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Mapping, Sequence

UNSUPPORTED_SYNTAX_EXIT = 2
COMMAND_NOT_FOUND_EXIT = 127

_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_OPERATOR_CHARS = frozenset("();<>|&")


class UnsupportedShellSyntax(ValueError):
    """The command string needs a shell feature this runner refuses."""


_FORBIDDEN_CHARS = {"\n": "newline", "\r": "carriage return", "\x00": "NUL"}
_DOUBLE_QUOTE_ESCAPABLE = frozenset('"\\$`')


def _tokenize(command: str) -> list[tuple[str, bool, bool]]:
    """Split *command* POSIX-style into ``(text, is_operator, assignment)``.

    Quoted or escaped operators and ``#`` stay literal word characters.
    ``assignment`` is True when the word starts with an unquoted ``NAME=``,
    the only form a shell treats as an environment assignment.
    """
    for char, name in _FORBIDDEN_CHARS.items():
        if char in command:
            raise UnsupportedShellSyntax(f"{name} in command string is not supported")
    tokens: list[tuple[str, bool, bool]] = []
    word: list[str] = []
    in_word = False
    bare_prefix: list[str] = []  # leading unquoted characters of the word
    prefix_open = True
    i = 0
    n = len(command)

    def flush() -> None:
        nonlocal word, in_word, bare_prefix, prefix_open
        if in_word:
            assignment = bool(_ASSIGNMENT.match("".join(bare_prefix)))
            tokens.append(("".join(word), False, assignment))
        word, in_word, bare_prefix, prefix_open = [], False, [], True

    while i < n:
        char = command[i]
        if char in " \t":
            flush()
            i += 1
        elif char == "'":
            end = command.find("'", i + 1)
            if end < 0:
                raise UnsupportedShellSyntax("unparseable command: unbalanced single quote")
            word.append(command[i + 1 : end])
            in_word, prefix_open = True, False
            i = end + 1
        elif char == '"':
            i += 1
            while True:
                if i >= n:
                    raise UnsupportedShellSyntax("unparseable command: unbalanced double quote")
                c = command[i]
                if c == '"':
                    i += 1
                    break
                if c == "\\" and i + 1 < n and command[i + 1] in _DOUBLE_QUOTE_ESCAPABLE:
                    word.append(command[i + 1])
                    i += 2
                    continue
                word.append(c)
                i += 1
            in_word, prefix_open = True, False
        elif char == "\\":
            if i + 1 >= n:
                raise UnsupportedShellSyntax("unparseable command: trailing backslash")
            word.append(command[i + 1])
            in_word, prefix_open = True, False
            i += 2
        elif char in _OPERATOR_CHARS:
            flush()
            j = i
            while j < n and command[j] in _OPERATOR_CHARS:
                j += 1
            tokens.append((command[i:j], True, False))
            i = j
        elif char == "#" and not in_word:
            # A shell would treat the rest as a comment; silently dropping it
            # could hide part of a verification command, so refuse instead.
            raise UnsupportedShellSyntax("unquoted '#' (shell comment) is not supported")
        else:
            word.append(char)
            if prefix_open:
                bare_prefix.append(char)
            in_word = True
            i += 1
    flush()
    return tokens


def _split_chain(command: str) -> list[list[tuple[str, bool]]]:
    segments: list[list[tuple[str, bool]]] = [[]]
    for text, is_operator, assignment in _tokenize(str(command)):
        if is_operator:
            if text != "&&":
                raise UnsupportedShellSyntax(f"shell operator {text!r} is not supported")
            segments.append([])
            continue
        segments[-1].append((text, assignment))
    if any(not segment for segment in segments):
        raise UnsupportedShellSyntax("empty command segment")
    return segments


def split_command_chain(command: str) -> list[list[str]]:
    """Return the ``&&``-separated segments of *command* as argv lists.

    Only an unquoted ``&&`` separates segments. Raises
    :class:`UnsupportedShellSyntax` for any other unquoted shell operator, an
    unquoted ``#`` starting a word, a newline/CR/NUL anywhere, an empty
    segment, or unbalanced quotes.
    """
    return [[text for text, _assignment in segment] for segment in _split_chain(command)]


def _split_assignments(
    words: Sequence[tuple[str, bool]],
) -> tuple[dict[str, str], list[str]]:
    env: dict[str, str] = {}
    index = 0
    # Only an unquoted leading NAME= is an assignment, as in a shell.
    while index < len(words) and words[index][1]:
        name, _, value = words[index][0].partition("=")
        env[name] = value
        index += 1
    return env, [text for text, _assignment in words[index:]]


def _only_exited_leader_left(pgid: int) -> bool:
    """macOS: whether group *pgid* holds nothing but its leader, exited and unreaped.

    Read through libproc, one call; anything it cannot tell is left to ``ps``."""
    if sys.platform != "darwin":
        return False
    try:
        libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        buffer = (ctypes.c_int * 1024)()
        filled = libproc.proc_listpids(2, pgid, buffer, ctypes.sizeof(buffer))  # PROC_PGRP_ONLY
        exited = os.waitid(os.P_PID, pgid, os.WEXITED | os.WNOWAIT | os.WNOHANG) is not None
    except (OSError, AttributeError):  # ChildProcessError included
        return False
    if filled <= 0 or filled >= ctypes.sizeof(buffer):
        return False
    return exited and list(buffer[: filled // ctypes.sizeof(ctypes.c_int)]) == [pgid]


def _live_group_members(pgid: int) -> list[int] | None:
    """Pids in process group *pgid* that are not zombies, or None when ``ps`` cannot tell."""
    try:
        listing = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["ps", "-A", "-o", "pid=,pgid=,stat="],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    members = []
    for line in listing.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[1] == str(pgid) and not fields[2].startswith("Z"):
            members.append(int(fields[0]))
    return members


def _kill_process_group(pgid: int) -> None:
    """SIGKILL group *pgid*; the caller guarantees its leader is not reaped yet (#3017).

    macOS refuses (EPERM) to signal a group whose only member is a zombie, which is what an
    unreaped leader that exited is. Linux signals it. Any other EPERM means a member this
    process may not signal survived, and that is raised, not taken as an empty group."""
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass  # nothing left in the group
    except PermissionError as exc:
        if _only_exited_leader_left(pgid):
            return
        survivors = _live_group_members(pgid)
        if survivors == []:
            return
        detail = "ps could not list it" if survivors is None else f"pids {survivors}"
        raise PermissionError(
            errno.EPERM, f"process group {pgid} keeps members it may not signal ({detail})"
        ) from exc


def _leader_unreaped(pid: int) -> bool:
    """Whether *pid* is still this process's child, exited or not, and so still holds its
    pid and process group id. ``WNOWAIT`` leaves an exited child unreaped."""
    try:
        os.waitid(os.P_PID, pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)
    except ChildProcessError:
        return False
    return True


def _wait_leader_unreaped(pid: int, deadline: float | None) -> bool:
    """Wait until *pid* exits without reaping it; False if *deadline* passes first.

    Polled like ``Popen.wait(timeout)`` when there is a deadline. ChildProcessError means
    something else reaped it."""
    if deadline is None:
        os.waitid(os.P_PID, pid, os.WEXITED | os.WNOWAIT)
        return True
    delay = 0.0005
    while os.waitid(os.P_PID, pid, os.WEXITED | os.WNOWAIT | os.WNOHANG) is None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(delay, remaining))
        delay = min(delay * 2, 0.05)
    return True


def _read_pipes(process: subprocess.Popen, deadline: float | None) -> tuple[dict[int, bytes], bool]:
    """Read stdout and stderr to EOF, as ``communicate`` does, without waiting for the child.

    Returns the bytes read per fd and whether *deadline* passed first."""
    pipes = [stream.fileno() for stream in (process.stdout, process.stderr) if stream]
    chunks: dict[int, list[bytes]] = {fd: [] for fd in pipes}
    selector_type = getattr(selectors, "PollSelector", selectors.SelectSelector)
    timed_out = False
    with selector_type() as selector:
        for fd in pipes:
            selector.register(fd, selectors.EVENT_READ)
        while selector.get_map():
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                timed_out = True
                break
            for key, _events in selector.select(remaining):
                data = os.read(key.fd, 32768)
                if data:
                    chunks[key.fd].append(data)
                else:
                    selector.unregister(key.fd)
    return {fd: b"".join(parts) for fd, parts in chunks.items()}, timed_out


def _kill_group_then_reap(process: subprocess.Popen) -> None:
    """SIGKILL the child's process group while the child is unreaped, then reap the child.

    The group id is the child's pid, which stays reserved while the child is unreaped (a zombie
    included). Once reaped and the group is empty, the id may name an unrelated group, so the
    group is never signalled after that. Only this function reaps the child, so an unreaped
    child seen just before ``killpg`` is still unreaped at ``killpg``."""
    reaped_elsewhere = not _leader_unreaped(process.pid)
    try:
        if not reaped_elsewhere:
            _kill_process_group(process.pid)
    finally:
        process.wait()
    if reaped_elsewhere:
        raise ChildProcessError(
            f"child {process.pid} was reaped outside run_reaping_process_group; "
            "its process group was not signalled"
        )


def run_reaping_process_group(
    argv: Sequence[str],
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    capture_output: bool = True,
    text: bool = True,
    timeout: float | None = None,
) -> subprocess.CompletedProcess:
    """``subprocess.run(argv, check=False)`` in a new session, whose process group is killed after.

    A child that forks and closes its output lets ``subprocess.run`` return while the fork keeps
    running, and a timeout kills only the direct child (#3017). Here the child leads its own
    process group, and that whole group gets SIGKILL on every return path, normal or timeout
    (as ``sandboxed_lane`` does on timeout for its lane runs, #2650), always before the child is
    reaped, so the group id cannot have been reused. A descendant that calls ``setsid()``
    itself leaves the group and is not reached.
    ``subprocess.TimeoutExpired`` propagates, as it does from ``subprocess.run``; a group member
    this process may not signal raises PermissionError once the child is reaped."""

    pipe = subprocess.PIPE if capture_output else None
    deadline = None if timeout is None else time.monotonic() + timeout
    with subprocess.Popen(  # noqa: S603 - argv list, no shell
        list(argv),
        cwd=None if cwd is None else str(cwd),
        env=None if env is None else dict(env),
        stdout=pipe,
        stderr=pipe,
        text=text,
        start_new_session=True,
    ) as process:
        streams = (process.stdout, process.stderr)
        try:
            # Neither step reaps the child: communicate() and wait() would.
            output, timed_out = _read_pipes(process, deadline)
            timed_out = timed_out or not _wait_leader_unreaped(process.pid, deadline)
        except BaseException:
            _kill_group_then_reap(process)
            raise
        _kill_group_then_reap(process)
        captured = [None if s is None else output.get(s.fileno(), b"") for s in streams]
        if timed_out:
            # As subprocess.run on POSIX: the bytes read so far, None for an empty stream.
            raise subprocess.TimeoutExpired(
                process.args,
                timeout or 0,
                output=captured[0] or None,
                stderr=captured[1] or None,
            )
        stdout, stderr = (
            _decode(data, stream) if text and data is not None else data
            for data, stream in zip(captured, streams)
        )
    return subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)


def _decode(data: bytes, stream: object) -> str:
    """Decode as ``communicate`` does in text mode: the stream's encoding, universal newlines."""
    encoding = getattr(stream, "encoding", None) or "utf-8"
    errors = getattr(stream, "errors", None) or "strict"
    return data.decode(encoding, errors).replace("\r\n", "\n").replace("\r", "\n")


def run_command_string(
    command: str,
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = None,
    capture_output: bool = True,
    argv_prefix: Sequence[str] = (),
    reap_process_group: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run *command* without a shell and return one combined result.

    ``subprocess.TimeoutExpired`` propagates, as it does from
    ``subprocess.run``; callers keep their existing timeout handling.
    ``argv_prefix`` is prepended to every segment's argv (e.g. a
    ``sandbox-exec`` wrapper, #2936). With ``reap_process_group`` each
    segment runs through ``run_reaping_process_group`` (#3017).
    """
    try:
        segments = _split_chain(command)
    except UnsupportedShellSyntax as exc:
        return subprocess.CompletedProcess(
            command, UNSUPPORTED_SYNTAX_EXIT, "", f"refused (no shell): {exc}\n"
        )
    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    returncode = 0
    base_env = dict(os.environ if env is None else env)
    for segment in segments:
        assignments, argv = _split_assignments(segment)
        if not argv:
            # Bare assignments set nothing for later segments, like a subshell.
            continue
        try:
            if reap_process_group:
                completed = run_reaping_process_group(
                    [*argv_prefix, *argv],
                    cwd=cwd,
                    env={**base_env, **assignments},
                    capture_output=capture_output,
                    timeout=timeout,
                )
            else:
                completed = subprocess.run(
                    [*argv_prefix, *argv],
                    cwd=None if cwd is None else str(cwd),
                    env={**base_env, **assignments},
                    capture_output=capture_output,
                    text=True,
                    timeout=timeout,
                    check=False,
                )
        except (FileNotFoundError, PermissionError, NotADirectoryError) as exc:
            stderr_parts.append(f"{argv[0]}: {exc}\n")
            returncode = COMMAND_NOT_FOUND_EXIT
            break
        stdout_parts.append(completed.stdout or "")
        stderr_parts.append(completed.stderr or "")
        returncode = completed.returncode
        if returncode != 0:
            break
    return subprocess.CompletedProcess(
        command, returncode, "".join(stdout_parts), "".join(stderr_parts)
    )
