from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


_FILE_PATTERN = re.compile(
    r"(?P<path>(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.(?:py|json|yml|yaml|toml|md|txt|sh|ts|tsx|js|jsx))(?::(?P<line>\d+))?"
)
_VERIFY_PREFIX_PATTERN = re.compile(r"^(?:\d+\s+)?(?:`)?(?P<cmd>(?:uv run pytest|pytest|python3?\s+-m\s+pytest)\b.*?)(?:`)?$")
_EVIDENCE_KEYWORDS = (
    "root cause",
    "fix method",
    "failure",
    "failed test",
    "line",
    "bucket",
    "根因",
    "修法",
    "失敗測試",
    "行號",
)


@dataclass(frozen=True)
class DirectModeSpec:
    enabled: bool
    reason: str
    target_files: list[str]
    verify_commands: list[str]


def _dedupe(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = str(value).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def extract_target_files(task_desc: str) -> list[str]:
    if not task_desc:
        return []
    paths = [m.group("path") for m in _FILE_PATTERN.finditer(task_desc)]
    return _dedupe(paths)


def extract_verify_commands(task_desc: str) -> list[str]:
    if not task_desc:
        return []
    commands: list[str] = []
    for raw in task_desc.splitlines():
        line = raw.strip()
        if not line:
            continue
        matched = _VERIFY_PREFIX_PATTERN.match(line)
        if not matched:
            continue
        command = matched.group("cmd").strip()
        if "pytest" not in command:
            continue
        commands.append(command)
    return _dedupe(commands)


def analyze_task_spec(task_desc: str) -> DirectModeSpec:
    text = task_desc or ""
    lowered = text.lower()
    target_files = extract_target_files(text)
    verify_commands = extract_verify_commands(text)

    has_line_refs = bool(re.search(r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]+:\d+", text))
    has_evidence_keywords = any(keyword in lowered for keyword in _EVIDENCE_KEYWORDS)
    has_verify = len(verify_commands) > 0
    has_files = len(target_files) > 0

    confidence_signals = sum([has_files, has_verify, has_line_refs, has_evidence_keywords])
    enabled = bool(has_files and confidence_signals >= 2)

    reason = "explicit_user_repair_spec" if enabled else "default_autonomic_route"
    return DirectModeSpec(
        enabled=enabled,
        reason=reason,
        target_files=target_files,
        verify_commands=verify_commands,
    )
