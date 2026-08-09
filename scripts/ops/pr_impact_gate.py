#!/usr/bin/env python3
"""Exact-base, tiered PR verification planner and regression classifier."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[2]
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


@dataclass(frozen=True)
class RegressionClassification:
    classification: str
    blocking: bool
    base_failures: list[str]
    head_failures: list[str]
    new_failures: list[str]
    resolved_failures: list[str]
    reason: str


def _unique_existing(targets: Iterable[str], *, root: Path = ROOT) -> list[str]:
    selected: list[str] = []
    for target in targets:
        path_part = target.split("::", 1)[0]
        if (root / path_part).exists() and target not in selected:
            selected.append(target)
    return selected


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
    normalized = sorted(
        {path.strip().replace("\\", "/").strip("/") for path in changed_paths if path.strip()}
    )
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
            reasons=["empty exact-base diff is not a valid PR impact packet"],
            unmatched_paths=[],
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
    details = select_target_details(normalized, load_impact_rules())
    unknown_unmatched = [
        path
        for path in details.unmatched_paths
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

    targets = list(details.targets)
    reasons = list(details.reasons)
    impact_class = "SCOPED_IMPLEMENTATION"
    tier = 1
    confidence = details.confidence

    if docs_only:
        impact_class = "DOCS_GOVERNANCE"
        mapped_docs_targets = [] if details.fallback_used else targets
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
    elif dependency_change or sensitive_change or contract_change or details.high_risk_escalated:
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


def classify_regression(base: PytestRunResult, head: PytestRunResult) -> RegressionClassification:
    base_failures = sorted(set(base.failures))
    head_failures = sorted(set(head.failures))
    new_failures = sorted(set(head_failures) - set(base_failures))
    resolved = sorted(set(base_failures) - set(head_failures))

    evidence_mismatch = (
        not base.plan_digest
        or base.plan_digest != head.plan_digest
        or base.selected_targets != head.selected_targets
        or not base.revision
        or not head.revision
        or bool(head.missing_targets)
        or bool(base.unexpected_missing_targets)
        or not base.verifier_digest
        or base.verifier_digest != head.verifier_digest
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
    unexpected_missing = [
        target
        for target in missing_targets
        if not (
            revision == base_revision
            and target.split("::", 1)[0] in changed_paths
            and target.split("::", 1)[0].startswith("tests/")
        )
    ]
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
        )
        result_path.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
        return 0
    command = [sys.executable, "-m", "pytest", *existing_targets, "-q", f"--junitxml={junit_path}"]
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)
    stdout_path.write_text(completed.stdout + completed.stderr, encoding="utf-8")
    status = (
        "COMPLETE"
        if completed.returncode in {0, 1} and junit_path.exists()
        else "CI_BOOTSTRAP_DEFECT"
    )
    try:
        failures = parse_junit_failures(junit_path) if status == "COMPLETE" else []
    except (ET.ParseError, OSError):
        failures = []
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
