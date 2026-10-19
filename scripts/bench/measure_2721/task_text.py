"""The one task text both arms receive, and the worker prompt built from it.

P1 accepts ``what`` and ``why`` of at most 4000 characters each
(``unified_mcp_gateway._text``) and strips surrounding whitespace.  Both arms
get the exact same (``what``, ``why``, ``allowed_files``, ``verifier_commands``)
and the BARE arm's prompt is rendered with the same template the Gateway
worker uses (``task_build._prompt``), so the base prompts are byte-identical;
the NEXUS arm differs only by whatever Nexus itself appends.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

TEXT_VERSION = "measure-2721-text.v1"
FIELD_MAX = 4000  # unified_mcp_gateway._text max_length for what / why
CONTINUED_MARKER = "\n[The issue text continues at the start of WHY.]"
TRUNCATED_MARKER = "\n[Issue text truncated here.]"
INSTRUCTION = (
    "Fix the GitHub issue described in WHAT in this repository checkout. "
    "Change only source files inside the allowed scope. Do not add or modify test files: "
    "hidden tests that you cannot see will judge the fix."
)
# Shared, neutral verifier: needs no task environment and touches no hidden test.
DEFAULT_VERIFIERS: tuple[str, ...] = ("git diff --check",)


@dataclass(frozen=True)
class TaskText:
    what: str
    why: str
    allowed_files: tuple[str, ...]
    verifier_commands: tuple[str, ...]
    truncated: bool
    statement_chars: int
    text_version: str = TEXT_VERSION

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["allowed_files"] = list(self.allowed_files)
        data["verifier_commands"] = list(self.verifier_commands)
        return data

    def sha256(self) -> str:
        return sha256_json(
            {
                "what": self.what,
                "why": self.why,
                "allowed_files": list(self.allowed_files),
                "verifier_commands": list(self.verifier_commands),
            }
        )


def sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def build_task_text(
    problem_statement: str,
    allowed_files: Sequence[str],
    verifier_commands: Sequence[str] = DEFAULT_VERIFIERS,
) -> TaskText:
    """Split the verbatim issue text over ``what`` and ``why`` within P1 limits."""
    statement = str(problem_statement).strip()
    if not statement:
        raise ValueError("problem_statement is empty")
    allowed = tuple(str(path) for path in allowed_files)
    verifiers = tuple(str(command) for command in verifier_commands)
    if not 1 <= len(allowed) <= 4:
        raise ValueError("allowed_files must contain 1-4 entries (P1 limit)")
    if not 1 <= len(verifiers) <= 4:
        raise ValueError("verifier_commands must contain 1-4 entries (P1 limit)")
    truncated = False
    if len(statement) <= FIELD_MAX:
        what, rest = statement, ""
    else:
        cut = FIELD_MAX - len(CONTINUED_MARKER)
        what, rest = statement[:cut].rstrip() + CONTINUED_MARKER, statement[cut:].lstrip()
    why = INSTRUCTION
    if rest:
        room = FIELD_MAX - len(INSTRUCTION) - 2
        if len(rest) > room:
            rest = rest[: room - len(TRUNCATED_MARKER)].rstrip() + TRUNCATED_MARKER
            truncated = True
        why = f"{rest}\n\n{INSTRUCTION}"
    what, why = what.strip(), why.strip()
    assert len(what) <= FIELD_MAX and len(why) <= FIELD_MAX
    return TaskText(
        what=what,
        why=why,
        allowed_files=allowed,
        verifier_commands=verifiers,
        truncated=truncated,
        statement_chars=len(statement),
    )


def render_worker_prompt(text: TaskText | Mapping[str, Any]) -> str:
    """Byte-identical copy of ``SelfHostedTaskService._prompt`` (task_build.py).

    ``tests/bench/test_measure_2721_harness.py`` pins this against the real
    method so a template change in Nexus breaks the test instead of silently
    breaking symmetry.
    """
    data = text.as_dict() if isinstance(text, TaskText) else dict(text)
    allowed = ", ".join(data["allowed_files"])
    verifiers = "\n".join(f"- {command}" for command in data["verifier_commands"])
    return (
        f"WHAT: {data['what']}\n"
        f"WHY: {data['why']}\n"
        f"Allowed files: {allowed}\n"
        "Work only in the isolated Target. Do not edit, delete, stage, commit, merge, push, or reset "
        "outside the allowed scope. Run every verifier command below after making the change; if any "
        "verifier fails, diagnose and repair within the allowed files before returning.\n"
        f"Required verifier commands:\n{verifiers}\n"
        "Return a concise summary only after all required verifiers pass."
    )
