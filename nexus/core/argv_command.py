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

import contextlib
import ctypes
import errno
import os
import re
import select
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Mapping, Sequence

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


class ProcessGroupReapingUnavailable(OSError):
    """Refused before anything is spawned: the child could not be kept unreaped until its
    process group has been killed (#3017)."""


_PROC_PGRP_ONLY = 2  # proc_listpids type, <libproc.h>
_PROC_PIDTBSDINFO = 3  # proc_pidinfo flavor, <sys/proc_info.h>
_SZOMB = 5  # pbi_status of an exited, unreaped process
_KILL_SETTLE_SECONDS = 2.0  # how long SIGKILLed group members get to die
_PROC_ROOT = "/proc"
_DIGITS = re.compile(r"[0-9]+")


class _ProcBsdInfo(ctypes.Structure):
    """macOS ``struct proc_bsdinfo`` (<sys/proc_info.h>), the fields read here named."""

    _fields_ = [
        ("pbi_flags", ctypes.c_uint32),
        ("pbi_status", ctypes.c_uint32),
        ("pbi_xstatus", ctypes.c_uint32),
        ("pbi_pid", ctypes.c_uint32),
        ("pbi_ppid", ctypes.c_uint32),
        ("ids", ctypes.c_uint32 * 7),  # uid, gid, ruid, rgid, svuid, svgid, reserved
        ("pbi_comm", ctypes.c_char * 16),
        ("pbi_name", ctypes.c_char * 32),
        ("pbi_nfiles", ctypes.c_uint32),
        ("pbi_pgid", ctypes.c_uint32),
        ("job", ctypes.c_uint32 * 4),  # pjobc, e_tdev, e_tpgid, nice
        ("pbi_start", ctypes.c_uint64 * 2),
    ]


def _libproc():
    """macOS libproc with the two calls used here typed; None elsewhere or if it cannot load."""
    if sys.platform != "darwin":
        return None
    try:
        lib = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    except OSError:
        return None
    lib.proc_listpids.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int]
    lib.proc_listpids.restype = ctypes.c_int
    lib.proc_pidinfo.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint64,
        ctypes.c_void_p,
        ctypes.c_int,
    ]
    lib.proc_pidinfo.restype = ctypes.c_int
    return lib


def _darwin_proc(pid: int) -> _ProcBsdInfo | None:
    """macOS: *pid*'s BSD info, a zombie's included; None when no process has that pid.

    Raises OSError when libproc cannot answer."""
    lib = _libproc()
    if lib is None:
        raise OSError(errno.ENOSYS, "libproc is not available")
    info = _ProcBsdInfo()
    size = ctypes.sizeof(info)
    # arg 1 makes PROC_PIDTBSDINFO find zombies too
    if lib.proc_pidinfo(pid, _PROC_PIDTBSDINFO, 1, ctypes.byref(info), size) != size:
        code = ctypes.get_errno()
        if code == errno.ESRCH:
            return None
        raise OSError(code or errno.EIO, f"proc_pidinfo({pid}) failed")
    if info.pbi_pid != pid:
        raise OSError(errno.EIO, f"proc_pidinfo({pid}) answered for pid {info.pbi_pid}")
    return info


