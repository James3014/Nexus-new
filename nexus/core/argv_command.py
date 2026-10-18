"""Run legacy command strings without a shell (#2635 SEC-007).

Several legacy paths accepted a command *string* from repo files, plans or
model output and ran it with ``shell=True``. That lets any ``;``, ``|``,
``$(...)`` or redirect inside the string execute. This helper keeps the
string interface but never invokes a shell:

* the string is tokenized with :mod:`shlex` (POSIX quoting rules);
* ``a && b`` chains are supported: segments run in order and the chain stops
  at the first non-zero exit, as a shell would;
* leading ``NAME=value`` words are passed as environment variables;
* every other shell operator (``;``, ``|``, ``||``, ``>``, ``<``, ``&``,
  parentheses) is refused fail-closed with exit code 2 and nothing runs;
* no variable, glob, tilde or command substitution happens: ``$HOME`` or
  ``*.py`` reach the program literally.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Mapping, Sequence

UNSUPPORTED_SYNTAX_EXIT = 2
COMMAND_NOT_FOUND_EXIT = 127

_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_OPERATOR_CHARS = frozenset("();<>|&")


class UnsupportedShellSyntax(ValueError):
    """The command string needs a shell feature this runner refuses."""


def split_command_chain(command: str) -> list[list[str]]:
    """Return the ``&&``-separated segments of *command* as argv lists.

    Raises :class:`UnsupportedShellSyntax` for any other shell operator, for
    an empty segment, or for unbalanced quotes.
    """
    lexer = shlex.shlex(str(command), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError as exc:
        raise UnsupportedShellSyntax(f"unparseable command: {exc}") from exc
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token == "&&":
            segments.append([])
            continue
        if token and set(token) <= _OPERATOR_CHARS:
            raise UnsupportedShellSyntax(f"shell operator {token!r} is not supported")
        segments[-1].append(token)
    if any(not segment for segment in segments):
        raise UnsupportedShellSyntax("empty command segment")
    return segments


def _split_assignments(argv: Sequence[str]) -> tuple[dict[str, str], list[str]]:
    env: dict[str, str] = {}
    index = 0
    while index < len(argv) and _ASSIGNMENT.match(argv[index]):
        name, _, value = argv[index].partition("=")
        env[name] = value
        index += 1
    return env, list(argv[index:])


def run_command_string(
    command: str,
    *,
    cwd: str | Path | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = None,
    capture_output: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run *command* without a shell and return one combined result.

    ``subprocess.TimeoutExpired`` propagates, as it does from
    ``subprocess.run``; callers keep their existing timeout handling.
    """
    try:
        segments = split_command_chain(command)
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
            completed = subprocess.run(
                argv,
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
