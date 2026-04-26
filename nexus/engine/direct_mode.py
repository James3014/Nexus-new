from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
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


def evaluate_direct_mode_completion(
    *,
    project_root: Path,
    task_desc: str,
    artifact_paths: list[str] | None = None,
) -> dict:
    spec = analyze_task_spec(task_desc)
    if not spec.enabled:
        return {
            "enabled": False,
            "semantic_failures": [],
            "verify_results": [],
            "changed_targets": [],
        }

    failures: list[str] = []
    verify_results: list[dict] = []
    changed_targets: list[str] = []

    for rel_path in spec.target_files:
        try:
            res = subprocess.run(
                ["git", "status", "--short", "--", rel_path],
                cwd=project_root,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception as exc:  # noqa: BLE001
            failures.append(f"target_status_probe_failed:{rel_path}:{exc}")
            continue
        if res.stdout.strip():
            changed_targets.append(rel_path)

    if spec.target_files and not changed_targets:
        failures.append("direct_mode_target_files_unchanged")

    for cmd in spec.verify_commands:
        try:
            res = subprocess.run(
                cmd,
                cwd=project_root,
                shell=True,
                capture_output=True,
                text=True,
                check=False,
            )
            verify_results.append(
                {
                    "command": cmd,
                    "exit_code": int(res.returncode),
                    "stdout": (res.stdout or "")[:400],
                    "stderr": (res.stderr or "")[:400],
                }
            )
            if res.returncode != 0:
                failures.append(f"direct_mode_verify_failed:{cmd}")
        except Exception as exc:  # noqa: BLE001
            verify_results.append(
                {
                    "command": cmd,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": str(exc),
                }
            )
            failures.append(f"direct_mode_verify_error:{cmd}")

    resolved_artifacts = [
        str(path)
        for path in (artifact_paths or [])
        if Path(path).exists() or (project_root / path).exists()
    ]

    return {
        "enabled": True,
        "semantic_failures": failures,
        "verify_results": verify_results,
        "changed_targets": changed_targets,
        "artifact_paths": resolved_artifacts,
        "spec": {
            "reason": spec.reason,
            "target_files": list(spec.target_files),
            "verify_commands": list(spec.verify_commands),
        },
    }