def _darwin_group_pids(pgid: int) -> list[int] | None:
    """macOS: every pid in group *pgid*, zombies included; None when libproc cannot tell."""
    lib = _libproc()
    if lib is None:
        return None
    buffer = (ctypes.c_int * 1024)()
    size = ctypes.sizeof(buffer)
    width = ctypes.sizeof(ctypes.c_int)
    filled = lib.proc_listpids(_PROC_PGRP_ONLY, pgid, buffer, size)
    if filled <= 0 or filled >= size or filled % width:
        return None
    return list(buffer[: filled // width])


def _only_exited_leader_left(pgid: int) -> bool:
    """macOS: whether group *pgid* holds nothing but its leader, exited and unreaped.

    The leader is checked first: once it is a zombie it forks no new member, so a listing taken
    after that holds every member. Anything libproc cannot tell is left to the full listing."""
    try:
        leader = _darwin_proc(pgid)
    except OSError:
        return False
    return leader is not None and leader.pbi_status == _SZOMB and _darwin_group_pids(pgid) == [pgid]


def _proc_live_group_members(pgid: int) -> list[int] | None:
    """Linux: pids in group *pgid* that are not zombies, read from /proc; None if unreadable."""
    try:
        names = [name for name in os.listdir(_PROC_ROOT) if _DIGITS.fullmatch(name)]
    except OSError:
        return None
    members = []
    seen_self = False
    for name in names:
        try:
            with open(os.path.join(_PROC_ROOT, name, "stat"), "rb") as stat_file:
                stat = stat_file.read()
        except (FileNotFoundError, ProcessLookupError):
            continue  # exited since the listing
        except OSError:
            return None
        # "pid (comm) state ppid pgrp ...": comm may hold spaces and parentheses
        _head, paren, tail = stat.rpartition(b")")
        fields = tail.split()
        if not paren or len(fields) < 3 or len(fields[0]) != 1 or not fields[2].isdigit():
            return None
        if int(fields[2]) == pgid and fields[0] not in (b"Z", b"X"):
            members.append(int(name))
        seen_self = seen_self or int(name) == os.getpid()
    # This process is always listed; a listing without it is not a full one.
    return members if seen_self else None


def _ps_live_group_members(pgid: int) -> list[int] | None:
    """Pids in group *pgid* that are neither zombies nor exiting, from ``/bin/ps``; None if it
    cannot tell.

    A state starting with ``Z`` (zombie) or holding ``E`` (macOS/BSD: trying to exit, it runs
    no more user code) is not live; macOS shows ``?`` for a state it cannot read. Any row that
    is not exactly ``pid pgid stat``, or a listing that misses this process itself, counts as
    unknown rather than as an empty group."""
    try:
        listing = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["/bin/ps", "-A", "-o", "pid=,pgid=,stat="],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    members = []
    listed = set()
    for line in listing.splitlines():
        fields = line.split()
        if len(fields) != 3 or not _DIGITS.fullmatch(fields[0]) or not _DIGITS.fullmatch(fields[1]):
            return None
        listed.add(int(fields[0]))
        state = fields[2]
        if int(fields[1]) == pgid and not state.startswith("Z") and "E" not in state:
            members.append(int(fields[0]))
    return members if os.getpid() in listed else None


def _live_group_members(pgid: int) -> list[int] | None:
    """Pids in process group *pgid* that are not zombies, or None when that cannot be told.

    Linux reads /proc, elsewhere ``/bin/ps``. A member the listing does not show this process
    (Linux ``hidepid``) cannot be seen."""
    if sys.platform.startswith("linux"):
        return _proc_live_group_members(pgid)
    return _ps_live_group_members(pgid)


def _group_survivors(pgid: int) -> list[int] | None:
    """Live members of group *pgid*: [] for none, None when unknown."""
    return [] if _only_exited_leader_left(pgid) else _live_group_members(pgid)


def _survivors_error(pgid: int, survivors: list[int] | None) -> PermissionError:
    detail = "it could not be listed" if survivors is None else f"pids {survivors}"
    return PermissionError(
        errno.EPERM, f"process group {pgid} keeps members it may not signal ({detail})"
    )


def _kill_process_group(pgid: int) -> None:
    """SIGKILL group *pgid* and confirm no live member is left; the caller guarantees its leader
    is not reaped yet (#3017).

    ``killpg`` succeeds once any member could be signalled, so a member with other credentials
    can survive a successful call: after one, the members get ``_KILL_SETTLE_SECONDS`` to die
    and any still alive are raised. macOS refuses (EPERM) to signal a group whose only member is
    a zombie, which is what an unreaped leader that exited is; Linux signals it. After EPERM
    nothing was signalled, so a live member then is raised at once. A survivor, or a group that
    cannot be listed, raises PermissionError: never taken as an empty group."""
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return  # nothing left in the group
    except PermissionError as exc:
        survivors = _group_survivors(pgid)
        if survivors == []:
            return
        raise _survivors_error(pgid, survivors) from exc
    deadline = time.monotonic() + _KILL_SETTLE_SECONDS
    delay = 0.001
    while not _only_exited_leader_left(pgid):
        # On macOS libproc's quick answer is retried and the full listing (a ps run) asked only
        # at the deadline; Linux reads /proc each time.
        last_try = time.monotonic() >= deadline
        if last_try or sys.platform != "darwin":
            survivors = _live_group_members(pgid)
            if survivors == []:
                return
            if last_try:
                raise _survivors_error(pgid, survivors)
        time.sleep(min(delay, max(0.0, deadline - time.monotonic())))
        delay = min(delay * 2, 0.05)


def _waitid_available() -> bool:
    return hasattr(os, "waitid") and hasattr(os, "WNOWAIT")


def _kqueue_available() -> bool:
    names = ("kqueue", "kevent", "KQ_FILTER_PROC", "KQ_NOTE_EXIT")
    return sys.platform == "darwin" and all(hasattr(select, name) for name in names)


def _refuse_unless_child_stays_unreaped() -> None:
    """Raise ProcessGroupReapingUnavailable, before anything is spawned, when the child cannot be
    waited for without being reaped, or SIGCHLD lets someone else reap it."""
    if not (_waitid_available() or _kqueue_available()):
        raise ProcessGroupReapingUnavailable(
            errno.ENOSYS,
            "cannot wait for a child without reaping it here "
            "(needs os.waitid with WNOWAIT, or kqueue on macOS)",
        )
    handler = signal.getsignal(signal.SIGCHLD)
    if handler is not signal.SIG_DFL:
        # SIG_IGN makes the kernel reap children itself; a handler (Python or not installed
        # from Python) is where a waitpid(-1) reaper would live.
        raise ProcessGroupReapingUnavailable(
            errno.EINVAL, f"SIGCHLD is {handler!r}, not SIG_DFL: the child could be reaped"
        )


def _leader_unreaped(pid: int) -> bool:
    """Whether *pid* is still this process's unreaped child, exited or not, and so still holds
    its pid and process group id.

    Asked with ``waitid(WNOWAIT)`` where it exists, which leaves an exited child unreaped; on
    macOS otherwise through libproc: the pid must exist, zombie or not, as this process's child
    leading its own group. When libproc cannot answer, the precondition (only this module
    reaps the child) is relied on."""
    if _waitid_available():
        try:
            os.waitid(os.P_PID, pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)
        except ChildProcessError:
            return False
        return True
    try:
        info = _darwin_proc(pid)
    except OSError:
        return True
    return info is not None and info.pbi_ppid == os.getpid() and info.pbi_pgid == pid


def _await_zombie(pid: int) -> None:
    """macOS: kqueue reports NOTE_EXIT while *pid* is still exiting, before it is a zombie (and
    ``killpg`` on it is refused meanwhile); wait, at most ``_KILL_SETTLE_SECONDS``, until it is
    one, as ``waitid`` would report it. Past that, the cleanup's listing still copes."""
    deadline = time.monotonic() + _KILL_SETTLE_SECONDS
    delay = 0.0005
    while time.monotonic() < deadline:
        try:
            info = _darwin_proc(pid)
        except OSError:
            return
        if info is None or info.pbi_status == _SZOMB:
            return
        time.sleep(delay)
        delay = min(delay * 2, 0.05)


def _kqueue_wait_exit(pid: int, deadline: float | None) -> bool:
    """macOS without ``os.waitid``: wait for *pid* to exit through kqueue, which does not reap.

    ESRCH on registration means the pid no longer runs: it exited and waits unreaped (only this
    module reaps it), or something else reaped it, which ``_leader_unreaped`` then reports."""
    # CI's pyright uses Linux stubs, which have no kqueue; only macOS runs this.
    kq = select.kqueue()  # pyright: ignore[reportAttributeAccessIssue]
    try:
        change = select.kevent(  # pyright: ignore[reportAttributeAccessIssue]
            pid,
            filter=select.KQ_FILTER_PROC,  # pyright: ignore[reportAttributeAccessIssue]
            flags=select.KQ_EV_ADD,  # pyright: ignore[reportAttributeAccessIssue]
            fflags=select.KQ_NOTE_EXIT,  # pyright: ignore[reportAttributeAccessIssue]
        )
        try:
            kq.control([change], 0)
        except ProcessLookupError:
            _await_zombie(pid)
            return True
        while True:
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            for event in kq.control(None, 1, remaining):
                if event.flags & select.KQ_EV_ERROR:  # pyright: ignore[reportAttributeAccessIssue]
                    raise OSError(event.data, os.strerror(event.data))
                if event.ident == pid and event.fflags & select.KQ_NOTE_EXIT:  # pyright: ignore[reportAttributeAccessIssue]
                    _await_zombie(pid)
                    return True
            if deadline is not None and time.monotonic() >= deadline:
                return False
    finally:
        kq.close()


def _wait_leader_unreaped(pid: int, deadline: float | None) -> bool:
    """Wait until *pid* exits without reaping it; False if *deadline* passes first.

    ``waitid(WNOWAIT)``, polled like ``Popen.wait(timeout)`` when there is a deadline, where it
    exists; kqueue on macOS before Python 3.13. ChildProcessError means something else reaped
    it."""
    if not _waitid_available():
        return _kqueue_wait_exit(pid, deadline)
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
    group is never signalled after ``process.wait()``. The check just before ``killpg`` turns a
    reap that already happened elsewhere (a broken precondition, see
    ``run_reaping_process_group``) into ChildProcessError with nothing signalled; it cannot
    close the gap between itself and ``killpg``, which only that precondition does.

    If this is interrupted (a signal handler raising) before the group was signalled and
    checked, the group gets SIGKILL again on the way out, still before the reap; a second
    SIGKILL to the same unreaped group is harmless. The reap waits at most
    ``_KILL_SETTLE_SECONDS``: a leader still alive then (one this process may not signal) is
    left unreaped, never signalled again, and raised as PermissionError."""
    unreaped = True
    finished = False
    try:
        unreaped = _leader_unreaped(process.pid)
        if unreaped:
            _kill_process_group(process.pid)
        finished = True
    finally:
        if unreaped and not finished:
            with contextlib.suppress(OSError):
                os.killpg(process.pid, signal.SIGKILL)
        try:
            process.wait(timeout=_KILL_SETTLE_SECONDS)
        except subprocess.TimeoutExpired as exc:
            raise PermissionError(
                errno.EPERM, f"child {process.pid} survived SIGKILL and is left unreaped"
            ) from exc
    if not unreaped:
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
    stdin: int | None = None,
) -> subprocess.CompletedProcess:
    """``subprocess.run(argv, check=False)`` in a new session, whose process group is killed after.

    A child that forks and closes its output lets ``subprocess.run`` return while the fork keeps
    running, and a timeout kills only the direct child (#3017). Here the child leads its own
    process group, and that whole group gets SIGKILL on every exit path, normal, timeout or an
    exception (as ``sandboxed_lane`` does on timeout for its lane runs, #2650), always before
    the child is reaped. A descendant that calls ``setsid()`` itself leaves the group and is not
    reached. As in ``subprocess.run``, output is read to EOF before the group is killed, so a
    member that keeps the pipes open holds the result until it exits or *timeout* passes.

    Precondition: only this function reaps the child, so its pid, which is the group id, cannot
    be reused before ``killpg``. Refused before anything is spawned, with
    ProcessGroupReapingUnavailable: SIGCHLD not at SIG_DFL (SIG_IGN lets the kernel reap
    children itself; a handler is where a ``waitpid(-1)`` reaper lives), or no way to wait for
    the child without reaping it (``os.waitid`` with ``WNOWAIT``, or kqueue on macOS). Not
    checkable, so required of the caller: nothing else in this process (another thread, a C
    library) waits for this child or calls ``waitpid(-1)``/``wait()`` while it runs, or sets
    SIGCHLD to SIG_IGN or SA_NOCLDWAIT after the check. A reap elsewhere that already happened
    when the group is about to be signalled raises ChildProcessError with nothing signalled.

    ``subprocess.TimeoutExpired`` propagates, as it does from ``subprocess.run``. A group member
    that is still alive after SIGKILL (other credentials, or not dead within
    ``_KILL_SETTLE_SECONDS``), or a group that cannot be listed, raises PermissionError once
    the child is reaped; a leader itself still alive then is left unreaped, not waited for.
    ``stdin`` is passed to ``Popen`` as is (e.g. ``subprocess.DEVNULL``); None inherits it.
    ``subprocess.PIPE`` is refused: nothing here would ever write to or close it."""

    if stdin == subprocess.PIPE:
        raise ValueError("stdin=PIPE is not supported: nothing would write to it")
    _refuse_unless_child_stays_unreaped()
    pipe = subprocess.PIPE if capture_output else None
    deadline = None if timeout is None else time.monotonic() + timeout
    # Not a ``with`` block: Popen.__exit__ would wait for the child without a bound.
    process = subprocess.Popen(  # noqa: S603 - argv list, no shell
        list(argv),
        cwd=None if cwd is None else str(cwd),
        env=None if env is None else dict(env),
        stdin=stdin,
        stdout=pipe,
        stderr=pipe,
        text=text,
        start_new_session=True,
    )
    streams = (process.stdout, process.stderr)
    try:
        try:
            # Neither step reaps the child: communicate() and wait() would.
            output, timed_out = _read_pipes(process, deadline)
            timed_out = timed_out or not _wait_leader_unreaped(process.pid, deadline)
        finally:
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
    finally:
        for stream in streams:
            if stream is not None:
                stream.close()
    return subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)


def require_child_stays_unreaped() -> None:
    """Raise ProcessGroupReapingUnavailable unless a child can be waited for without being
    reaped here; call it before spawning a child for ``communicate_then_kill_group``."""
    _refuse_unless_child_stays_unreaped()


def communicate_then_kill_group(
    process: subprocess.Popen,
    timeout: float | None,
    before_kill: Callable[[], object] | None = None,
) -> tuple[bytes, bytes]:
    """``process.communicate(timeout=timeout)`` that also SIGKILLs the child's process group once
    the child exits, before it is reaped (#3052). For a child the caller started with
    ``start_new_session=True`` and binary pipes; returns (stdout, stderr), b"" for no pipe.

    Same precondition as ``run_reaping_process_group``: check ``require_child_stays_unreaped``
    before spawning, and nothing else reaps the child meanwhile. On timeout it raises
    ``subprocess.TimeoutExpired`` with the output read so far and leaves the child running,
    unsignalled and unreaped, its pipes open, as ``communicate`` does, for the caller's own
    timeout handling. ``before_kill``, if given, runs once the child has exited and its output is
    read, before the group is signalled (the group is still killed if it raises). A group member
    alive after SIGKILL raises PermissionError once the child is reaped; a reap that already
    happened elsewhere raises ChildProcessError."""
    deadline = None if timeout is None else time.monotonic() + timeout
    streams = (process.stdout, process.stderr)
    output, timed_out = _read_pipes(process, deadline)
    timed_out = timed_out or not _wait_leader_unreaped(process.pid, deadline)
    captured = [b"" if s is None else output.get(s.fileno(), b"") for s in streams]
    if timed_out:
        raise subprocess.TimeoutExpired(
            process.args, timeout or 0, output=captured[0], stderr=captured[1]
        )
    try:
        try:
            if before_kill is not None:
                before_kill()
        finally:
            _kill_group_then_reap(process)
    finally:
        for stream in streams:
            if stream is not None:
                stream.close()
    return captured[0], captured[1]


def kill_group_if_exited(process: subprocess.Popen) -> bool:
    """Non-blocking ``process.poll()`` that also SIGKILLs the child's process group once the child
    has exited, before it is reaped (#3052). For a child the caller started with
    ``start_new_session=True`` whose output does not go to pipes this process reads.

    False, with nothing signalled or reaped, while the child still runs. Once it has exited: the
    group gets SIGKILL, the child is reaped (``process.returncode`` is set) and True is
    returned. Same precondition as ``communicate_then_kill_group``: check
    ``require_child_stays_unreaped`` before spawning, and nothing else reaps the child
    meanwhile (``poll()`` or ``wait()`` included). A group member alive after SIGKILL raises
    PermissionError once the child is reaped; a reap that already happened elsewhere raises
    ChildProcessError with nothing signalled."""
    if process.returncode is None and not _wait_leader_unreaped(process.pid, time.monotonic()):
        return False
    _kill_group_then_reap(process)
    return True


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
