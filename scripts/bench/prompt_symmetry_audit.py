"""Captured-prompt symmetry audit for the counted like-for-like A/B (online A/B S21).

Replaces the old ``_prompt_leak_audit_failures`` (which skipped hard_v1, exempted status
enums, and never looked at the prompts actually sent).  Input: the per-call records that
``scripts/bench/agy_prompt_capture.py`` wrote into THIS run's private capture dir for both arms,
the run's rows, and each task's fixture material.

Per task x trial the audit requires (any miss -> the counted metric is invalid):
  (b) both arms have a row, each arm sent at most one distinct prompt (an identical prompt re-sent
      after a pre-effect quota rotation counts once), every row that reports a provider call has
      a captured prompt, and a with-Nexus prompt always has its bare counterpart;
  (d) no hidden-only literal, hidden-only test line or hidden-only word reaches the with-Nexus
      prompt (text is NFKC-normalised, zero-width characters removed, JSON strings decoded, and
      matched case-insensitively);
  (e) the with-Nexus prompt contains the visible test and no ``[Prior Art]``; the no-tools prefix
      appears exactly once in both prompts, at the top of the bare prompt and before ``[TASK]``;
  (f) every with-Nexus-only line is one of the allowlisted Nexus blocks (2026-10-14 decision: the
      wrapper blocks ARE the treatment) and their bodies pass the block checks.
"""

from __future__ import annotations

import ast
import json
import os
import re
import stat
import unicodedata
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA = "nexus_bench_prompt_symmetry_audit_v2"
NO_TOOLS_PREFIX = "Do not use any tools (no commands, no file reads, no file writes). Answer directly in this reply."
PRIOR_ART_MARKER = "[Prior Art]"

# Allowed with-Nexus-only content (coordinator decision 2026-10-14).
NEXUS_PREAMBLE = (
    "You are an agent wearing Nexus. Use the Nexus route, CodeIntel, governance, and artifact "
    "constraints below. Stay within the task scope."
)
SESSION_BOUNDARY_RE = re.compile(
    r"^NEXUS_SESSION_BOUNDARY_V1 task_id=[A-Za-z0-9_.:-]+ task_type=[A-Za-z0-9_.:-]+ "
    r"Treat this as an isolated task\. Do not use facts from prior turns\.$"
)
TASK_HEADER = "[TASK]"
TASK_SCAFFOLDING = frozenset({
    "Return JSON. Prefer patch=<full updated target file>. If patch is not used, use "
    "operation=replace with exact target_snippet and replacement.",
    "Hint: baseline",
    "Source:",
    "Tests:",
})
HIDDEN_GUIDANCE_HEADER = "[NEXUS HIDDEN-VERIFIER GUIDANCE]"
CODEINTEL_HEADER = "[NEXUS CODEINTEL SUMMARY]"
PAYLOAD_HEADER = "[PAYLOAD]"
JSON_BLOCK_HEADERS = frozenset({
    "[NEXUS ROUTE SUMMARY]",
    CODEINTEL_HEADER,
    "[NEXUS EXECUTION PROFILE]",
    "[NEXUS EXECUTOR FLAGS]",
    "[NEXUS CAPABILITY EVIDENCE]",
    "[NEXUS MODEL CONTEXT]",
})
NEXUS_BLOCK_HEADERS = JSON_BLOCK_HEADERS | {HIDDEN_GUIDANCE_HEADER, PAYLOAD_HEADER}
# Any bracketed all-caps line starts a new section (also the bare template's [CURRENT SOURCE] etc.).
SECTION_HEADER_RE = re.compile(r"^\[[A-Z0-9][A-Z0-9 _/-]*\]$")
MAX_JSON_STRING_CHARS = 120
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿­"), None)
_WORD_RE = re.compile(r"[a-z_][a-z0-9_]{2,}")
# A line that looks like Python source/test code (after normalisation).
_CODE_LINE_RE = re.compile(
    r"^(?:async def |def |class |import |from \S+ import |return\b|raise\b|assert\b|yield\b|"
    r"while\b.*:$|with\b.*:$|try:$|except\b.*:$|finally:$|elif\b.*:$|else:$|if\b.*:$|for\b.*:$|"
    r"lambda\b|@[a-z_][\w.]*|[a-z_][\w.\[\]'\"]*\s*(?:[+\-*/%|&^]?=)(?!=)|[a-z_][\w.]*\(.*\)$)"
)

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


