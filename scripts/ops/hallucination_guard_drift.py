#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nexus.core.hallucination_guard import HallucinationGuard

DEFAULT_SCHEMA = REPO_ROOT / "nexus" / "schemas" / "hallucination_index_v1.json"
DEFAULT_ALIGNMENT_DOC = REPO_ROOT / "wiki" / "critique_brain_hub_alignment_gap.md"
DEFAULT_SCORING_SPEC = REPO_ROOT / "nexus_wiki_vault" / "07_Compliance" / "Hallucination_Guard_Scoring_Spec.md"
REQUIRED_CHECKS = {
    "claim_completion_with_low_success",
    "contradiction_with_failed_artifacts",
    "logic_mismatch",
    "verified_claim_without_evidence",
}
DOC_FEATURE_MARKERS = {
    "logic_mismatch": ("logic mismatch", "邏輯", "mismatch"),
    "verified_claim_without_evidence": ("verified claim", "驗證", "evidence"),
}
SCORING_SPEC_RULE_MAP = {
    "evidence gap": "evidence_gap",
    "benchmark fail": "contradiction_with_failed_artifacts",
    "logic mismatch": "logic_mismatch",
    "verified claim": "verified_claim_without_evidence",
}


@dataclass(frozen=True)
class DriftAudit:
    schema_checks: list[str]
    runtime_checks: list[str]
    runtime_probes: dict[str, bool]
    required_checks: list[str]
    doc_features: dict[str, bool]
    scoring_spec_rules: dict[str, dict[str, Any]]
    failures: list[dict[str, Any]] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


def _schema_checks(schema: dict[str, Any]) -> list[str]:
    checks = []
    for metric in schema.get("metrics", {}).values():
        if isinstance(metric, dict) and metric.get("check"):
            checks.append(str(metric["check"]))
    return sorted(set(checks))


def _runtime_checks(guard: HallucinationGuard) -> list[str]:
    return sorted(
        name.removeprefix("_check_")
        for name in dir(guard)
        if name.startswith("_check_") and callable(getattr(guard, name))
    )


def _doc_features(path: Path) -> dict[str, bool]:
    if not path.exists():
        return {feature: False for feature in DOC_FEATURE_MARKERS}
    text = path.read_text(encoding="utf-8").lower()
    return {
        feature: all(marker.lower() in text for marker in markers)
        for feature, markers in DOC_FEATURE_MARKERS.items()
    }


def _runtime_probes(guard: HallucinationGuard) -> dict[str, bool]:
    rejected = guard.analyze(
        "The runtime matches the contract.",
        {
            "code_artifacts": ["nexus/core/hallucination_guard.py"],
            "logic_checks": [
                {
                    "expected": "deny_by_default",
                    "actual": "allow_by_default",
                    "operator": "equals",
                }
            ],
        },
    )
    allowed = guard.analyze(
        "The runtime matches the contract.",
        {
            "code_artifacts": ["nexus/core/hallucination_guard.py"],
            "logic_checks": [
                {
                    "expected": "deny_by_default",
                    "actual": "deny_by_default",
                    "operator": "equals",
                }
            ],
        },
    )
    return {
        "logic_mismatch_hard_rejects": "logic_mismatch" in rejected.get("triggers", []),
        "logic_mismatch_allows_match": "logic_mismatch" not in allowed.get("triggers", []),
    }


def _parse_boolish_hard_block(text: str) -> bool | None:
    normalized = text.strip().strip("*[]").lower()
    if not normalized or normalized == "-":
        return None
    if "force_rejected" in normalized or normalized in {"yes", "true", "hard"}:
        return True
    if normalized in {"no", "false", "none"}:
        return False
    return None


