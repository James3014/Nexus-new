#!/usr/bin/env python3
"""Exact-base, tiered PR verification planner and regression classifier."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[2]
_TRUSTED_GIT_EXECUTABLE = (
    str(Path(executable).resolve()) if (executable := shutil.which("git")) else ""
)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.ops.select_tests import (  # noqa: E402, I001
    load_impact_rules,
    select_target_details,
)


DOC_PREFIXES = ("docs/", "openwiki/", "nexus_wiki_vault/")
GOVERNANCE_FILES = {"AGENTS.md", "MUSE_PROTO.md"}
WORKFLOW_PREFIXES = (".github/workflows/", "scripts/ops/")
DEPENDENCY_FILES = {
    "pyproject.toml",
    "uv.lock",
    "pytest.ini",
    "pyrightconfig.json",
    "ruff.toml",
}
SENSITIVE_PREFIXES = (
    "nexus/engine/capability_planner",
    "nexus/services/worker_registry",
    "nexus/lifecycle/",
    "nexus/verifiers/",
    "nexus/contracts/",
    "nexus/orchestrator/",
    "scripts/ops/ci_gate.py",
    ".github/workflows/",
)
MANDATORY_TIER2_TARGETS = (
    "tests/gates/test_s2t_memory_sidecar_fixtures.py",
    "tests/ops/test_select_tests.py",
    "tests/ops/test_pr_impact_gate.py",
    "tests/services/test_policy_gate.py",
    "tests/architecture/test_boundaries.py",
    "tests/architecture/test_boundaries_v2.py",
    "tests/architecture/test_boundaries_v3.py",
    "tests/architecture/test_boundaries_v4.py",
)
DOC_GOVERNANCE_TARGETS = (
    "tests/ops/test_select_tests.py",
    "tests/ops/test_ci_gate_wiki_sync_block.py",
)
CI_MACHINERY_TARGETS = (
    "tests/ops/test_select_tests.py",
    "tests/ops/test_pr_impact_gate.py",
    "tests/ops/test_ci_gate_report_trust_audit.py",
)
EXACT_CONFIG_TARGETS: dict[str, tuple[str, ...]] = {
    "configs/codex_dx_failure_prevention.json": ("tests/ops/test_codex_dx_failure_prevention.py",),
    "configs/codex_task_context_index.json": ("tests/ops/test_codex_task_context_index.py",),
    "configs/benchmarks/codex_dx_before_v1.json": (
        "tests/benchmark/test_codex_dx_benchmark.py",
        "tests/benchmark/test_codex_dx_history.py",
    ),
}

OPTIONAL_BROWSER_EXCLUSION = "tests/core/test_web_dom_mapper.py"
EXACT_GIT_EVIDENCE_ONLY = "EXACT_GIT_EVIDENCE_ONLY"
_UNKNOWN = "IMPACT_UNKNOWN"
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
_AWARE_ISO_DATETIME = re.compile(
    r"(?<![0-9A-Za-z])"
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}"
    r"(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})"
    r"(?![0-9A-Za-z])"
)

LogicalNodeKey = tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ImpactPlan:
    base_sha: str
    head_sha: str
    changed_paths: list[str]
    tier: int
    impact_class: str
    confidence: float
    pytest_targets: list[str]
    pytest_required: bool
    wiki_required: bool
    workflow_validation_required: bool
    changed_python_paths: list[str]
    reasons: list[str]
    unmatched_paths: list[str]
    source_tree: str = ""
    test_inventory_tree: str = ""
    base_source_tree: str = ""
    base_test_inventory_tree: str = ""


@dataclass(frozen=True)
class PytestRunResult:
    exit_code: int
    status: str
    failures: list[str]
    junit_path: str
    stdout_path: str
    executed_targets: list[str] = field(default_factory=list)
    missing_targets: list[str] = field(default_factory=list)
    revision: str = ""
    plan_digest: str = ""
    selected_targets: list[str] = field(default_factory=list)
    impact_class: str = ""
    unexpected_missing_targets: list[str] = field(default_factory=list)
    verifier_digest: str = ""
    source_tree: str = ""
    test_inventory_tree: str = ""
    bound_source_tree: str = ""
    bound_test_inventory_tree: str = ""
    collection_count: int = 0
    node_ids: list[str] = field(default_factory=list)
    passed_node_ids: list[str] = field(default_factory=list)
    error_node_ids: list[str] = field(default_factory=list)
    skipped_node_ids: list[str] = field(default_factory=list)
    failed_node_ids: list[str] = field(default_factory=list)
    terminal_status: str = ""
    provenance_digest: str = ""


@dataclass(frozen=True)
class RegressionClassification:
    classification: str
    blocking: bool
    base_failures: list[str]
    head_failures: list[str]
    new_failures: list[str]
    resolved_failures: list[str]
    reason: str


def _exact_sha(value: str, label: str) -> None:
    if not isinstance(value, str) or not _FULL_SHA.fullmatch(value):
        raise ValueError(f"{label} must be a full lowercase immutable SHA")


def _exact_digest(value: str, label: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(f"{label} must be a full lowercase SHA-256 digest")


def _run_trusted_git(
    root: Path,
    args: list[str],
    *,
    text: bool,
) -> subprocess.CompletedProcess[Any]:
    if not _TRUSTED_GIT_EXECUTABLE or not root.is_dir():
        empty = "" if text else b""
        return subprocess.CompletedProcess(args, 127, stdout=empty, stderr=empty)
    return subprocess.run(
        [_TRUSTED_GIT_EXECUTABLE, *args],
        cwd=root,
        text=text,
        capture_output=True,
        check=False,
    )


def parse_raw_diff_z(stream: bytes) -> list[dict[str, str]]:
    """Parse one strict ``git diff --raw -z --no-renames`` byte stream.

    Git emits alternating metadata and path fields terminated by NUL.  We do
    not accept rename scores, non-deletion records, or incomplete field pairs.
    """
    if not isinstance(stream, bytes) or not stream or not stream.endswith(b"\0"):
        raise ValueError("raw diff stream is missing its NUL terminator")
    records = stream[:-1].split(b"\0")
    if len(records) % 2:
        raise ValueError("raw diff stream has a truncated metadata/path pair")
    parsed: list[dict[str, str]] = []
    seen: set[str] = set()
    pairs = []
    for index in range(0, len(records), 2):
        metadata, raw_path = records[index : index + 2]
        pairs.append((metadata, raw_path))
    for metadata, raw_path in pairs:
        try:
            metadata_text = metadata.decode("ascii")
            path = raw_path.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("raw diff contains non-text metadata/path") from exc
        fields = metadata_text.split()
        if len(fields) != 5 or not fields[0].startswith(":"):
            raise ValueError("raw diff metadata is malformed")
        old_mode, new_mode, old_sha, new_sha, status = fields
        old_mode = old_mode[1:]
        if (
            len(old_mode) != 6
            or len(new_mode) != 6
            or not re.fullmatch(r"[0-7]{12}", old_mode + new_mode)
        ):
            raise ValueError("raw diff mode is malformed")
        if not all(re.fullmatch(r"[0-9a-f]{7,64}", value) for value in (old_sha, new_sha)):
            raise ValueError("raw diff object id is malformed")
        if status != "D" or not path or path.startswith("/") or "\x00" in path:
            raise ValueError("stream is not deletion-only exact evidence")
        if path in seen:
            raise ValueError("raw diff contains a duplicate path")
        seen.add(path)
        parsed.append({
            "old_mode": old_mode,
            "new_mode": new_mode,
            "old_sha": old_sha,
            "new_sha": new_sha,
            "status": status,
            "path": path,
        })
    if not parsed:
        raise ValueError("raw diff stream is empty")
    return parsed


def compute_orphan_evidence_digest(path: str, base_tree: str) -> str:
    """Return the digest of the small, recomputable orphan evidence tuple."""
    _exact_sha(base_tree, "base_tree")
    payload = json.dumps(
        {"base_tree": base_tree, "orphan": True, "path": path},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _unknown_exact_git_result(reasons: list[str]) -> dict[str, Any]:
    return {
        "status": _UNKNOWN,
        "claim": _UNKNOWN,
        "blocking": True,
        "reasons": sorted(set(reasons)),
        "candidate_commit_allowed": False,
        "public_claim_allowed": False,
        "merge_authority": False,
        "consumers": [],
    }


def verify_exact_git_deletion_evidence(
    *,
    base_sha: str,
    target_sha: str,
    base_tree: str,
    target_tree: str,
    test_inventory_tree: str,
    raw_stream_a: bytes | None = None,
    raw_stream_b: bytes | None = None,
    allowed_deletion_manifest: Iterable[str] | None = None,
    orphan_evidence: Mapping[str, Mapping[str, Any]] | None = None,
    dynamic_caller_universe_known: bool = False,
    root: Path | None = None,
) -> dict[str, Any]:
    """Recompute and classify a complete exact-endpoint Git diff."""
    reasons: list[str] = []
    try:
        for value, label in (
            (base_sha, "base_sha"),
            (target_sha, "target_sha"),
            (base_tree, "base_tree"),
            (target_tree, "target_tree"),
            (test_inventory_tree, "test_inventory_tree"),
        ):
            _exact_sha(value, label)
    except ValueError as exc:
        return _unknown_exact_git_result([str(exc)])

    if base_sha == target_sha or base_tree == target_tree:
        reasons.append("base and target are not distinct immutable endpoints")
    computed_stream_a = b""
    computed_stream_b = b""
    if root is None:
        reasons.append("trusted Git root is required")
    else:
        try:
            recomputed_base_tree, _ = _git_revision_trees(root, base_sha)
            recomputed_target_tree, recomputed_test_tree = _git_revision_trees(root, target_sha)
            if recomputed_base_tree != base_tree:
                reasons.append("base_tree does not match exact Git endpoint")
            if recomputed_target_tree != target_tree:
                reasons.append("target_tree does not match exact Git endpoint")
            if recomputed_test_tree != test_inventory_tree:
                reasons.append("test inventory tree does not match exact target tree")
        except ValueError as exc:
            reasons.append(str(exc))
        streams = [
            _run_trusted_git(
                root,
                ["diff", "--raw", "-z", "--no-renames", base_sha, target_sha],
                text=False,
            )
            for _ in range(2)
        ]
        if any(item.returncode != 0 for item in streams):
            reasons.append("complete exact Git raw diff could not be produced")
        else:
            computed_stream_a = streams[0].stdout
            computed_stream_b = streams[1].stdout
            if computed_stream_a != computed_stream_b:
                reasons.append("independently recomputed complete Git diffs diverge")

    if raw_stream_a is None or raw_stream_b is None:
        reasons.append("two supplied complete raw evidence streams are required")
    else:
        if raw_stream_a != raw_stream_b:
            reasons.append("supplied raw evidence streams diverge")
        if computed_stream_a and raw_stream_a != computed_stream_a:
            reasons.append("supplied raw evidence identity does not match complete Git diff")
        if computed_stream_b and raw_stream_b != computed_stream_b:
            reasons.append("supplied raw evidence identity does not match complete Git diff")

    try:
        supplied_first = parse_raw_diff_z(raw_stream_a or b"")
        supplied_second = parse_raw_diff_z(raw_stream_b or b"")
    except ValueError as exc:
        reasons.append(str(exc))
        supplied_first, supplied_second = [], []
    if supplied_first and supplied_second and supplied_first != supplied_second:
        reasons.append("independent raw diff streams diverge")
    try:
        recomputed = parse_raw_diff_z(computed_stream_a)
    except ValueError as exc:
        reasons.append(str(exc))
        recomputed = []
    paths = [entry["path"] for entry in recomputed]
    manifest = list(allowed_deletion_manifest or [])
    if not manifest or len(manifest) != len(set(manifest)) or set(manifest) != set(paths):
        reasons.append("allowed deletion manifest is missing, stale, duplicated, or drifting")
    evidence = orphan_evidence or {}
    if set(evidence) != set(paths):
        reasons.append("orphan evidence does not cover exactly every deletion path")
    for path in paths:
        item = evidence.get(path, {})
        expected_digest = compute_orphan_evidence_digest(path, base_tree)
        if (
            item.get("orphan") is not True
            or item.get("base_tree") != base_tree
            or item.get("source_revision") != base_sha
            or item.get("evidence_digest") != expected_digest
        ):
            reasons.append(f"orphan evidence is missing or tampered for {path}")
    if not dynamic_caller_universe_known:
        reasons.append("dynamic caller universe is unknown")
    if reasons:
        return _unknown_exact_git_result(reasons)
    return {
        "status": EXACT_GIT_EVIDENCE_ONLY,
        "claim": EXACT_GIT_EVIDENCE_ONLY,
        "blocking": False,
        "reasons": [],
        "deletions": paths,
        "base_sha": base_sha,
        "target_sha": target_sha,
        "base_tree": base_tree,
        "target_tree": target_tree,
        "test_inventory_tree": test_inventory_tree,
        "raw_stream_sha256": hashlib.sha256(computed_stream_a).hexdigest(),
        "candidate_commit_allowed": False,
        "public_claim_allowed": False,
        "merge_authority": False,
        "consumers": [],
    }


def _unique_existing(targets: Iterable[str], *, root: Path = ROOT) -> list[str]:
    selected: list[str] = []
    for target in targets:
        path_part = target.split("::", 1)[0]
        if (root / path_part).exists() and target not in selected:
            selected.append(target)
    return selected


def _git_revision_trees(root: Path, revision: str) -> tuple[str, str]:
    _exact_sha(revision, "revision")
    commit = _run_trusted_git(
        root,
        ["rev-parse", f"{revision}^{{commit}}"],
        text=True,
    )
    source = _run_trusted_git(
        root,
        ["rev-parse", f"{revision}^{{tree}}"],
        text=True,
    )
    inventory = _run_trusted_git(
        root,
        ["rev-parse", f"{revision}:tests"],
        text=True,
    )
    if (
        commit.returncode != 0
        or commit.stdout.strip() != revision
        or source.returncode != 0
        or inventory.returncode != 0
    ):
        raise ValueError("revision trees cannot be resolved from the immutable commit")
    source_tree = source.stdout.strip()
    test_inventory_tree = inventory.stdout.strip()
    _exact_sha(source_tree, "source_tree")
    _exact_sha(test_inventory_tree, "test_inventory_tree")
    return source_tree, test_inventory_tree


def compute_test_provenance_digest(
    *,
    revision: str,
    source_tree: str,
    test_inventory_tree: str,
    plan_digest: str,
    verifier_digest: str,
    collection_count: int = 0,
    node_ids: list[str] | None = None,
    passed_node_ids: list[str] | None = None,
    failed_node_ids: list[str] | None = None,
    error_node_ids: list[str] | None = None,
    skipped_node_ids: list[str] | None = None,
    terminal_status: str = "",
    exit_code: int = 0,
    status: str = "",
    failures: list[str] | None = None,
    executed_targets: list[str] | None = None,
    missing_targets: list[str] | None = None,
    selected_targets: list[str] | None = None,
    unexpected_missing_targets: list[str] | None = None,
    impact_class: str = "",
) -> str:
    for value, label in (
        (revision, "revision"),
        (source_tree, "source_tree"),
        (test_inventory_tree, "test_inventory_tree"),
    ):
        _exact_sha(value, label)
    _exact_digest(plan_digest, "plan_digest")
    _exact_digest(verifier_digest, "verifier_digest")
    payload = json.dumps(
        {
            "plan_digest": plan_digest,
            "revision": revision,
            "source_tree": source_tree,
            "test_inventory_tree": test_inventory_tree,
            "verifier_digest": verifier_digest,
            "collection_count": collection_count,
            "node_ids": sorted(node_ids or []),
            "passed_node_ids": sorted(passed_node_ids or []),
            "failed_node_ids": sorted(failed_node_ids or []),
            "error_node_ids": sorted(error_node_ids or []),
            "skipped_node_ids": sorted(skipped_node_ids or []),
            "terminal_status": terminal_status,
            "exit_code": exit_code,
            "status": status,
            "failures": list(failures or []),
            "executed_targets": list(executed_targets or []),
            "missing_targets": list(missing_targets or []),
            "selected_targets": list(selected_targets or []),
            "unexpected_missing_targets": list(unexpected_missing_targets or []),
            "impact_class": impact_class,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _is_docs_or_governance(path: str) -> bool:
    return path in GOVERNANCE_FILES or path.endswith(".md") or path.startswith(DOC_PREFIXES)


def _is_workflow_or_ci(path: str) -> bool:
    return path.startswith(WORKFLOW_PREFIXES) or path in {".github/dependabot.yml"}


def build_impact_plan(
    changed_paths: list[str],
    *,
    base_sha: str = "",
    head_sha: str = "",
    root: Path = ROOT,
) -> ImpactPlan:
    source_tree = ""
    test_inventory_tree = ""
    base_source_tree = ""
    base_test_inventory_tree = ""
    provenance_error = ""
    if base_sha or head_sha:
        try:
            base_source_tree, base_test_inventory_tree = _git_revision_trees(root, base_sha)
            source_tree, test_inventory_tree = _git_revision_trees(root, head_sha)
        except ValueError as exc:
            provenance_error = str(exc)
    normalized = sorted({
        path.strip().replace("\\", "/").strip("/") for path in changed_paths if path.strip()
    })
    if not normalized:
        return ImpactPlan(
            base_sha=base_sha,
            head_sha=head_sha,
            changed_paths=[],
            tier=2,
            impact_class="IMPACT_UNKNOWN",
            confidence=0.0,
            pytest_targets=_unique_existing(MANDATORY_TIER2_TARGETS, root=root),
            pytest_required=True,
            wiki_required=False,
            workflow_validation_required=True,
            changed_python_paths=[],
            reasons=[
                "empty exact-base diff is not a valid PR impact packet",
                *([provenance_error] if provenance_error else []),
            ],
            unmatched_paths=[],
            source_tree=source_tree,
            test_inventory_tree=test_inventory_tree,
            base_source_tree=base_source_tree,
            base_test_inventory_tree=base_test_inventory_tree,
        )

    docs_only = all(_is_docs_or_governance(path) for path in normalized)
    workflow_change = any(_is_workflow_or_ci(path) for path in normalized)
    dependency_change = any(path in DEPENDENCY_FILES for path in normalized)
    sensitive_change = any(path.startswith(SENSITIVE_PREFIXES) for path in normalized)
    contract_change = any(
        "contract" in path.lower() or "schema" in path.lower() for path in normalized
    )
    changed_tests = [
        path for path in normalized if path.startswith("tests/") and path.endswith(".py")
    ]
    changed_python = [
        path for path in normalized if path.endswith(".py") and not path.startswith("tests/")
    ]
    wiki_required = any(path.startswith(("openwiki/", "nexus_wiki_vault/")) for path in normalized)

    exact_config_paths = [
        path for path in normalized if path in EXACT_CONFIG_TARGETS and (root / path).is_file()
    ]
    exact_config_targets: list[str] = []
    exact_config_reasons: list[str] = []
    for path in exact_config_paths:
        for target in EXACT_CONFIG_TARGETS[path]:
            if target not in exact_config_targets:
                exact_config_targets.append(target)
        exact_config_reasons.append(f"{path}: matched exact config contract")

    other_paths = [
        path
        for path in normalized
        if path not in exact_config_paths and path not in exact_config_targets
    ]

    if other_paths:
        details = select_target_details(other_paths, load_impact_rules())
        details_targets = list(details.targets)
        details_reasons = list(details.reasons)
        details_confidence = details.confidence
        details_unmatched = list(details.unmatched_paths)
        details_high_risk = details.high_risk_escalated
        details_fallback_used = details.fallback_used
    else:
        details_targets = []
        details_reasons = []
        details_confidence = 0.9
        details_unmatched = []
        details_high_risk = False
        details_fallback_used = False

    unknown_unmatched = [
        path
        for path in details_unmatched
        if not (
            _is_docs_or_governance(path)
            or _is_workflow_or_ci(path)
            or (path.startswith("tests/") and path.endswith(".py"))
            or path in DEPENDENCY_FILES
            or path.startswith(SENSITIVE_PREFIXES)
            or "contract" in path.lower()
            or "schema" in path.lower()
        )
    ]

    targets = list(exact_config_targets) + [
        t for t in details_targets if t not in exact_config_targets
    ]
    reasons = list(exact_config_reasons) + list(details_reasons)
    impact_class = "SCOPED_IMPLEMENTATION"
    tier = 1
    confidence = min(0.9, details_confidence) if other_paths else 0.9

    if docs_only:
        impact_class = "DOCS_GOVERNANCE"
        mapped_docs_targets = [] if details_fallback_used else targets
        targets = _unique_existing([*mapped_docs_targets, *DOC_GOVERNANCE_TARGETS], root=root)
        confidence = max(confidence, 0.8)
        reasons.append("docs/governance-only diff selects governance verification")
    else:
        targets = _unique_existing([*changed_tests, *targets], root=root)

    if workflow_change:
        impact_class = "CI_INFRASTRUCTURE"
        tier = 2
        targets = _unique_existing(
            [*targets, *CI_MACHINERY_TARGETS, *MANDATORY_TIER2_TARGETS], root=root
        )
        reasons.append("CI/workflow change requires CI machinery regression set")
    elif dependency_change or sensitive_change or contract_change or details_high_risk:
        impact_class = "HIGH_RISK_INTEGRATION"
        tier = 2
        targets = _unique_existing([*targets, *MANDATORY_TIER2_TARGETS], root=root)
        reasons.append("authority/contract/dependency/high-risk seam escalated to Tier 2")

    if unknown_unmatched:
        impact_class = "IMPACT_UNKNOWN"
        tier = 2
        confidence = min(confidence, 0.4)
        targets = _unique_existing([*targets, *MANDATORY_TIER2_TARGETS], root=root)
        reasons.append("unmatched paths fail closed to broader verification")

    if changed_python and not targets:
        impact_class = "IMPACT_UNKNOWN"
        tier = 2
        confidence = 0.0
        targets = _unique_existing(MANDATORY_TIER2_TARGETS, root=root)
        reasons.append("production Python change had no mapped tests")

    if provenance_error:
        impact_class = "IMPACT_UNKNOWN"
        tier = 2
        confidence = 0.0
        targets = _unique_existing([*targets, *MANDATORY_TIER2_TARGETS], root=root)
        reasons.append(provenance_error)

    pytest_required = bool(targets)
    if not pytest_required and not docs_only:
        impact_class = "IMPACT_UNKNOWN"
        tier = 2
        targets = _unique_existing(MANDATORY_TIER2_TARGETS, root=root)
        pytest_required = True
        reasons.append("empty verification set failed closed")

    return ImpactPlan(
        base_sha=base_sha,
        head_sha=head_sha,
        changed_paths=normalized,
        tier=tier,
        impact_class=impact_class,
        confidence=round(confidence, 2),
        pytest_targets=targets,
        pytest_required=pytest_required,
        wiki_required=wiki_required,
        workflow_validation_required=workflow_change,
        changed_python_paths=changed_python,
        reasons=reasons,
        unmatched_paths=unknown_unmatched,
        source_tree=source_tree,
        test_inventory_tree=test_inventory_tree,
        base_source_tree=base_source_tree,
        base_test_inventory_tree=base_test_inventory_tree,
    )


def parse_junit_failures(path: Path) -> list[str]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    root = ET.parse(path).getroot()
    failures: list[str] = []
    for case in root.iter("testcase"):
        if case.find("failure") is None and case.find("error") is None:
            continue
        classname = case.attrib.get("classname", "").strip()
        name = case.attrib.get("name", "").strip()
        node_id = f"{classname}::{name}" if classname else name
        if node_id and node_id not in failures:
            failures.append(node_id)
    return sorted(failures)


def parse_junit_metadata(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    nodes: list[str] = []
    passed: list[str] = []
    errors: list[str] = []
    skipped: list[str] = []
    for case in root.iter("testcase"):
        classname = case.attrib.get("classname", "").strip()
        name = case.attrib.get("name", "").strip()
        node = f"{classname}::{name}" if classname else name
        if not node or node in nodes:
            continue
        nodes.append(node)
        if case.find("skipped") is not None:
            skipped.append(node)
        elif case.find("error") is not None:
            errors.append(node)
        elif case.find("failure") is None:
            passed.append(node)
    return {
        "collection_count": len(nodes),
        "node_ids": sorted(nodes),
        "passed_node_ids": sorted(passed),
        "failed_node_ids": sorted(
            node
            for node in nodes
            if node not in passed and node not in errors and node not in skipped
        ),
        "error_node_ids": sorted(errors),
        "skipped_node_ids": sorted(skipped),
    }


def _logical_node_key(raw_node: str) -> LogicalNodeKey:
    """Abstract valid aware ISO datetimes only inside a pytest parameter id."""
    component_start = raw_node.rfind("::") + 2
    parameter_start = raw_node.find("[", component_start)
    if parameter_start < component_start or not raw_node.endswith("]"):
        return (("literal", raw_node),)

    parameter_id = raw_node[parameter_start + 1 : -1]
    segments: list[tuple[str, str]] = [("literal", raw_node[: parameter_start + 1])]
    cursor = 0
    normalized = False
    for match in _AWARE_ISO_DATETIME.finditer(parameter_id):
        token = match.group(0)
        try:
            parsed = datetime.fromisoformat(token[:-1] + "+00:00" if token.endswith("Z") else token)
        except ValueError:
            continue
        if parsed.utcoffset() is None:
            continue
        segments.append(("literal", parameter_id[cursor : match.start()]))
        segments.append(("aware_iso_datetime", ""))
        cursor = match.end()
        normalized = True
    if not normalized:
        return (("literal", raw_node),)
    segments.append(("literal", parameter_id[cursor:] + "]"))
    return tuple(segments)


def _logical_node_index(raw_nodes: Iterable[str]) -> dict[LogicalNodeKey, str] | None:
    index: dict[LogicalNodeKey, str] = {}
    for raw_node in raw_nodes:
        key = _logical_node_key(raw_node)
        if key in index and index[key] != raw_node:
            return None
        index[key] = raw_node
    return index


def _logical_node_set(raw_nodes: Iterable[str]) -> set[LogicalNodeKey] | None:
    index = _logical_node_index(raw_nodes)
    return None if index is None else set(index)


def _parameterized_family(raw_node: str) -> str | None:
    """Return the unparameterized pytest node name for a parameterized node."""
    component_start = raw_node.rfind("::") + 2
    parameter_start = raw_node.find("[", component_start)
    if parameter_start <= component_start or not raw_node.endswith("]"):
        return None
    return raw_node[:parameter_start]


def _expanded_node_keys(
    base: PytestRunResult,
    head: PytestRunResult,
    base_index: Mapping[LogicalNodeKey, str],
    head_index: Mapping[LogicalNodeKey, str],
) -> tuple[set[LogicalNodeKey], set[LogicalNodeKey], bool]:
    """Map unparameterized base nodes to their head parameterizations.

    Expansion is accepted only when the test inventory changed.  A retained
    unparameterized head node alongside parameterizations is ambiguous and is
    therefore rejected instead of being treated as a successful replacement.
    """
    if base.test_inventory_tree == head.test_inventory_tree:
        return set(), set(), False
    base_passed = _logical_node_set(base.passed_node_ids)
    if base_passed is None:
        return set(), set(), True
    head_by_family: dict[str, list[LogicalNodeKey]] = {}
    for key, raw_node in head_index.items():
        family = _parameterized_family(raw_node)
        if family is not None:
            head_by_family.setdefault(family, []).append(key)

    expanded_base: set[LogicalNodeKey] = set()
    expanded_head: set[LogicalNodeKey] = set()
    for base_key, raw_node in base_index.items():
        if base_key not in base_passed or _parameterized_family(raw_node) is not None:
            continue
        candidates = head_by_family.get(raw_node, [])
        if not candidates:
            continue
        if base_key in head_index:
            return set(), set(), True
        expanded_base.add(base_key)
        expanded_head.update(candidates)
    return expanded_base, expanded_head, False


def _metadata_mismatch(base: PytestRunResult, head: PytestRunResult) -> bool:
    base_index = _logical_node_index(base.node_ids)
    head_index = _logical_node_index(head.node_ids)
    base_passed = _logical_node_set(base.passed_node_ids)
    head_passed = _logical_node_set(head.passed_node_ids)
    base_skipped = _logical_node_set(base.skipped_node_ids)
    head_skipped = _logical_node_set(head.skipped_node_ids)
    head_failed = _logical_node_set(head.failed_node_ids)
    head_errors = _logical_node_set(head.error_node_ids)
    indexes = (
        base_index,
        head_index,
        base_passed,
        head_passed,
        base_skipped,
        head_skipped,
        head_failed,
        head_errors,
    )
    if any(index is None for index in indexes):
        return True

    assert base_index is not None and head_index is not None
    assert base_passed is not None and head_passed is not None
    assert base_skipped is not None and head_skipped is not None
    assert head_failed is not None and head_errors is not None
    base_nodes = set(base_index)
    head_nodes = set(head_index)
    if not base_nodes and not head_nodes:
        return False
    expanded_base, expanded_head, expansion_ambiguous = _expanded_node_keys(
        base, head, base_index, head_index
    )
    if expansion_ambiguous:
        return True
    if not base_nodes or not head_nodes or not (base_nodes - expanded_base) <= head_nodes:
        return True

    head_only = head_nodes - base_nodes
    if head_only and base.test_inventory_tree == head.test_inventory_tree:
        return True
    ordinary_head_only = head_only - expanded_head
    if not ordinary_head_only <= head_passed:
        return True
    expanded_nonpassing = expanded_head - head_passed
    if expanded_nonpassing - (head_failed | head_errors):
        return True
    if not head_skipped <= base_skipped:
        return True

    downgraded = (base_passed - expanded_base) - head_passed
    classified_failures = head_failed | head_errors
    return bool(downgraded - classified_failures)


def _valid_test_provenance(result: PytestRunResult) -> bool:
    partitions = (
        result.passed_node_ids,
        result.failed_node_ids,
        result.error_node_ids,
        result.skipped_node_ids,
    )
    node_ids = list(result.node_ids)
    target_fields = (
        result.selected_targets,
        result.executed_targets,
        result.missing_targets,
        result.unexpected_missing_targets,
    )
    if (
        result.status not in {"COMPLETE", "CI_BOOTSTRAP_DEFECT", "IMPACT_UNKNOWN"}
        or result.terminal_status != result.status
        or not result.impact_class
        or any(len(items) != len(set(items)) for items in target_fields)
        or set(result.executed_targets) & set(result.missing_targets)
        or set(result.executed_targets) | set(result.missing_targets)
        != set(result.selected_targets)
        or not set(result.unexpected_missing_targets) <= set(result.missing_targets)
        or len(result.failures) != len(set(result.failures))
        or result.collection_count < 0
        or len(node_ids) != result.collection_count
        or len(set(node_ids)) != len(node_ids)
        or any(len(items) != len(set(items)) for items in partitions)
        or any(set(items) - set(node_ids) for items in partitions)
        or sum(len(items) for items in partitions) != result.collection_count
        or set().union(*partitions) != set(node_ids)
        or any(
            set(left) & set(right)
            for index, left in enumerate(partitions)
            for right in partitions[index + 1 :]
        )
        or sorted(result.failures)
        != sorted(set(result.failed_node_ids) | set(result.error_node_ids))
        or (
            result.status == "COMPLETE"
            and (
                result.exit_code not in {0, 1}
                or (result.exit_code == 0 and result.failures)
                or (result.exit_code == 1 and not result.failures)
            )
        )
    ):
        return False
    try:
        expected = compute_test_provenance_digest(
            revision=result.revision,
            source_tree=result.source_tree,
            test_inventory_tree=result.test_inventory_tree,
            plan_digest=result.plan_digest,
            verifier_digest=result.verifier_digest,
            collection_count=result.collection_count,
            node_ids=result.node_ids,
            passed_node_ids=result.passed_node_ids,
            failed_node_ids=result.failed_node_ids,
            error_node_ids=result.error_node_ids,
            skipped_node_ids=result.skipped_node_ids,
            terminal_status=result.terminal_status,
            exit_code=result.exit_code,
            status=result.status,
            failures=result.failures,
            executed_targets=result.executed_targets,
            missing_targets=result.missing_targets,
            selected_targets=result.selected_targets,
            unexpected_missing_targets=result.unexpected_missing_targets,
            impact_class=result.impact_class,
        )
    except ValueError:
        return False
    return (
        bool(result.provenance_digest)
        and result.provenance_digest == expected
        and result.source_tree == result.bound_source_tree
        and result.test_inventory_tree == result.bound_test_inventory_tree
        and result.terminal_status == result.status
    )


def classify_regression(base: PytestRunResult, head: PytestRunResult) -> RegressionClassification:
    base_failures = sorted(set(base.failures))
    head_failures = sorted(set(head.failures))
    base_failure_index = _logical_node_index(base_failures)
    head_failure_index = _logical_node_index(head_failures)
    if base_failure_index is None or head_failure_index is None:
        new_failures = sorted(set(head_failures) - set(base_failures))
        resolved = sorted(set(base_failures) - set(head_failures))
        logical_failure_collision = True
    else:
        new_failures = sorted(
            raw for key, raw in head_failure_index.items() if key not in base_failure_index
        )
        resolved = sorted(
            raw for key, raw in base_failure_index.items() if key not in head_failure_index
        )
        logical_failure_collision = False

    evidence_mismatch = (
        logical_failure_collision
        or not base.plan_digest
        or base.plan_digest != head.plan_digest
        or base.selected_targets != head.selected_targets
        or not base.revision
        or not head.revision
        or bool(head.missing_targets)
        or bool(base.unexpected_missing_targets)
        or not base.verifier_digest
        or base.verifier_digest != head.verifier_digest
        or not _valid_test_provenance(base)
        or not _valid_test_provenance(head)
        or base.revision == head.revision
        or _metadata_mismatch(base, head)
        or base.status not in {"COMPLETE", "CI_BOOTSTRAP_DEFECT", "IMPACT_UNKNOWN"}
        or head.status not in {"COMPLETE", "CI_BOOTSTRAP_DEFECT", "IMPACT_UNKNOWN"}
        or (
            base.status == "COMPLETE"
            and (
                base.exit_code not in {0, 1}
                or (base.exit_code == 0 and bool(base_failures))
                or (base.exit_code == 1 and not base_failures)
            )
        )
        or (
            head.status == "COMPLETE"
            and (
                head.exit_code not in {0, 1}
                or (head.exit_code == 0 and bool(head_failures))
                or (head.exit_code == 1 and not head_failures)
            )
        )
        or sorted(set(base.executed_targets + base.missing_targets))
        != sorted(set(base.selected_targets))
        or sorted(set(head.executed_targets + head.missing_targets))
        != sorted(set(head.selected_targets))
        or base.impact_class == "IMPACT_UNKNOWN"
        or head.impact_class == "IMPACT_UNKNOWN"
    )
    if evidence_mismatch or base.status == "IMPACT_UNKNOWN" or head.status == "IMPACT_UNKNOWN":
        return RegressionClassification(
            "IMPACT_UNKNOWN",
            True,
            base_failures,
            head_failures,
            new_failures,
            resolved,
            "test execution metadata did not prove a trustworthy exact-base comparison",
        )
    if head.exit_code == 0 and head.status == "COMPLETE":
        return RegressionClassification(
            "PASS",
            False,
            base_failures,
            head_failures,
            [],
            resolved,
            "exact head verification passed",
        )
    if base.status == "CI_BOOTSTRAP_DEFECT" or head.status == "CI_BOOTSTRAP_DEFECT":
        return RegressionClassification(
            "CI_BOOTSTRAP_DEFECT",
            True,
            base_failures,
            head_failures,
            new_failures,
            resolved,
            "pytest collection, configuration, or evidence generation failed",
        )
    if base.exit_code == 0 or new_failures:
        return RegressionClassification(
            "NEW_REGRESSION",
            True,
            base_failures,
            head_failures,
            new_failures,
            resolved,
            "exact head introduced failures absent from exact base",
        )
    return RegressionClassification(
        "EXACT_BASELINE_DEBT",
        False,
        base_failures,
        head_failures,
        [],
        resolved,
        "exact head did not add to the exact base failure set",
    )


def _git_changed_paths(base_sha: str, head_sha: str, *, root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", base_sha, head_sha],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git diff failed")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _validate_optional_browser_exclusion(cwd: Path) -> str | None:
    """Return a diagnostic when the exact optional exclusion is unsafe."""
    try:
        resolved_cwd = cwd.resolve(strict=True)
        exclusion = cwd / OPTIONAL_BROWSER_EXCLUSION
        resolved_exclusion = exclusion.resolve(strict=True)
    except (OSError, RuntimeError):
        return f"missing declared optional exclusion: {OPTIONAL_BROWSER_EXCLUSION}"
    if exclusion.is_symlink():
        return f"declared optional exclusion must not be a symlink: {OPTIONAL_BROWSER_EXCLUSION}"
    try:
        resolved_exclusion.relative_to(resolved_cwd)
    except ValueError:
        return f"declared optional exclusion resolves outside cwd: {OPTIONAL_BROWSER_EXCLUSION}"
    if not resolved_exclusion.is_file():
        return f"declared optional exclusion is not a regular file: {OPTIONAL_BROWSER_EXCLUSION}"
    return None


def run_pytest_plan(
    plan_path: Path,
    result_path: Path,
    junit_path: Path,
    stdout_path: Path,
    *,
    cwd: Path,
    revision: str,
) -> int:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan_digest = hashlib.sha256(
        json.dumps(plan, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    verifier_digest = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    targets = [str(item) for item in plan.get("pytest_targets", []) if str(item).strip()]
    impact_class = str(plan.get("impact_class", "IMPACT_UNKNOWN"))
    existing_targets = [target for target in targets if (cwd / target.split("::", 1)[0]).exists()]
    missing_targets = [target for target in targets if target not in existing_targets]
    changed_paths = {str(path) for path in plan.get("changed_paths", [])}
    base_revision = str(plan.get("base_sha", ""))
    head_revision = str(plan.get("head_sha", ""))
    expected_source_tree = ""
    expected_test_inventory_tree = ""
    provenance_failure = ""
    if revision == base_revision:
        expected_source_tree = str(plan.get("base_source_tree", ""))
        expected_test_inventory_tree = str(plan.get("base_test_inventory_tree", ""))
    elif revision == head_revision:
        expected_source_tree = str(plan.get("source_tree", ""))
        expected_test_inventory_tree = str(plan.get("test_inventory_tree", ""))
    else:
        provenance_failure = "run revision is not an exact plan endpoint"
    source_tree = ""
    test_inventory_tree = ""
    provenance_digest = ""
    if not provenance_failure:
        try:
            source_tree, test_inventory_tree = _git_revision_trees(cwd, revision)
            if (
                source_tree != expected_source_tree
                or test_inventory_tree != expected_test_inventory_tree
            ):
                provenance_failure = "run trees drifted from the immutable plan binding"
        except ValueError as exc:
            provenance_failure = str(exc)
    unexpected_missing = [
        target
        for target in missing_targets
        if not (
            revision == base_revision
            and target.split("::", 1)[0] in changed_paths
            and target.split("::", 1)[0].startswith("tests/")
        )
    ]
    if provenance_failure:
        stdout_path.write_text(provenance_failure + "\n", encoding="utf-8")
        result = PytestRunResult(
            5,
            "IMPACT_UNKNOWN",
            [],
            str(junit_path),
            str(stdout_path),
            revision=revision,
            plan_digest=plan_digest,
            selected_targets=targets,
            impact_class="IMPACT_UNKNOWN",
            unexpected_missing_targets=unexpected_missing,
            verifier_digest=verifier_digest,
            source_tree=source_tree,
            test_inventory_tree=test_inventory_tree,
            bound_source_tree=expected_source_tree,
            bound_test_inventory_tree=expected_test_inventory_tree,
            terminal_status="IMPACT_UNKNOWN",
            provenance_digest=provenance_digest,
        )
        result_path.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
        return 5
    if not targets:
        result = PytestRunResult(
            5,
            "IMPACT_UNKNOWN",
            [],
            str(junit_path),
            str(stdout_path),
            revision=revision,
            plan_digest=plan_digest,
            selected_targets=targets,
            impact_class=impact_class,
            unexpected_missing_targets=unexpected_missing,
            verifier_digest=verifier_digest,
            source_tree=source_tree,
            test_inventory_tree=test_inventory_tree,
            bound_source_tree=expected_source_tree,
            bound_test_inventory_tree=expected_test_inventory_tree,
            terminal_status="IMPACT_UNKNOWN",
            provenance_digest=provenance_digest,
        )
        result_path.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
        return 5
    if not existing_targets:
        stdout_path.write_text(
            "No selected targets exist at this revision; treated as an empty exact-base comparison.\n",
            encoding="utf-8",
        )
        result = PytestRunResult(
            0,
            "COMPLETE",
            [],
            str(junit_path),
            str(stdout_path),
            executed_targets=[],
            missing_targets=missing_targets,
            revision=revision,
            plan_digest=plan_digest,
            selected_targets=targets,
            impact_class=impact_class,
            unexpected_missing_targets=unexpected_missing,
            verifier_digest=verifier_digest,
            source_tree=source_tree,
            test_inventory_tree=test_inventory_tree,
            bound_source_tree=expected_source_tree,
            bound_test_inventory_tree=expected_test_inventory_tree,
            terminal_status="COMPLETE",
            provenance_digest=compute_test_provenance_digest(
                revision=revision,
                source_tree=source_tree,
                test_inventory_tree=test_inventory_tree,
                plan_digest=plan_digest,
                verifier_digest=verifier_digest,
                terminal_status="COMPLETE",
                exit_code=0,
                status="COMPLETE",
                executed_targets=[],
                missing_targets=missing_targets,
                selected_targets=targets,
                unexpected_missing_targets=unexpected_missing,
                impact_class=impact_class,
            ),
        )
        result_path.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
        return 0
    if "tests/core" in existing_targets:
        diagnostic = _validate_optional_browser_exclusion(cwd)
        if diagnostic is not None:
            diagnostic += "\n"
            stdout_path.write_text(diagnostic, encoding="utf-8")
            status = "CI_BOOTSTRAP_DEFECT"
            result = PytestRunResult(
                2,
                status,
                [],
                str(junit_path),
                str(stdout_path),
                executed_targets=existing_targets,
                missing_targets=missing_targets,
                revision=revision,
                plan_digest=plan_digest,
                selected_targets=targets,
                impact_class=impact_class,
                unexpected_missing_targets=unexpected_missing,
                verifier_digest=verifier_digest,
                source_tree=source_tree,
                test_inventory_tree=test_inventory_tree,
                bound_source_tree=expected_source_tree,
                bound_test_inventory_tree=expected_test_inventory_tree,
                collection_count=0,
                node_ids=[],
                passed_node_ids=[],
                failed_node_ids=[],
                error_node_ids=[],
                skipped_node_ids=[],
                terminal_status=status,
                provenance_digest=compute_test_provenance_digest(
                    revision=revision,
                    source_tree=source_tree,
                    test_inventory_tree=test_inventory_tree,
                    plan_digest=plan_digest,
                    verifier_digest=verifier_digest,
                    collection_count=0,
                    node_ids=[],
                    passed_node_ids=[],
                    failed_node_ids=[],
                    error_node_ids=[],
                    skipped_node_ids=[],
                    terminal_status=status,
                    exit_code=2,
                    status=status,
                    failures=[],
                    executed_targets=existing_targets,
                    missing_targets=missing_targets,
                    selected_targets=targets,
                    unexpected_missing_targets=unexpected_missing,
                    impact_class=impact_class,
                ),
            )
            result_path.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
            return 2
    pytest_args = list(existing_targets)
    if "tests/core" in existing_targets:
        pytest_args.append(f"--ignore={OPTIONAL_BROWSER_EXCLUSION}")
    command = [sys.executable, "-m", "pytest", *pytest_args, "-q", f"--junitxml={junit_path}"]
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    stdout_path.write_text(completed.stdout + completed.stderr, encoding="utf-8")
    status = (
        "COMPLETE"
        if completed.returncode in {0, 1} and junit_path.exists()
        else "CI_BOOTSTRAP_DEFECT"
    )
    try:
        failures = parse_junit_failures(junit_path) if status == "COMPLETE" else []
        metadata = parse_junit_metadata(junit_path) if status == "COMPLETE" else {}
    except (ET.ParseError, OSError):
        failures = []
        metadata = {}
        status = "CI_BOOTSTRAP_DEFECT"
    result = PytestRunResult(
        completed.returncode,
        status,
        failures,
        str(junit_path),
        str(stdout_path),
        executed_targets=existing_targets,
        missing_targets=missing_targets,
        revision=revision,
        plan_digest=plan_digest,
        selected_targets=targets,
        impact_class=impact_class,
        unexpected_missing_targets=unexpected_missing,
        verifier_digest=verifier_digest,
        source_tree=source_tree,
        test_inventory_tree=test_inventory_tree,
        bound_source_tree=expected_source_tree,
        bound_test_inventory_tree=expected_test_inventory_tree,
        collection_count=int(metadata.get("collection_count", 0)),
        node_ids=list(metadata.get("node_ids", [])),
        passed_node_ids=list(metadata.get("passed_node_ids", [])),
        failed_node_ids=list(metadata.get("failed_node_ids", [])),
        error_node_ids=list(metadata.get("error_node_ids", [])),
        skipped_node_ids=list(metadata.get("skipped_node_ids", [])),
        terminal_status=status,
        provenance_digest=compute_test_provenance_digest(
            revision=revision,
            source_tree=source_tree,
            test_inventory_tree=test_inventory_tree,
            plan_digest=plan_digest,
            verifier_digest=verifier_digest,
            collection_count=int(metadata.get("collection_count", 0)),
            node_ids=list(metadata.get("node_ids", [])),
            passed_node_ids=list(metadata.get("passed_node_ids", [])),
            failed_node_ids=list(metadata.get("failed_node_ids", [])),
            error_node_ids=list(metadata.get("error_node_ids", [])),
            skipped_node_ids=list(metadata.get("skipped_node_ids", [])),
            terminal_status=status,
            exit_code=completed.returncode,
            status=status,
            failures=failures,
            executed_targets=existing_targets,
            missing_targets=missing_targets,
            selected_targets=targets,
            unexpected_missing_targets=unexpected_missing,
            impact_class=impact_class,
        ),
    )
    result_path.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
    return 0 if status == "COMPLETE" else completed.returncode or 2


def _load_run_result(path: Path) -> PytestRunResult:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return PytestRunResult(
        exit_code=int(payload["exit_code"]),
        status=str(payload["status"]),
        failures=[str(item) for item in payload.get("failures", [])],
        junit_path=str(payload.get("junit_path", "")),
        stdout_path=str(payload.get("stdout_path", "")),
        executed_targets=[str(item) for item in payload.get("executed_targets", [])],
        missing_targets=[str(item) for item in payload.get("missing_targets", [])],
        revision=str(payload.get("revision", "")),
        plan_digest=str(payload.get("plan_digest", "")),
        selected_targets=[str(item) for item in payload.get("selected_targets", [])],
        impact_class=str(payload.get("impact_class", "")),
        unexpected_missing_targets=[
            str(item) for item in payload.get("unexpected_missing_targets", [])
        ],
        verifier_digest=str(payload.get("verifier_digest", "")),
        source_tree=str(payload.get("source_tree", "")),
        test_inventory_tree=str(payload.get("test_inventory_tree", "")),
        bound_source_tree=str(payload.get("bound_source_tree", "")),
        bound_test_inventory_tree=str(payload.get("bound_test_inventory_tree", "")),
        collection_count=int(payload.get("collection_count", 0)),
        node_ids=[str(item) for item in payload.get("node_ids", [])],
        passed_node_ids=[str(item) for item in payload.get("passed_node_ids", [])],
        failed_node_ids=[str(item) for item in payload.get("failed_node_ids", [])],
        error_node_ids=[str(item) for item in payload.get("error_node_ids", [])],
        skipped_node_ids=[str(item) for item in payload.get("skipped_node_ids", [])],
        terminal_status=str(payload.get("terminal_status", "")),
        provenance_digest=str(payload.get("provenance_digest", "")),
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    plan = subparsers.add_parser("plan")
    plan.add_argument("--base-sha", required=True)
    plan.add_argument("--head-sha", required=True)
    plan.add_argument("--output", type=Path, required=True)

    run = subparsers.add_parser("run")
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--result", type=Path, required=True)
    run.add_argument("--junit", type=Path, required=True)
    run.add_argument("--stdout", type=Path, required=True)
    run.add_argument("--cwd", type=Path, default=ROOT)
    run.add_argument("--revision", required=True)

    classify = subparsers.add_parser("classify")
    classify.add_argument("--base-result", type=Path, required=True)
    classify.add_argument("--head-result", type=Path, required=True)
    classify.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "plan":
        changed = _git_changed_paths(args.base_sha, args.head_sha, root=ROOT)
        payload = asdict(build_impact_plan(changed, base_sha=args.base_sha, head_sha=args.head_sha))
        args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(payload, indent=2))
        return 0
    if args.command == "run":
        return run_pytest_plan(
            args.plan,
            args.result,
            args.junit,
            args.stdout,
            cwd=args.cwd,
            revision=args.revision,
        )

    classification = classify_regression(
        _load_run_result(args.base_result), _load_run_result(args.head_result)
    )
    payload = asdict(classification)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 1 if classification.blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