class CaptureError(RuntimeError):
    """A capture file is unreadable, not a regular file, or from another run."""


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
    bare_resends: int = 0
    with_nexus_resends: int = 0
    hidden_hits: list[str] = field(default_factory=list)
    hidden_line_hits: list[str] = field(default_factory=list)
    extra_lines: list[str] = field(default_factory=list)
    visible_test_present: bool = False
    prior_art_present: bool = False
    disallowed_lines: list[str] = field(default_factory=list)
    code_lines: list[str] = field(default_factory=list)
    codeintel_findings: list[str] = field(default_factory=list)
    hidden_guidance_lines: list[str] = field(default_factory=list)
    json_string_findings: list[str] = field(default_factory=list)
    with_nexus_prompt_chars: int = 0
    bare_prompt_chars: int = 0
    violations: list[str] = field(default_factory=list)

    @property
    def extra_chars(self) -> int:
        return sum(len(line) for line in self.extra_lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "task_id": self.task_id,
            "bare_calls": self.bare_calls,
            "with_nexus_calls": self.with_nexus_calls,
            "bare_account_rotations": self.bare_resends,
            "with_nexus_account_rotations": self.with_nexus_resends,
            "hidden_hits": self.hidden_hits,
            "hidden_line_hits": self.hidden_line_hits,
            "extra_lines": self.extra_lines,
            "visible_test_present": self.visible_test_present,
            "prior_art_present": self.prior_art_present,
            "disallowed_lines": self.disallowed_lines,
            "code_lines": self.code_lines,
            "codeintel_findings": self.codeintel_findings,
            "hidden_guidance_lines": self.hidden_guidance_lines,
            "json_string_findings": self.json_string_findings,
            "with_nexus_prompt_chars": self.with_nexus_prompt_chars,
            "bare_prompt_chars": self.bare_prompt_chars,
            "nexus_prompt_extra_lines": len(self.extra_lines),
            "nexus_prompt_extra_chars": self.extra_chars,
            "violations": self.violations,
        }


def normalize(text: str) -> str:
    """NFKC, zero-width characters removed, whitespace collapsed, case-folded."""

    return " ".join(
        unicodedata.normalize("NFKC", str(text)).translate(_ZERO_WIDTH).split()
    ).casefold()


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


def hidden_only_lines(material: TaskMaterial) -> list[str]:
    visible = {normalize(line) for line in material.visible_test.splitlines()}
    return sorted({
        normalize(line)
        for line in material.hidden_test.splitlines()
        if len(normalize(line)) >= 8 and normalize(line) not in visible
    })


def hidden_only_words(material: TaskMaterial, bare_prompt: str) -> set[str]:
    """Word-level hidden-only vocabulary: in the hidden test, not in anything the bare arm saw."""

    seen = set(
        _WORD_RE.findall(normalize(" ".join([material.visible_test, material.source, bare_prompt])))
    )
    return set(_WORD_RE.findall(normalize(material.hidden_test))) - seen


def _needles(literal: str, inventory: set[str]) -> tuple[str, ...]:
    """Inventory literals match as substrings; auto-extracted hidden-test constants match only in
    their quoted form, so a common word (e.g. ``token``) in Nexus text is not a false hit."""

    if literal in inventory:
        return (normalize(literal),)
    return (normalize(f"'{literal}'"), normalize(f'"{literal}"'))


def _lines(prompt: str) -> list[str]:
    return [" ".join(line.split()) for line in prompt.splitlines() if line.strip()]


def strip_no_tools(prompt: str) -> str:
    return prompt.replace(NO_TOOLS_PREFIX, "")


def extra_lines(with_nexus_prompt: str, bare_prompt: str) -> list[str]:
    bare = set(_lines(strip_no_tools(bare_prompt)))
    return [line for line in _lines(strip_no_tools(with_nexus_prompt)) if line not in bare]


def _json_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key)
            yield from _json_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _json_strings(item)


def _decoded_corpus(prompt: str) -> str:
    """Normalised prompt plus every decoded JSON string value (quoted) found on JSON lines."""

    parts = [normalize(prompt)]
    for line in prompt.splitlines():
        stripped = line.strip()
        if not stripped.startswith(("{", "[")):
            continue
        try:
            payload = json.loads(stripped)
        except ValueError:
            continue
        parts.extend(normalize(f'"{text}"') for text in _json_strings(payload))
    return "\n".join(parts)


