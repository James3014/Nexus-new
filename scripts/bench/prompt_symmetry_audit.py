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

Treatment lane (``lane="treatment"``, wiring plan PR-3): the with-Nexus arm may send 1..N prompts
per row (N = the row's ``treatment_max_model_calls``) and the captured count must equal the row's
``model_calls``; the bare arm still sends exactly one. Round 1 gets every strict check above (only
the four config numbers listed under ``treatment_blocks.widen`` in the schema may differ). Every
later round is audited on its own (``audit_treatment_round``): the no-tools prefix once before
``[TASK]``, no hidden literal or hidden test line, no ``[Prior Art]``, no local support candidate,
and each line that is in neither the round-1 prompt nor the bare prompt must be a fixed retry
sentence/header, a line of an earlier model candidate of the same row (bytes from the row's
candidate archive, sha256 in the row's ``model_candidate_sha256s``), a line of the runner's own
visible-test run on such a candidate, a short product error code, or a schema-valid Nexus block.
"""

from __future__ import annotations

import ast
import base64
import binascii
import codecs
import hashlib
import html
import json
import os
import re
import stat
import unicodedata
import urllib.parse
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
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"), None)
_WORD_RE = re.compile(r"[a-z_][a-z0-9_]{2,}")
# A line that looks like Python source/test code (after normalisation).
_CODE_LINE_RE = re.compile(
    r"^(?:async def |def |class |import |from \S+ import |return\b|raise\b|assert\b|yield\b|"
    r"while\b.*:|with\b.*:|try:|except\b.*:|finally:|elif\b.*:|else:|if\b.*:|for\b.*:|"
    r"lambda\b|@[a-z_][\w.]*|[a-z_][\w.\[\]'\"]*\s*(?:[+\-*/%|&^]?=)(?!=)|[a-z_][\w.]*\(.*\)$)"
)
# A token that may hide text in base64/hex (decoded and re-checked when it decodes to text).
_ENCODED_TOKEN_RE = re.compile(r"^[A-Za-z0-9+/=_-]{8,}$")
_SCHEMA_PATH = Path(__file__).with_name("prompt_symmetry_schema.json")
# Exact fixed Nexus sentences allowed in JSON blocks regardless of length/vocabulary checks. Each
# one is checked by a test to contain no hidden-only word of ANY fixture; nothing is inferred.
TEMPLATE_STRINGS: frozenset[str] = frozenset({
    # [NEXUS MODEL CONTEXT] claim_boundary (nexus-runtime context assembly, fixed text).
    "CapabilityPlanner remains the selection authority; source reduction is a subordinate projection.",
    "Context assembly materializes already-selected context under budget only.",
    "Serialization does not prove physical provider consumption or outcome contribution.",
    "Source identities and claim ceilings are preserved, not strengthened by this package.",
    "The semantic package hash is consumer-neutral; consumer and worker binding use a separate "
    "deterministic projection.",
})

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


LANE_STRICT = "strict"
LANE_TREATMENT = "treatment"
DEFAULT_TREATMENT_MAX_MODEL_CALLS = 4
LOCAL_SUPPORT_HEADER = "[NEXUS LOCAL SUPPORT CANDIDATE]"
SELF_HEAL_SENTENCE = (
    "Previous candidate failed verification. Repair the candidate using the failure evidence below."
)
# Short product error codes a failed visible evaluation can carry instead of pytest output
# (sprint_service CandidateEval.error); detail is bounded and still goes through the hidden grep.
# Exact product error codes a failed visible evaluation can carry instead of pytest output
# (sprint_service CandidateEval.error / _semantic_guard). Nothing else, no free-text detail.
PRODUCT_ERROR_CODES = frozenset({
    "broker_timeout",
    "no_change_candidate",
    "pytest_failed",
    "test_timeout",
    "semantic_guard_placeholder_only",
    "semantic_guard_zero_delta",
    "semantic_guard_low_delta_feature",
    "semantic_guard_syntax_warning",
    "file_lock_denied",
    "confinement_unavailable:no_visible_test",
})
# The confined visible evaluation's refusal for companion edits (#2211 sprint_service).
_MULTI_FILE_RE = re.compile(r"^confinement_unavailable:multi_file:[0-9]{1,3}$")
# Volatile parts of pytest output that differ between two runs of the same test.
_DURATION_RE = re.compile(r"\bin [0-9]+(?:\.[0-9]+)?s\b")


class CaptureError(RuntimeError):
    """A capture file is unreadable, not a regular file, or from another run."""


@dataclass
class TaskMaterial:
    task_id: str
    visible_test: str
    hidden_test: str
    source: str = ""
    task_desc: str = ""
    error: str = ""


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
    lane: str = LANE_STRICT
    treatment_literal_hits: list[str] = field(default_factory=list)
    row_void: bool = False
    treatment_round_findings_deferred: bool = False
    treatment_rounds_audited: int = 0
    self_heal_rounds_observed: int = 0
    treatment_round_findings: list[str] = field(default_factory=list)

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
            "lane": self.lane,
            "treatment_literal_hits": self.treatment_literal_hits,
            "row_void": self.row_void,
            "treatment_round_findings_deferred": self.treatment_round_findings_deferred,
            "treatment_rounds_audited": self.treatment_rounds_audited,
            "self_heal_rounds_observed": self.self_heal_rounds_observed,
            "treatment_round_findings": self.treatment_round_findings,
        }


# Cyrillic/Greek look-alikes mapped to their ASCII skeleton before any matching.
_CONFUSABLES = str.maketrans({
    "\u0430": "a",
    "\u0435": "e",
    "\u043e": "o",
    "\u0440": "p",
    "\u0441": "c",
    "\u0443": "y",
    "\u0445": "x",
    "\u0455": "s",
    "\u0456": "i",
    "\u0458": "j",
    "\u04bb": "h",
    "\u0501": "d",
    "\u0410": "A",
    "\u0412": "B",
    "\u0415": "E",
    "\u041a": "K",
    "\u041c": "M",
    "\u041d": "H",
    "\u041e": "O",
    "\u0420": "P",
    "\u0421": "C",
    "\u0422": "T",
    "\u0425": "X",
    "\u0405": "S",
    "\u0406": "I",
    "\u0408": "J",
    "\u03b1": "a",
    "\u03bf": "o",
    "\u03c1": "p",
    "\u03b5": "e",
    "\u03ba": "k",
    "\u03bd": "v",
    "\u03c4": "t",
    "\u03c5": "u",
    "\u03c7": "x",
    "\u0391": "A",
    "\u0392": "B",
    "\u0395": "E",
    "\u0396": "Z",
    "\u0397": "H",
    "\u0399": "I",
    "\u039a": "K",
    "\u039c": "M",
    "\u039d": "N",
    "\u039f": "O",
    "\u03a1": "P",
    "\u03a4": "T",
    "\u03a5": "Y",
    "\u03a7": "X",
})


def normalize(text: str) -> str:
    """NFKC, confusables to ASCII skeleton, zero-width removed, whitespace collapsed, case-folded."""

    folded = unicodedata.normalize("NFKC", str(text)).translate(_ZERO_WIDTH).translate(_CONFUSABLES)
    return " ".join(folded.split()).casefold()


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
        if ("file" in key or "symbol" in key) and isinstance(value, (list, str)) and value:
            findings.append(f"{key}={str(value)[:60]}")
        if (key.endswith("_path") or key.endswith("_paths")) and value:
            findings.append(f"{key}={value}")
        if key.endswith("_report_present") and value:
            findings.append(f"{key}=true")
    return findings


def load_block_schema(lane: str = LANE_STRICT) -> dict[str, dict[str, dict[str, Any]]]:
    """Block schema; the treatment lane widens only the paths listed in ``treatment_blocks.widen``."""

    data = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    blocks = data["blocks"]
    if lane != LANE_TREATMENT:
        return blocks
    treatment = data.get("treatment_blocks") or {}
    round_id = treatment.get("round_id_pattern") or {}
    extra = dict(treatment.get("extra_capabilities") or {})
    widened: dict[str, dict[str, dict[str, Any]]] = {}
    for header, paths in blocks.items():
        widened[header] = {}
        for path, spec in paths.items():
            patterns = list(spec.get("patterns") or [])
            if patterns:
                if round_id.get("from"):
                    patterns = [item.replace(round_id["from"], round_id["to"]) for item in patterns]
                for name, template in extra.items():
                    patterns += [
                        item.replace(template, name) for item in patterns if template in item
                    ]
                spec = {**spec, "patterns": list(dict.fromkeys(patterns))}
            widened[header][path] = spec
    for header, paths in (treatment.get("widen") or {}).items():
        for path, override in paths.items():
            base = widened.get(header, {}).get(path)
            if base is None:
                raise ValueError(f"treatment_blocks widens an unknown path: {header} {path}")
            merged = {**base, **override}
            merged.pop("enum" if "patterns" in override else "patterns", None)
            widened[header][path] = merged
    return widened


def load_treatment_blocks() -> dict[str, Any]:
    return dict(json.loads(_SCHEMA_PATH.read_text(encoding="utf-8")).get("treatment_blocks") or {})


class DuplicateKeyError(ValueError):
    """A JSON object repeats a key (after normalisation); earlier values would be hidden."""


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for key, value in pairs:
        normalized = normalize(key)
        if normalized in {normalize(existing) for existing in seen}:
            raise DuplicateKeyError(f"duplicate key {key!r}")
        seen[key] = value
    return seen


def parse_block_json(line: str) -> Any:
    return json.loads(line, object_pairs_hook=_no_duplicate_keys)


def _decode_once(text: str) -> list[str]:
    out: list[str] = []
    for decoder in (html.unescape, urllib.parse.unquote):
        decoded = decoder(text)
        if decoded != text:
            out.append(decoded)
    if "\\" in text:
        try:
            decoded = codecs.decode(text, "unicode_escape")
        except (UnicodeDecodeError, ValueError):
            decoded = text
        if decoded != text:
            out.append(decoded)
    token = text.strip()
    if _ENCODED_TOKEN_RE.match(token):
        candidates: list[bytes] = []
        if re.fullmatch(r"[0-9a-fA-F]+", token) and len(token) % 2 == 0:
            try:
                candidates.append(binascii.unhexlify(token))
            except binascii.Error:
                pass
        for altchars in (None, b"-_"):
            try:
                padded = token + "=" * (-len(token) % 4)
                candidates.append(base64.b64decode(padded, altchars=altchars, validate=True))
            except (binascii.Error, ValueError):
                pass
        for raw in candidates:
            try:
                decoded = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            printable = sum(1 for ch in decoded if ch.isprintable() or ch in "\n\t")
            if len(decoded) >= 4 and printable / len(decoded) >= 0.9:
                out.append(decoded)
    return out


def _decoded_variants(text: str, *, max_layers: int = 5) -> list[str]:
    """All layers of HTML / %NN / escape / base64 / hex decoding, iterated to a fixed point (<= 5)."""

    layers: list[str] = []
    frontier = [text]
    seen = {text}
    for _ in range(max_layers):
        next_frontier: list[str] = []
        for item in frontier:
            for decoded in _decode_once(item):
                if decoded not in seen:
                    seen.add(decoded)
                    layers.append(decoded)
                    next_frontier.append(decoded)
        if not next_frontier:
            break
        frontier = next_frontier
    return layers


def _walk_json(value: Any, path: str = "") -> Iterator[tuple[str, Any]]:
    """(schema path, value) for EVERY node (objects, lists, leaves); list elements use ``path[]``."""

    yield path, value
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield from _walk_json(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list):
        for item in value:
            yield from _walk_json(item, f"{path}[]")


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "str"
    return type(value).__name__


_MARKER_RE = re.compile(r"^[a-z_]+:(result|payload|finding)$")
_ISO8601_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:\d{2}|Z)?$")
_ABS_PATH_RE = re.compile(r"^/[A-Za-z0-9_./-]+$")


_REGISTERED_CAPABILITIES: frozenset[str] | None = None


def registered_capability_ids() -> frozenset[str]:
    """Capability ids of the executor registry (fail closed to empty if it cannot be imported)."""

    global _REGISTERED_CAPABILITIES
    if _REGISTERED_CAPABILITIES is None:
        try:
            from nexus.core.capability_executor_registry import EXECUTOR_REGISTRY
        except Exception:  # noqa: BLE001
            _REGISTERED_CAPABILITIES = frozenset()
        else:
            _REGISTERED_CAPABILITIES = frozenset(str(key) for key in EXECUTOR_REGISTRY)
    return _REGISTERED_CAPABILITIES


def _numeric_literals(source: str) -> set[float]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    return {
        float(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    }


def hidden_only_numbers(material: TaskMaterial, bare_prompt: str) -> set[float]:
    """Numbers in the hidden test that the bare arm never saw (0 and 1 excluded)."""

    seen = _numeric_literals(material.visible_test) | _numeric_literals(material.source)
    seen |= {float(match) for match in re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])", bare_prompt)}
    return {
        value for value in _numeric_literals(material.hidden_test) - seen if value not in (0.0, 1.0)
    }


def _round_task_text_ok(value: str, task_desc: str, round_lines: frozenset[str]) -> bool:
    """A later treatment round's task text (task_desc + the self-heal block) echoed in a Nexus
    block: it must start with the task description and every further line must be a line of
    the same prompt (audited there line by line); the last line may be cut (a capped echo)."""

    if not task_desc or not value.startswith(task_desc):
        return False
    rest = [" ".join(line.split()) for line in value[len(task_desc) :].splitlines()]
    rest = [line for line in rest if line]
    for index, line in enumerate(rest):
        if line in round_lines:
            continue
        if index == len(rest) - 1 and any(item.startswith(line) for item in round_lines):
            continue
        return False
    return True


def _format_ok(
    fmt: str,
    value: str,
    material: TaskMaterial,
    selected: frozenset[str] = frozenset(),
    round_lines: frozenset[str] | None = None,
) -> bool:
    if fmt == "task_desc":
        return value == material.task_desc or (
            round_lines is not None and _round_task_text_ok(value, material.task_desc, round_lines)
        )
    if fmt == "task_desc_prefix":
        return bool(value) and material.task_desc.startswith(value)
    if fmt == "template":
        return value in TEMPLATE_STRINGS
    if fmt == "marker":
        # capability:(result|payload|finding), capability registered AND selected in this prompt.
        match = _MARKER_RE.match(value)
        capability = value.split(":", 1)[0]
        return bool(match) and capability in registered_capability_ids() and capability in selected
    if fmt == "iso8601":
        return bool(_ISO8601_RE.match(value))
    if fmt == "abs_path":
        return bool(_ABS_PATH_RE.match(value))
    return False


def _schema_findings(
    header: str,
    payload: Any,
    schema: Mapping[str, Mapping[str, Any]],
    material: TaskMaterial,
    *,
    selected: frozenset[str] = frozenset(),
    hidden_numbers: frozenset[float] = frozenset(),
    round_lines: frozenset[str] | None = None,
) -> list[str]:
    """Known paths only; kind, type, enum/range/pattern/format per path (schema v2)."""

    findings: list[str] = []
    if not isinstance(payload, Mapping):
        return [f"{header}: block body is not a JSON object"]
    for path, value in _walk_json(payload):
        spec = schema.get(path)
        if spec is None:
            findings.append(f"{header}: unknown path {path or '<root>'}")
            continue
        kind = spec.get("kind")
        if isinstance(value, Mapping):
            if kind != "object":
                findings.append(f"{header}: {path} must not be an object")
            continue
        if isinstance(value, list):
            if kind != "list":
                findings.append(f"{header}: {path} must not be a list")
            elif spec.get("items") == "empty" and value:
                findings.append(f"{header}: {path} must be empty")
            continue
        if kind != "leaf":
            findings.append(f"{header}: {path} must be a {kind}")
            continue
        actual = _type_name(value)
        types = set(spec.get("types") or [])
        if actual not in types and not (actual == "int" and "number" in types):
            findings.append(f"{header}: {path} must be {'|'.join(sorted(types))}, got {actual}")
            continue
        if isinstance(value, bool) or value is None:
            continue
        if isinstance(value, (int, float)):
            if "enum" in spec and value not in spec["enum"]:
                findings.append(f"{header}: {path} value {value} not in {spec['enum']}")
            if "range" in spec and not (spec["range"][0] <= value <= spec["range"][1]):
                findings.append(f"{header}: {path} value {value} outside {spec['range']}")
            if float(value) in hidden_numbers and value not in (spec.get("enum") or []):
                findings.append(f"{header}: {path} value {value} is a hidden-only number")
            continue
        if any(not ch.isascii() for ch in value if ch.isalpha()):
            findings.append(f"{header}: {path} has non-ASCII letters")
        if "format" in spec:
            if not _format_ok(str(spec["format"]), value, material, selected, round_lines):
                findings.append(f"{header}: {path} does not match bound format {spec['format']}")
        elif not any(re.match(pattern, value) for pattern in spec.get("patterns") or []):
            findings.append(
                f"{header}: {path} value not in its declared enum/pattern: {value[:60]!r}"
            )
    return findings


def _selected_capabilities(prompt: str) -> set[str]:
    """Capability ids this prompt's own route/evidence/model-context blocks say were selected."""

    out: set[str] = set()
    for header, line in _blocks(prompt):
        if header not in JSON_BLOCK_HEADERS or not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except ValueError:
            continue
        for path, value in _walk_json(payload):
            if path in {"selected_capabilities[]", "selected_capability_ids[]"} and isinstance(
                value, str
            ):
                out.add(value)
    return out


def classify_extra_lines(
    with_nexus_prompt: str,
    bare_prompt: str,
    material: TaskMaterial,
    *,
    lane: str = LANE_STRICT,
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
    schema = load_block_schema(lane)
    # Only exact, checked-in Nexus sentences, the task description verbatim, or a whole line of
    # the bare prompt are exempt from the length/vocabulary checks. Nothing is inferred.
    exempt = {normalize(text) for text in TEMPLATE_STRINGS}
    exempt |= {normalize(line) for line in bare_prompt.splitlines() if line.strip()}
    if material.task_desc.strip():
        exempt.add(normalize(material.task_desc))
    bare_corpus = _decoded_corpus(bare_prompt)
    hidden_lines = hidden_only_lines(material)
    hidden_numbers = frozenset(hidden_only_numbers(material, bare_prompt))
    selected = frozenset(_selected_capabilities(with_nexus_prompt))
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
            payload = parse_block_json(line)
        except DuplicateKeyError as exc:
            out["json"].append(f"{header}: {exc}")
            continue
        except ValueError:
            out["disallowed"].append(line)  # allowed blocks carry JSON only
            continue
        out["json"].extend(
            _schema_findings(
                header,
                payload,
                schema.get(header, {}),
                material,
                selected=selected,
                hidden_numbers=hidden_numbers,
            )
        )
        nodes = list(_walk_json(payload))
        # Literal/code/vocabulary checks also run on the JOINED text of every string list, so a
        # literal or code line split across items is still caught.
        joined = [
            (f"{path}<joined>", " ".join(item for item in value if isinstance(item, str)))
            for path, value in nodes
            if isinstance(value, list)
            and sum(isinstance(item, str) for item in value) > 1
            # a list made only of exempt items (template sentences, task text) carries nothing new
            and not all(normalize(item) in exempt for item in value if isinstance(item, str))
        ]
        for path, value in [*nodes, *joined]:
            if isinstance(value, (list, Mapping)):
                continue
            if header == CODEINTEL_HEADER and ("file" in path or "symbol" in path):
                if isinstance(value, str) and value:
                    out["codeintel"].append(f"{path}={value[:60]}")
            if not isinstance(value, str):
                continue
            texts = [value, *_decoded_variants(value)]
            if value.strip() and _ENCODED_TOKEN_RE.match(value.strip()) and len(texts) > 1:
                out["json"].append(f"{header}: {path} encodes text: {texts[1][:40]!r}")
            for text in texts:
                normalized = normalize(text)
                if normalized in exempt:
                    continue
                if len(text) > MAX_JSON_STRING_CHARS and not path.endswith("<joined>"):
                    out["json"].append(
                        f"{header}: {path} longer than {MAX_JSON_STRING_CHARS} chars: {text[:60]}"
                    )
                words = set(_WORD_RE.findall(normalized)) & hidden_words
                if words:
                    out["json"].append(f"{header}: {path} hidden-only words {sorted(words)}")
                for hidden_line in hidden_lines:
                    if hidden_line in normalized and hidden_line not in bare_corpus:
                        out["json"].append(
                            f"{header}: {path} hidden test line {hidden_line[:60]!r}"
                        )
                for literal in hidden_only_literals(material):
                    if normalize(literal) in normalized and normalize(literal) not in bare_corpus:
                        out["json"].append(f"{header}: {path} hidden literal {literal!r}")
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


def _distinct(records: list[dict[str, Any]], allowed_folds: int = 0) -> tuple[int, int]:
    """(calls, folded re-sends).

    An identical prompt re-sent is folded into one call only up to ``allowed_folds``: the number of
    pre-effect quota failures the row's lease records report (the bare arm's account rotation).
    Any other repeat is a genuine second attempt and counts.
    """

    shas = [
        str(item.get("prompt_sha256") or normalize(str(item.get("prompt") or "")))
        for item in records
    ]
    repeats = len(shas) - len(set(shas))
    folds = min(repeats, max(0, int(allowed_folds)))
    return len(shas) - folds, folds


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
    lane: str = LANE_STRICT,
) -> TaskAudit:
    treatment = lane == LANE_TREATMENT
    result = TaskAudit(
        key=key, task_id=material.task_id, lane=LANE_TREATMENT if treatment else LANE_STRICT
    )
    if material.error:
        result.violations.append(f"fixture_unreadable:{material.error}")
    bare_folds = sum(int(row.get("pre_effect_quota_resends") or 0) for row in bare_rows or [])
    result.bare_calls, result.bare_resends = _distinct(bare_records, bare_folds)
    result.with_nexus_calls, result.with_nexus_resends = _distinct(with_records, 0)
    not_run = any(row.get("not_run") for row in [*(bare_rows or []), *(with_rows or [])])
    if (
        bare_rows is not None
        and with_rows is not None
        and (len(bare_rows) != 1 or len(with_rows) != 1)
    ):
        result.violations.append(f"unpaired_rows:bare={len(bare_rows)},with_nexus={len(with_rows)}")
    # Every COMPLETED row is audited on its own; only the pairwise checks are skipped when its
    # partner is not_run (run stopped early).
    completed = {
        "bare": [row for row in bare_rows or [] if not row.get("not_run")],
        "with_nexus": [row for row in with_rows or [] if not row.get("not_run")],
    }
    with_row = completed["with_nexus"][0] if completed["with_nexus"] else None
    for arm, calls in (("bare", result.bare_calls), ("with_nexus", result.with_nexus_calls)):
        arm_rows = completed[arm]
        if (
            arm_rows
            and calls == 0
            and any(int(row.get("model_calls") or 0) > 0 for row in arm_rows)
        ):
            result.violations.append(f"{arm}_model_call_not_captured")
        if treatment and arm == "with_nexus":
            # Treatment lane: 1..N with-Nexus calls; the bare arm stays at exactly one.
            cap = _treatment_max_calls(with_row)
            if calls > cap:
                result.violations.append(f"with_nexus_calls={calls}>treatment_max={cap}")
        elif calls > 1:
            result.violations.append(f"{arm}_calls={calls}")
    killed = with_row is not None and (
        with_row.get("treatment_timeout") is True
        or str(with_row.get("runtime_classification") or "") == "subprocess_timeout"
        or with_row.get("task_deadline_exceeded") is True
    )
    if (
        treatment
        and with_row is not None
        and not (killed and int(with_row.get("model_calls") or 0) == 0)
    ):
        # A killed subprocess reports no calls; its calls are the captured ones (H2).
        row_calls = int(with_row.get("model_calls") or 0)
        if row_calls != result.with_nexus_calls:
            # Every model call the row reports was captured, and nothing else was.
            result.violations.append(
                f"with_nexus_calls_mismatch:captured={result.with_nexus_calls},row={row_calls}"
            )
    candidates: dict[str, str] = {}
    runner_order: list[str] = []
    visible_lines: set[str] = set()
    hidden_line_set = set(hidden_only_lines(material))
    if treatment and len(with_records) > 1:
        candidates, candidate_errors = load_row_candidates(with_row or {})
        result.treatment_round_findings.extend(candidate_errors)
        runner_order = [str(sha) for sha in (with_row or {}).get("runner_candidate_sha256s") or []]
        visible_lines = row_visible_output_lines(with_row or {})

    def _earlier_candidates(round_index: int) -> list[str]:
        """Runner-derived candidates of the calls before ``round_index`` (0-based)."""

        return [candidates[sha] for sha in runner_order[:round_index] if sha in candidates]

    def _earlier_candidate_lines(round_index: int) -> set[str]:
        """Exact raw lines of earlier runner-derived candidates (never a hidden test line)."""

        return {
            line
            for text in _earlier_candidates(round_index)
            for line in text.splitlines()
            if line.strip() and normalize(line) not in hidden_line_set
        }

    if not not_run and result.bare_calls == 0 and result.with_nexus_calls > 0:
        result.violations.append("bare_calls=0")
    bare_prompt = str(bare_records[0].get("prompt") or "") if bare_records else ""
    bare_corpus = _decoded_corpus(bare_prompt)
    literals = hidden_only_literals(material)
    inventory = set(HIDDEN_LITERALS.get(material.task_id, ()))
    hidden_lines = hidden_only_lines(material)
    for index, record in enumerate(with_records):
        # (1) Every round's FULL raw prompt goes through the hidden-line scan first (no exemption,
        # aborts the run) and the hidden-literal scan (G2). Only in rounds >= 2 of the treatment
        # lane, a literal inside a line byte-identical to a line of an EARLIER runner-derived model
        # candidate is exempt: the model wrote it before any feedback (R2-3). Other literal hits
        # in rounds >= 2 void the row (treatment_literal_hits) instead of aborting the run.
        prompt = str(record.get("prompt") or "")
        corpus = _decoded_corpus(prompt)
        later_round = treatment and index > 0
        if later_round:
            exempt = _earlier_candidate_lines(index)
            literal_corpus = _decoded_corpus(
                "\n".join(line for line in prompt.splitlines() if line not in exempt)
            )
        else:
            literal_corpus = corpus
        hits = result.treatment_literal_hits if later_round else result.hidden_hits
        for literal in literals:
            if literal in hits:
                continue
            if any(
                needle in literal_corpus and needle not in bare_corpus
                for needle in _needles(literal, inventory)
            ):
                hits.append(literal)
        for line in hidden_lines:
            if line in corpus and line not in bare_corpus and line not in result.hidden_line_hits:
                result.hidden_line_hits.append(line)
        if normalize(PRIOR_ART_MARKER) in corpus:
            result.prior_art_present = True
    if result.hidden_hits:
        result.violations.append("hidden_literal_in_with_nexus_prompt")
    result.row_void = bool(result.treatment_literal_hits)
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
        # Without a bare capture (partner not_run) compare against what the bare arm is given:
        # the task text, the source and the visible test from the fixture material.
        reference = bare_prompt if bare_records else synthetic_bare_reference(material)
        if bare_records or not_run:
            result.extra_lines = extra_lines(first, reference)
            checks = classify_extra_lines(first, reference, material, lane=result.lane)
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
        deferred = treatment and with_row is not None and "_treatment_rescore" in with_row
        if deferred and len(with_records) > 1:
            # The visible re-runs this classification needs happen at the end of the run (no
            # staging window open); the early audit defers it, the final audit always runs it.
            result.treatment_round_findings_deferred = True
        elif treatment and len(with_records) > 1:
            for index, record in enumerate(with_records[1:], start=2):
                findings, self_heal = audit_treatment_round(
                    str(record.get("prompt") or ""),
                    round1_prompt=first,
                    bare_prompt=reference,
                    material=material,
                    candidate_lines={
                        " ".join(line.split()) for line in _earlier_candidate_lines(index - 1)
                    },
                    candidate_texts=_earlier_candidates(index - 1),
                    visible_lines=visible_lines,
                    product_python=str((with_row or {}).get("treatment_product_python") or ""),
                    visible_test_arg=str((with_row or {}).get("treatment_visible_test_arg") or ""),
                )
                result.treatment_rounds_audited += 1
                result.self_heal_rounds_observed += int(self_heal)
                result.treatment_round_findings.extend(f"round{index}:{item}" for item in findings)
            if result.treatment_round_findings:
                result.violations.append("treatment_round_not_allowed")
    return result


def _treatment_max_calls(row: Mapping[str, Any] | None) -> int:
    try:
        value = int(
            (row or {}).get("treatment_max_model_calls") or DEFAULT_TREATMENT_MAX_MODEL_CALLS
        )
    except (TypeError, ValueError):
        value = DEFAULT_TREATMENT_MAX_MODEL_CALLS
    return max(1, value)


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def load_row_candidates(row: Mapping[str, Any]) -> tuple[dict[str, str], list[str]]:
    """The row's runner-derived model candidates (``treatment_candidates``), each re-hashed.

    The runner derived them from the capture wrapper's recorded model responses
    (``treatment_lane.derive_runner_candidates``), not from anything the product reported.
    """

    raw = row.get("treatment_candidates")
    out: dict[str, str] = {}
    errors: list[str] = []
    if not isinstance(raw, Mapping) or not raw:
        return out, ["no_runner_derived_candidates"]
    for sha, text in raw.items():
        sha = str(sha)
        if not _SHA256_RE.match(sha) or not isinstance(text, str):
            errors.append(f"candidate_sha_malformed:{sha[:16]}")
            continue
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != sha:
            errors.append(f"candidate_sha_mismatch:{sha[:12]}")
            continue
        out[sha] = text
    return out, errors


def _syntax_lines(candidate_texts: Iterable[str]) -> set[str]:
    """The exact ``syntax_error``/``syntax_warning`` lines the product would print for these candidates."""

    from nexus.research.sprint_service import syntax_rejection_lines

    out: set[str] = set()
    for text in candidate_texts:
        out |= {" ".join(line.split()) for line in syntax_rejection_lines(text)}
    return out


def normalize_output_line(line: str) -> str:
    """One pytest output line without its volatile parts (durations, rule fills)."""

    # Durations only. Directories are NOT stripped (G5-3 class): the counted lane's confined
    # runs print rootdir-relative paths, so a path can never carry text past this check.
    text = _DURATION_RE.sub("in Xs", " ".join(str(line).split()))
    return text.strip(" =_-")


def row_visible_output_lines(row: Mapping[str, Any]) -> set[str]:
    """The runner's own visible-test output on the row's candidates (normalised lines)."""

    out: set[str] = set()
    outputs = row.get("treatment_visible_outputs") or {}
    if isinstance(outputs, Mapping):
        for text in outputs.values():
            for line in str(text or "").splitlines():
                normalized = normalize_output_line(line)
                if normalized:
                    out.add(normalized)
    return out


def audit_treatment_round(
    prompt: str,
    *,
    round1_prompt: str,
    bare_prompt: str,
    material: TaskMaterial,
    candidate_lines: set[str],
    visible_lines: set[str],
    candidate_texts: Iterable[str] = (),
    product_python: str = "",
    visible_test_arg: str = "",
) -> tuple[list[str], bool]:
    """Findings for one later with-Nexus round (round >= 2) and whether it was a self-heal round."""

    blocks_cfg = load_treatment_blocks()
    schema = load_block_schema(LANE_TREATMENT)
    findings: list[str] = []
    if not _no_tools_position_ok(prompt, bare=False):
        findings.append("no_tools_prefix_not_once_before_task")
    known = set(_lines(strip_no_tools(round1_prompt))) | set(_lines(strip_no_tools(bare_prompt)))
    fixed = {" ".join(str(text).split()) for text in blocks_cfg.get("fixed_sentences") or []}
    headers = {str(text) for text in blocks_cfg.get("headers") or []}
    forbidden = {str(text) for text in blocks_cfg.get("forbidden_headers") or []}
    candidate_header = re.compile(str(blocks_cfg.get("candidate_header_pattern") or r"^$^"))
    syntax_lines = _syntax_lines(candidate_texts)
    round_lines = frozenset(_lines(strip_no_tools(prompt)))
    from nexus.research.sprint_service import visible_timeout_line_re

    timeout_re = visible_timeout_line_re(product_python, visible_test_arg)
    selected = frozenset(_selected_capabilities(prompt))
    hidden_numbers = frozenset(hidden_only_numbers(material, bare_prompt))
    self_heal = False
    previous = ""
    for header, line in _blocks(prompt):
        first_failure_line, previous = previous == "[FAILURE]", line
        if line in forbidden:
            findings.append(f"forbidden_block:{line}")
            continue
        if header == HIDDEN_GUIDANCE_HEADER and not SECTION_HEADER_RE.match(line):
            findings.append("hidden_verifier_guidance_not_empty")
            continue
        if header in forbidden:
            continue  # body of a forbidden block (already a finding)
        if line in known:
            continue
        if SESSION_BOUNDARY_RE.match(line):
            continue  # each round is a new sprint attempt (task_id ...-s<n>-a<k>)
        if line in fixed:
            self_heal = self_heal or line == " ".join(SELF_HEAL_SENTENCE.split())
            continue
        if line in headers or candidate_header.match(line):
            continue
        if line in candidate_lines:
            continue
        output_line = normalize_output_line(line)
        if output_line and (
            output_line in visible_lines
            # only the first [FAILURE] line can be cut mid-line (the product keeps the last 1200 chars)
            or (first_failure_line and any(item.endswith(output_line) for item in visible_lines))
        ):
            continue
        if line in PRODUCT_ERROR_CODES or line in syntax_lines or _MULTI_FILE_RE.match(line):
            continue
        if timeout_re.match(line):
            continue
        if header in JSON_BLOCK_HEADERS and line.startswith("{"):
            try:
                payload = parse_block_json(line)
            except ValueError:
                findings.append(f"block_not_json:{header}")
                continue
            findings.extend(
                _schema_findings(
                    header,
                    payload,
                    schema.get(header, {}),
                    material,
                    selected=selected,
                    hidden_numbers=hidden_numbers,
                    round_lines=round_lines,
                )
            )
            continue
        findings.append(f"line_not_allowed:{line[:80]}")
    return findings, self_heal


def synthetic_bare_reference(material: TaskMaterial) -> str:
    """The bare arm's informational content, rebuilt from the fixture (no instructions)."""

    return "\n".join([
        NO_TOOLS_PREFIX,
        f"Task: {material.task_desc}",
        material.task_desc,
        material.source,
        material.visible_test,
    ])


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
    lane: str = LANE_STRICT,
) -> dict[str, Any]:
    treatment = lane == LANE_TREATMENT
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
                lane=lane,
            )
        )
    unknown = sorted(
        f"{arm}__{key}"
        for (arm, key) in captures
        if arm not in {"with_nexus", "without_nexus"} or key not in materials
    )
    row_violations: list[str] = []
    for row_key in sorted({_row_key(row) for row in rows} - set(materials)):
        counts = (
            len(by_arm.get(("without_nexus", row_key), [])),
            len(by_arm.get(("with_nexus", row_key), [])),
        )
        if counts != (1, 1):
            row_violations.append(
                f"{row_key}:unpaired_rows:bare={counts[0]},with_nexus={counts[1]}"
            )
    for row in rows:
        ident = f"{row.get('mode')}:{row.get('task_id')}#{row.get('trial_index')}"
        if _row_key(row) not in materials and not row.get("not_run"):
            row_violations.append(f"{ident}:no_fixture_material")
        if str(row.get("route_cost_policy_source") or ""):
            row_violations.append(f"{ident}:promoted_route_cost_policy")
        if (
            str(row.get("mode")) == "with_nexus"
            and int(row.get("attempt_count") or 0) > 1
            and not treatment  # treatment lane: in-product rounds; calls are reconciled per task
        ):
            row_violations.append(f"{ident}:attempt_count>1")
        if treatment and row.get("bounded_nexus_rescue_used") is True:
            row_violations.append(f"{ident}:runner_rescue_in_treatment_lane")
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
        "lane": LANE_TREATMENT if treatment else LANE_STRICT,
        "run_id": run_id,
        "tasks": [item.to_dict() for item in tasks],
        "failed_keys": [item.key for item in failed],
        "unattributed_captures": unknown,
        "row_violations": row_violations,
        "run_violations": run_violations,
    }
