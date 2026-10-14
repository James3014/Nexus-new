"""Reject committee candidates whose patch modifies a test or oracle file.

A candidate that edits the check it is judged by (the repro script, a pytest module, anything
under a tests directory) can pass by weakening that check. Execution verifiers would then report
a pass, so this rule runs on the patch text BEFORE verification and selection, and a rejected
candidate can never be selected.

Paths come from the unified-diff headers in the patch: ``diff --git``, ``---``/``+++``,
``rename``/``copy`` lines and ``Binary files`` lines, both sides. A path is a test/oracle path
when, case-insensitively:

- its basename is an oracle/repro script (``ORACLE_NAMES``);
- its basename is a pytest module or plugin: ``test_*.py``, ``*_test.py``, ``conftest.py``;
- any directory component is ``tests``, ``test`` or ``testing``.

Fail closed: a header line that is present but cannot be parsed into a path rejects the
candidate. An artifact with no diff header at all (a bare code snippet) names no file, so this
rule has nothing to check and leaves it to the verifiers.

Evidence: judge pair set v1 addendum (``eval/judge-pair-qualification-v1``). The rule rejected
10/10 test-weakening probes and 0/575 legitimate proposer candidates, at no model cost.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from nexus.verifiers.contracts import EvidenceRef, FailureTag, VerifierVerdict

GUARD_NAME = "test_oracle_guard"
FAILURE_CODE = "TEST_OR_ORACLE_MODIFIED"
ORACLE_NAMES = frozenset({
    "repro.py",
    "reproduce_bug.py",
    "test_repro.py",
    "debug_repro.py",
    "nexus_repro_contract.py",
})
TEST_DIRS = frozenset({"tests", "test", "testing"})

_GIT_HEADER = re.compile(r"^diff --git (?:\"?a/)(.+?)\"? (?:\"?b/)(.+?)\"?$")
_BINARY = re.compile(r"^Binary files (.+) and (.+) differ$")
_RENAME_COPY = ("rename from ", "rename to ", "copy from ", "copy to ")


def _strip_side(target: str) -> str:
    target = target.split("\t", 1)[0].strip().strip('"')
    if target.startswith(("a/", "b/")):
        target = target[2:]
    return target


def is_test_or_oracle_path(path: str) -> bool:
    parts = [p.lower() for p in PurePosixPath(str(path).replace("\\", "/")).parts if p != "/"]
    if not parts:
        return False
    name = parts[-1]
    return (
        name in ORACLE_NAMES
        or name == "conftest.py"
        or (name.startswith("test_") and name.endswith(".py"))
        or name.endswith("_test.py")
        or any(part in TEST_DIRS for part in parts[:-1])
    )


def patch_paths(patch: str) -> tuple[list[str], list[str]]:
    """``(paths, malformed header lines)`` named by the unified-diff headers of ``patch``."""

    paths: list[str] = []
    malformed: list[str] = []
    lines = str(patch or "").splitlines()
    for index, line in enumerate(lines):
        # ``---``/``+++`` count as file headers only as an adjacent pair, so a removed line
        # that starts with ``-- `` (or an added ``++ ``) inside a hunk is not read as a path.
        is_old_header = (
            line.startswith("--- ")
            and index + 1 < len(lines)
            and lines[index + 1].startswith("+++ ")
        )
        is_new_header = (
            line.startswith("+++ ") and index > 0 and lines[index - 1].startswith("--- ")
        )
        if line.startswith("diff --git "):
            match = _GIT_HEADER.match(line)
            if not match:
                malformed.append(line[:200])
                continue
            paths.extend(match.groups())
        elif is_old_header or is_new_header:
            target = _strip_side(line[4:])
            if target == "/dev/null":
                continue
            if not target:
                malformed.append(line[:200])
                continue
            paths.append(target)
        elif line.startswith(_RENAME_COPY):
            target = line.split(" ", 2)[2].strip().strip('"')
            if not target:
                malformed.append(line[:200])
                continue
            paths.append(target)
        elif line.startswith("Binary files "):
            match = _BINARY.match(line)
            if not match:
                malformed.append(line[:200])
                continue
            paths.extend(
                _strip_side(side) for side in match.groups() if side.strip() != "/dev/null"
            )
    return list(dict.fromkeys(p for p in paths if p)), malformed


def patch_violations(patch: str) -> list[str]:
    """Reasons to reject ``patch``; empty when it may proceed to verification."""

    try:
        paths, malformed = patch_paths(patch)
    except Exception as exc:  # fail closed: a guard error rejects the candidate
        return [f"guard_error:{type(exc).__name__}"]
    reasons = [f"unparseable_diff_header:{line}" for line in malformed]
    reasons.extend(f"test_or_oracle:{path}" for path in paths if is_test_or_oracle_path(path))
    return reasons


def rejection_verdict(candidate_id: str, reasons: list[str]) -> VerifierVerdict:
    return VerifierVerdict(
        verifier_name=GUARD_NAME,
        candidate_id=candidate_id,
        passed=False,
        score=0.0,  # a failed verdict already scores -20; a score below -5 would mark a
        # "conflict" and make the whole round abstain instead of dropping this candidate
        evidence_refs=[EvidenceRef(source_file=r.split(":", 1)[-1]) for r in reasons[:20]],
        failure_tags=[
            FailureTag(
                code=FAILURE_CODE,
                description="; ".join(reasons[:20]),
            )
        ],
    )