def _parse_scoring_spec(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    rules: dict[str, dict[str, Any]] = {}
    row_re = re.compile(r"^\|\s*\*\*(?P<name>[^*]+)\*\*\s*\|[^|]*\|\s*\*\*(?P<weight>[+-]?[0-9]+(?:\.[0-9]+)?)\*\*\s*\|\s*(?P<hard>[^|]+)\|")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = row_re.match(line)
        if not match:
            continue
        display = match.group("name").strip()
        rule_id = SCORING_SPEC_RULE_MAP.get(display.lower())
        if not rule_id:
            continue
        hard_block = _parse_boolish_hard_block(match.group("hard"))
        rules[rule_id] = {
            "display_name": display,
            "weight": abs(float(match.group("weight"))),
            "hard_block": hard_block,
        }
    return rules


def _scoring_spec_failures(
    *,
    schema: dict[str, Any],
    scoring_spec: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    metrics = schema.get("metrics", {}) if isinstance(schema.get("metrics"), dict) else {}
    thresholds = schema.get("thresholds", {}) if isinstance(schema.get("thresholds"), dict) else {}
    rejected_threshold = float(thresholds.get("REJECTED", 6) or 6)
    for rule_id in sorted(SCORING_SPEC_RULE_MAP.values()):
        metric = metrics.get(rule_id)
        spec = scoring_spec.get(rule_id)
        if not isinstance(metric, dict):
            failures.append({"reason": "scoring_spec_rule_missing_schema", "rule_id": rule_id})
            continue
        if not spec:
            failures.append({"reason": "schema_rule_missing_scoring_spec", "rule_id": rule_id})
            continue
        schema_weight = abs(float(metric.get("weight", 0) or 0))
        if schema_weight != float(spec.get("weight", 0) or 0):
            failures.append(
                {
                    "reason": "scoring_spec_weight_mismatch",
                    "rule_id": rule_id,
                    "schema_weight": schema_weight,
                    "spec_weight": spec.get("weight"),
                }
            )
        spec_hard = spec.get("hard_block")
        if spec_hard is not None:
            schema_hard = bool(metric.get("force_rejected", False) or schema_weight >= rejected_threshold)
            if bool(spec_hard) != schema_hard:
                failures.append(
                    {
                        "reason": "scoring_spec_hard_block_mismatch",
                        "rule_id": rule_id,
                        "schema_hard_block": schema_hard,
                        "spec_hard_block": spec_hard,
                    }
                )
    return failures


def audit_drift(
    *,
    schema_path: Path = DEFAULT_SCHEMA,
    alignment_doc: Path = DEFAULT_ALIGNMENT_DOC,
    scoring_spec: Path = DEFAULT_SCORING_SPEC,
    guard_factory: Any | None = None,
) -> DriftAudit:
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    guard = guard_factory(schema_path=schema_path) if guard_factory is not None else HallucinationGuard(schema_path=schema_path)
    schema_checks = _schema_checks(schema)
    runtime_checks = _runtime_checks(guard)
    runtime_probes = _runtime_probes(guard)
    doc_features = _doc_features(alignment_doc)
    scoring_spec_rules = _parse_scoring_spec(scoring_spec)
    failures: list[dict[str, Any]] = []

    for check in schema_checks:
        if check not in runtime_checks:
            failures.append({"reason": "schema_check_missing_runtime_method", "check": check})
    for check in sorted(REQUIRED_CHECKS):
        if check not in schema_checks:
            failures.append({"reason": "required_check_missing_schema", "check": check})
        if check not in runtime_checks:
            failures.append({"reason": "required_check_missing_runtime", "check": check})
    for feature, documented in doc_features.items():
        if documented and feature not in schema_checks:
            failures.append({"reason": "documented_feature_missing_schema", "feature": feature})
        if documented and feature not in runtime_checks:
            failures.append({"reason": "documented_feature_missing_runtime", "feature": feature})
    for probe, passed in runtime_probes.items():
        if not passed:
            failures.append({"reason": "runtime_probe_failed", "probe": probe})
    failures.extend(_scoring_spec_failures(schema=schema, scoring_spec=scoring_spec_rules))

    return DriftAudit(
        schema_checks=schema_checks,
        runtime_checks=runtime_checks,
        runtime_probes=runtime_probes,
        required_checks=sorted(REQUIRED_CHECKS),
        doc_features=doc_features,
        scoring_spec_rules=scoring_spec_rules,
        failures=failures,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit HallucinationGuard schema/runtime/wiki alignment.")
    parser.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    parser.add_argument("--alignment-doc", default=str(DEFAULT_ALIGNMENT_DOC))
    parser.add_argument("--scoring-spec", default=str(DEFAULT_SCORING_SPEC))
    parser.add_argument("--output-json", action="store_true", help="Compatibility flag; this command always emits JSON.")
    args = parser.parse_args(argv)

    audit = audit_drift(schema_path=Path(args.schema), alignment_doc=Path(args.alignment_doc), scoring_spec=Path(args.scoring_spec))
    print(json.dumps({"schema_version": "nexus_hallucination_guard_drift.v1", "passed": audit.passed, **asdict(audit)}, indent=2, ensure_ascii=False))
    return 0 if audit.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
