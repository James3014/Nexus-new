"""Captured-prompt symmetry audit for the counted like-for-like A/B (online A/B S21).

Replaces the old ``_prompt_leak_audit_failures`` (which skipped hard_v1, exempted status
enums, and never looked at the prompts actually sent).  Input: the per-call records written by
``scripts/bench/agy_prompt_capture.py`` for both arms, plus each task's fixture material.

Per task x trial the audit requires:
  (b) at most one capture per arm (first attempt, one call), and a bare capture whenever the
      with-Nexus arm sent a prompt;
  (d) no hidden-only literal in any with-Nexus prompt (literal absent from the bare prompt);
  (e) the with-Nexus prompt contains the visible test text and no ``[Prior Art]``;
  (f) every non-empty with-Nexus prompt line, after removing the no-tools prefix, also appears
      in the bare prompt (no with-Nexus-only text).
Any violation makes the run's counted metric invalid.
"""

from __future__ import annotations

import ast
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA = "nexus_bench_prompt_symmetry_audit_v1"
NO_TOOLS_PREFIX = "Do not use any tools (no commands, no file reads, no file writes). Answer directly in this reply."
PRIOR_ART_MARKER = "[Prior Art]"

# Hidden-only literal list from the 2026-10-14 symmetry inventory (hidden minus visible test;
# hard_v1 strings also exist in the post-fix upstream code, so a hit there means repo exposure).
HIDDEN_LITERALS: dict[str, tuple[str, ...]] = {
    "nexus-value-hidden-001": ("duplicate", "idempotent"),
    "nexus-value-hidden-002": ("API__Token", "api-token", "  User   Name  "),
    "nexus-value-repair-001": ("'timeout': None", "'jitter': 1", "ignore None", "None-valued"),
    "nexus-value-repair-002": ("remaining_ms(100, 200, 50)", "clamp", "[0, timeout"),
    "nexus-value-gov-001": ("[REDACTED]", "'password': 'pw'"),
    "nexus-value-gov-002": ("can_access('unknown'", "deny by default", "fail closed"),
    "nexus-value-evidence-001": ("'status': 'fail', 'artifact'", "singular 'artifact'"),
    "nexus-value-evidence-002": ("missing claim", "phase_ready({'status': 'pass', 'reason': ''})"),
    "nexus-value-context-001": (
        "'result': 'ok'",
        "canonical output field is result",
        "FIELD = 'result'",
    ),
    "nexus-value-context-002": ("strict=True", "retries=3", "{'strict': True, 'retries': 3}"),
    "nexus-value-trust-001": ("'evidence': 'b'}]) == 'fail'",),
    "nexus-value-trust-002": ("needs_evidence", "{'verified': False}"),
    "oabh-ledger": ("unsupported mastery level", "LedgerContractError"),
    "oabh-remote": ("evil.github.com", "github.com.evil", "notgithub.com", "repo.git.git"),
    "oabh-diffhash": ("middle_anchor", "@@ -9,2 +9,2 @@", "bind_selected_to_applied"),
    "oabh-fence": ("agy_json_envelope", "NO_PATCH"),
    "oabh-activation": (
        "EMPTY_VARS",
        "DeleteAwareGh",
        "HTTP 422",
        "NEXUS_HYBRID_REPLICATION_T_AUTO",
    ),
    "oabh-conflict": (
        "UNSUPPORTED_MUTATION_LANE",
        "WRITER_REVISION_STALE",
        "CROSS_ENTRYPOINT_INVENTORY_INCOMPLETE",
    ),
    "oabh-ruleset": ("DEFAULT_BRANCH_NOT_INCLUDED", "~DEFAULT_BRANCH"),
    "oabh-drift": (
        "GATEWAY_BIND_ONLY_LOCAL_COMMITS",
        "GATEWAY_BEHIND_MAIN",
        "touched_paths_outside_tasks",
    ),
    "oabh-redact": ("HFTOKEN_", "NPMTOKEN_", "github_pat_", "redis://:p@ss@host", "keepme"),
    "oabh-intent": ("rebuild_index", "create_cache", "repair additional validation"),
}


@dataclass
class TaskMaterial:
    task_id: str
    visible_test: str
    hidden_test: str
    source: str = ""


@dataclass
class TaskAudit:
    key: str
    task_id: str
    bare_calls: int = 0
    with_nexus_calls: int = 0
    hidden_hits: list[str] = field(default_factory=list)
    extra_lines: list[str] = field(default_factory=list)
    visible_test_present: bool = False
    prior_art_present: bool = False
    violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "task_id": self.task_id,
            "bare_calls": self.bare_calls,
            "with_nexus_calls": self.with_nexus_calls,
            "hidden_hits": self.hidden_hits,
            "extra_lines": self.extra_lines,
            "visible_test_present": self.visible_test_present,
            "prior_art_present": self.prior_art_present,
            "violations": self.violations,
        }