def _blocks(prompt: str) -> list[tuple[str, str]]:
    """(current section header or "", normalized line) for every non-empty prompt line.

    Every bracketed all-caps line ends the previous block, so text after the Nexus blocks
    (e.g. ``[CURRENT SOURCE]`` / ``[VISIBLE TESTS]``) is never attributed to them.
    """

    header = ""
    out: list[tuple[str, str]] = []
    for line in _lines(strip_no_tools(prompt)):
        if SECTION_HEADER_RE.match(line):
            header = line
        out.append((header, line))
    return out


def _code_like(fragment: str) -> bool:
    return bool(_CODE_LINE_RE.match(normalize(fragment)))


def _codeintel_findings(body: str) -> list[str]:
    try:
        payload = json.loads(body)
    except ValueError:
        return [f"unparsable:{body[:80]}"]
    if not isinstance(payload, dict):
        return [f"not_object:{body[:80]}"]
    findings: list[str] = []
    for key in ("impacted_files_count", "impacted_symbols_count"):
        value = payload.get(key)
        try:
            count = int(value or 0)
        except (TypeError, ValueError):
            findings.append(f"{key}=non_integer:{value!r}")
            continue
        if count != 0:
            findings.append(f"{key}={value}")
    for key, value in payload.items():
        if (key.endswith("_path") or key.endswith("_paths")) and value:
            findings.append(f"{key}={value}")
        if key.endswith("_report_present") and value:
            findings.append(f"{key}=true")
    return findings


def classify_extra_lines(
    with_nexus_prompt: str, bare_prompt: str, material: TaskMaterial
) -> dict[str, list[str]]:
    """Split the with-Nexus-only lines into allowed / disallowed and run the block-body checks."""

    bare = set(_lines(strip_no_tools(bare_prompt)))
    fixture_lines = {
        normalize(line)
        for line in [*material.source.splitlines(), *material.visible_test.splitlines()]
    }
    hidden_words = hidden_only_words(material, bare_prompt)
    out: dict[str, list[str]] = {
        "disallowed": [],
        "code": [],
        "codeintel": [],
        "guidance": [],
        "json": [],
    }
    preamble = " ".join(NEXUS_PREAMBLE.split())
    for header, line in _blocks(with_nexus_prompt):
        is_header = bool(SECTION_HEADER_RE.match(line))
        if header == HIDDEN_GUIDANCE_HEADER and not is_header:
            out["guidance"].append(line)  # must be empty under strict, even if bare had the line
        if line in bare:
            continue
        if is_header:
            if line != TASK_HEADER and line not in NEXUS_BLOCK_HEADERS:
                out["disallowed"].append(line)
            continue
        if line == preamble or SESSION_BOUNDARY_RE.match(line):
            continue
        if header == TASK_HEADER:
            if line not in TASK_SCAFFOLDING:
                out["disallowed"].append(line)  # task text/source/tests must match the bare prompt
            continue
        if header not in JSON_BLOCK_HEADERS:
            # Unknown section, prose before any header, [PAYLOAD] text, guidance text: not allowed.
            out["disallowed"].append(line)
            continue
        try:
            payload = json.loads(line)
        except ValueError:
            out["disallowed"].append(line)  # allowed blocks carry JSON only
            continue
        for text in _json_strings(payload):
            if len(text) > MAX_JSON_STRING_CHARS:
                out["json"].append(
                    f"{header}: string longer than {MAX_JSON_STRING_CHARS} chars: {text[:60]}"
                )
            words = set(_WORD_RE.findall(normalize(text))) & hidden_words
            if words:
                out["json"].append(f"{header}: hidden-only words {sorted(words)}")
            for fragment in text.splitlines():
                if (
                    fragment.strip()
                    and _code_like(fragment)
                    and normalize(fragment) not in fixture_lines
                ):
                    out["code"].append(" ".join(fragment.split()))
        if header == CODEINTEL_HEADER:
            out["codeintel"].extend(_codeintel_findings(line))
    return out


def _distinct(records: list[dict[str, Any]]) -> tuple[int, int]:
    """(distinct prompts, re-sends of an identical prompt, i.e. pre-effect account rotations)."""

    shas = [
        str(item.get("prompt_sha256") or normalize(str(item.get("prompt") or "")))
        for item in records
    ]
    return len(set(shas)), len(shas) - len(set(shas))


