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

import os
import re
import subprocess
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