def _string_literals(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    return {
        node.value.strip()
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.strip()
    }


def hidden_only_literals(material: TaskMaterial) -> list[str]:
    """Inventory literals plus hidden-test string constants (>= 4 chars) absent from the visible test."""

    auto = {
        literal
        for literal in _string_literals(material.hidden_test)
        - _string_literals(material.visible_test)
        if len(literal) >= 4 and literal not in material.visible_test
    }
    return sorted({*HIDDEN_LITERALS.get(material.task_id, ()), *auto})


def _needles(literal: str, inventory: set[str]) -> tuple[str, ...]:
    """Inventory literals match as substrings; auto-extracted hidden-test constants match only in
    their quoted form, so a common word (e.g. ``token``) in Nexus text is not a false hit."""

    if literal in inventory:
        return (literal,)
    return (f"'{literal}'", f'"{literal}"')


def _lines(prompt: str) -> list[str]:
    return [" ".join(line.split()) for line in prompt.splitlines() if line.strip()]


def strip_no_tools(prompt: str) -> str:
    return prompt.replace(NO_TOOLS_PREFIX, "")


def extra_lines(with_nexus_prompt: str, bare_prompt: str) -> list[str]:
    bare = set(_lines(strip_no_tools(bare_prompt)))
    return [line for line in _lines(strip_no_tools(with_nexus_prompt)) if line not in bare]


def load_captures(capture_dir: str | Path) -> dict[tuple[str, str], list[dict[str, Any]]]:
    out: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    root = Path(capture_dir)
    if not root.is_dir():
        return out
    for path in sorted(root.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            out[(str(record.get("arm") or "unknown"), str(record.get("key") or "unknown"))].append(
                record
            )
    for records in out.values():
        records.sort(key=lambda item: float(item.get("ts") or 0.0))
    return out


def audit_task(
    key: str,
    material: TaskMaterial,
    bare_records: list[dict[str, Any]],
    with_records: list[dict[str, Any]],
) -> TaskAudit:
    result = TaskAudit(key=key, task_id=material.task_id)
    result.bare_calls = len(bare_records)
    result.with_nexus_calls = len(with_records)
    # No call in either arm (dry lane, no leasable account) leaves nothing to compare; a
    # with-Nexus prompt without its bare counterpart cannot be proven symmetric.
    if result.bare_calls > 1 or (result.bare_calls == 0 and result.with_nexus_calls > 0):
        result.violations.append(f"bare_calls={result.bare_calls}")
    if result.with_nexus_calls > 1:
        result.violations.append(f"with_nexus_calls={result.with_nexus_calls}")
    bare_prompt = str(bare_records[0].get("prompt") or "") if bare_records else ""
    literals = hidden_only_literals(material)
    inventory = set(HIDDEN_LITERALS.get(material.task_id, ()))
    for record in with_records:
        prompt = str(record.get("prompt") or "")
        for literal in literals:
            if literal in result.hidden_hits:
                continue
            if any(
                needle in prompt and needle not in bare_prompt
                for needle in _needles(literal, inventory)
            ):
                result.hidden_hits.append(literal)
        if PRIOR_ART_MARKER in prompt:
            result.prior_art_present = True
    if result.hidden_hits:
        result.violations.append("hidden_literal_in_with_nexus_prompt")
    if result.prior_art_present:
        result.violations.append("prior_art_in_with_nexus_prompt")
    if with_records:
        first = str(with_records[0].get("prompt") or "")
        visible = material.visible_test.strip()
        result.visible_test_present = bool(visible) and all(
            line in _lines(first) for line in _lines(visible)
        )
        if not result.visible_test_present:
            result.violations.append("visible_test_missing_from_with_nexus_prompt")
        if bare_records:
            result.extra_lines = extra_lines(first, bare_prompt)
            if result.extra_lines:
                result.violations.append("with_nexus_only_text")
    return result


def audit_run(
    capture_dir: str | Path,
    materials: Mapping[str, TaskMaterial],
    *,
    rows: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    captures = load_captures(capture_dir)
    tasks = [
        audit_task(
            key,
            material,
            captures.get(("without_nexus", key), []),
            captures.get(("with_nexus", key), []),
        )
        for key, material in sorted(materials.items())
    ]
    unknown = sorted(
        f"{arm}__{key}"
        for (arm, key) in captures
        if arm not in {"with_nexus", "without_nexus"} or key not in materials
    )
    row_violations: list[str] = []
    for row in rows:
        ident = f"{row.get('mode')}:{row.get('task_id')}#{row.get('trial_index')}"
        if str(row.get("route_cost_policy_source") or ""):
            row_violations.append(f"{ident}:promoted_route_cost_policy")
        if str(row.get("mode")) == "with_nexus" and int(row.get("attempt_count") or 0) > 1:
            row_violations.append(f"{ident}:attempt_count>1")
        if str(row.get("hidden_retry_reason") or "") in {
            "hidden_verifier_failure_deterministic_pre_retry",
            "hidden_verifier_failure_bounded_nexus_retry",
        }:
            row_violations.append(f"{ident}:hidden_feedback")
    failed = [item for item in tasks if item.violations]
    status = "PASS" if not failed and not unknown and not row_violations else "FAIL"
    return {
        "schema": SCHEMA,
        "status": status,
        "tasks": [item.to_dict() for item in tasks],
        "failed_keys": [item.key for item in failed],
        "unattributed_captures": unknown,
        "row_violations": row_violations,
    }