def _no_tools_position_ok(prompt: str, *, bare: bool) -> bool:
    if prompt.count(NO_TOOLS_PREFIX) != 1:
        return False
    index = prompt.index(NO_TOOLS_PREFIX)
    if bare:
        return prompt.lstrip().startswith(NO_TOOLS_PREFIX)
    task_at = prompt.find(TASK_HEADER)
    return task_at == -1 or index < task_at


def audit_task(
    key: str,
    material: TaskMaterial,
    bare_records: list[dict[str, Any]],
    with_records: list[dict[str, Any]],
    *,
    bare_rows: list[Mapping[str, Any]] | None = None,
    with_rows: list[Mapping[str, Any]] | None = None,
) -> TaskAudit:
    result = TaskAudit(key=key, task_id=material.task_id)
    result.bare_calls, result.bare_resends = _distinct(bare_records)
    result.with_nexus_calls, result.with_nexus_resends = _distinct(with_records)
    if bare_rows is not None and with_rows is not None and len(bare_rows) != len(with_rows):
        result.violations.append(f"unpaired_rows:bare={len(bare_rows)},with_nexus={len(with_rows)}")
    for arm, rows, calls in (
        ("bare", bare_rows, result.bare_calls),
        ("with_nexus", with_rows, result.with_nexus_calls),
    ):
        if rows and calls == 0 and any(int(row.get("model_calls") or 0) > 0 for row in rows):
            result.violations.append(f"{arm}_model_call_not_captured")
    if result.bare_calls > 1:
        result.violations.append(f"bare_calls={result.bare_calls}")
    if result.bare_calls == 0 and result.with_nexus_calls > 0:
        result.violations.append("bare_calls=0")
    if result.with_nexus_calls > 1:
        result.violations.append(f"with_nexus_calls={result.with_nexus_calls}")
    bare_prompt = str(bare_records[0].get("prompt") or "") if bare_records else ""
    bare_corpus = _decoded_corpus(bare_prompt)
    literals = hidden_only_literals(material)
    inventory = set(HIDDEN_LITERALS.get(material.task_id, ()))
    hidden_lines = hidden_only_lines(material)
    for record in with_records:
        prompt = str(record.get("prompt") or "")
        corpus = _decoded_corpus(prompt)
        for literal in literals:
            if literal in result.hidden_hits:
                continue
            if any(
                needle in corpus and needle not in bare_corpus
                for needle in _needles(literal, inventory)
            ):
                result.hidden_hits.append(literal)
        for line in hidden_lines:
            if line in corpus and line not in bare_corpus and line not in result.hidden_line_hits:
                result.hidden_line_hits.append(line)
        if normalize(PRIOR_ART_MARKER) in corpus:
            result.prior_art_present = True
    if result.hidden_hits:
        result.violations.append("hidden_literal_in_with_nexus_prompt")
    if result.hidden_line_hits:
        result.violations.append("hidden_test_line_in_with_nexus_prompt")
    if result.prior_art_present:
        result.violations.append("prior_art_in_with_nexus_prompt")
    if bare_records and not _no_tools_position_ok(bare_prompt, bare=True):
        result.violations.append("bare_no_tools_prefix_not_once_at_top")
    if with_records:
        first = str(with_records[0].get("prompt") or "")
        if not _no_tools_position_ok(first, bare=False):
            result.violations.append("with_nexus_no_tools_prefix_not_once_before_task")
        visible = material.visible_test.strip()
        first_lines = set(_lines(first))
        result.visible_test_present = bool(visible) and all(
            line in first_lines for line in _lines(visible)
        )
        if not result.visible_test_present:
            result.violations.append("visible_test_missing_from_with_nexus_prompt")
        result.with_nexus_prompt_chars = len(first)
        result.bare_prompt_chars = len(bare_prompt)
        if bare_records:
            result.extra_lines = extra_lines(first, bare_prompt)
            checks = classify_extra_lines(first, bare_prompt, material)
            result.disallowed_lines = checks["disallowed"]
            result.code_lines = checks["code"]
            result.codeintel_findings = checks["codeintel"]
            result.hidden_guidance_lines = checks["guidance"]
            result.json_string_findings = checks["json"]
            if result.disallowed_lines:
                result.violations.append("with_nexus_only_text")
            if result.code_lines:
                result.violations.append("source_code_in_nexus_block")
            if result.codeintel_findings:
                result.violations.append("codeintel_reports_repo_context")
            if result.hidden_guidance_lines:
                result.violations.append("hidden_verifier_guidance_not_empty")
            if result.json_string_findings:
                result.violations.append("nexus_block_string_not_allowed")
    return result


def load_captures(
    capture_dir: str | Path, *, run_id: str | None = None
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """Read this run's capture files; refuse symlinks/non-regular files and foreign run ids."""

    out: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    root = Path(capture_dir)
    if not root.exists():
        return out
    info = os.lstat(root)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise CaptureError(f"capture dir is not a real directory: {root}")
    for path in sorted(root.iterdir()):
        info = os.lstat(path)
        if not stat.S_ISREG(info.st_mode):
            raise CaptureError(f"capture entry is not a regular file: {path.name}")
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise CaptureError(f"corrupt capture file {path.name}: {exc}") from exc
        if not isinstance(record, dict):
            raise CaptureError(f"capture file {path.name} is not an object")
        if run_id is not None and str(record.get("run_id") or "") != run_id:
            raise CaptureError(f"capture file {path.name} belongs to run {record.get('run_id')!r}")
        out[(str(record.get("arm") or "unknown"), str(record.get("key") or "unknown"))].append(
            record
        )
    for records in out.values():
        records.sort(key=lambda item: float(item.get("ts") or 0.0))
    return out


def _row_key(row: Mapping[str, Any]) -> str:
    return f"{row.get('task_id')}__{row.get('trial_index')}"


def audit_run(
    capture_dir: str | Path,
    materials: Mapping[str, TaskMaterial],
    *,
    rows: Iterable[Mapping[str, Any]] = (),
    run_id: str | None = None,
    expect_model_calls: bool = False,
) -> dict[str, Any]:
    captures = load_captures(capture_dir, run_id=run_id)
    rows = list(rows)
    by_arm: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_arm[(str(row.get("mode")), _row_key(row))].append(row)
    tasks = []
    for key, material in sorted(materials.items()):
        tasks.append(
            audit_task(
                key,
                material,
                captures.get(("without_nexus", key), []),
                captures.get(("with_nexus", key), []),
                bare_rows=by_arm.get(("without_nexus", key), []) if rows else None,
                with_rows=by_arm.get(("with_nexus", key), []) if rows else None,
            )
        )
    unknown = sorted(
        f"{arm}__{key}"
        for (arm, key) in captures
        if arm not in {"with_nexus", "without_nexus"} or key not in materials
    )
    row_violations: list[str] = []
    for row in rows:
        ident = f"{row.get('mode')}:{row.get('task_id')}#{row.get('trial_index')}"
        if _row_key(row) not in materials:
            row_violations.append(f"{ident}:no_fixture_material")
        if str(row.get("route_cost_policy_source") or ""):
            row_violations.append(f"{ident}:promoted_route_cost_policy")
        if str(row.get("mode")) == "with_nexus" and int(row.get("attempt_count") or 0) > 1:
            row_violations.append(f"{ident}:attempt_count>1")
        if str(row.get("hidden_retry_reason") or "") in {
            "hidden_verifier_failure_deterministic_pre_retry",
            "hidden_verifier_failure_bounded_nexus_retry",
        }:
            row_violations.append(f"{ident}:hidden_feedback")
    run_violations: list[str] = []
    if expect_model_calls:
        for arm in ("with_nexus", "without_nexus"):
            arm_rows = [row for row in rows if str(row.get("mode")) == arm]
            arm_captures = sum(len(records) for (a, _k), records in captures.items() if a == arm)
            if arm_rows and arm_captures == 0:
                run_violations.append(f"{arm}:no_model_call_observed")
    failed = [item for item in tasks if item.violations]
    status = (
        "PASS"
        if not failed and not unknown and not row_violations and not run_violations
        else "FAIL"
    )
    return {
        "schema": SCHEMA,
        "status": status,
        "run_id": run_id,
        "tasks": [item.to_dict() for item in tasks],
        "failed_keys": [item.key for item in failed],
        "unattributed_captures": unknown,
        "row_violations": row_violations,
        "run_violations": run_violations,
    }
