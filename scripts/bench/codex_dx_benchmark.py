#!/usr/bin/env python3
"""Validate and compare fail-closed Codex repository-DX benchmark receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

TASK_CLASSES = {"orientation", "setup", "focused_test", "bounded_change", "verification"}
BENCHMARK_REPO = "James3014/Nexus-new"
BEFORE_COMMIT = "b6601270edd95a756c4eab8c7a623006ee1b32d1"
SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs/benchmark/codex_dx_benchmark_receipt_v1.schema.json"
)
TRIAL_REQUIRED = {
    "trial_id",
    "task_id",
    "repetition",
    "session_id",
    "fresh_context",
    "source_commit",
    "fixture_sha256",
    "verifier_id",
    "verifier_status",
    "verifier_artifact",
    "valid",
    "invalid_reasons",
    "context",
    "tool_calls",
    "wall_time_seconds",
    "human_interventions",
    "secret_reads",
    "unauthorized_actions",
    "diff",
    "outcome",
}


class ReceiptError(ValueError):
    """Raised when a receipt cannot support a benchmark claim."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ReceiptError(message)


def task_fixture_sha256(task: dict[str, Any]) -> str:
    contract = {key: value for key, value in task.items() if key != "fixture_sha256"}
    encoded = json.dumps(
        contract, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReceiptError(f"cannot load receipt {path}: {exc}") from exc
    _require(isinstance(value, dict), "receipt root must be an object")
    return value


def _schema_type_matches(value: Any, declared: str) -> bool:
    if declared == "object":
        return isinstance(value, dict)
    if declared == "array":
        return isinstance(value, list)
    if declared == "string":
        return isinstance(value, str)
    if declared == "boolean":
        return isinstance(value, bool)
    if declared == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if declared == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False


def _apply_schema(value: Any, rule: dict[str, Any], root: dict[str, Any], path: str) -> None:
    reference = rule.get("$ref")
    if reference:
        _require(reference.startswith("#/$defs/"), f"unsupported schema reference at {path}")
        _apply_schema(value, root["$defs"][reference.removeprefix("#/$defs/")], root, path)
        return
    if "const" in rule:
        _require(value == rule["const"], f"schema const mismatch at {path}")
    if "enum" in rule:
        _require(value in rule["enum"], f"schema enum mismatch at {path}")
    declared_type = rule.get("type")
    if declared_type:
        _require(_schema_type_matches(value, declared_type), f"schema type mismatch at {path}")
    if isinstance(value, dict):
        required = set(rule.get("required", []))
        _require(required <= value.keys(), f"schema required field missing at {path}")
        properties = rule.get("properties", {})
        if rule.get("additionalProperties") is False:
            extras = set(value) - set(properties)
            _require(not extras, f"schema additional property at {path}: {sorted(extras)}")
        for key, child in value.items():
            if key in properties:
                _apply_schema(child, properties[key], root, f"{path}.{key}")
    if isinstance(value, list):
        _require(len(value) >= int(rule.get("minItems", 0)), f"schema minItems at {path}")
        if "maxItems" in rule:
            _require(len(value) <= int(rule["maxItems"]), f"schema maxItems at {path}")
        if rule.get("uniqueItems"):
            canonical = [json.dumps(item, sort_keys=True, ensure_ascii=False) for item in value]
            _require(len(canonical) == len(set(canonical)), f"schema uniqueItems at {path}")
        item_rule = rule.get("items")
        if item_rule:
            for index, item in enumerate(value):
                _apply_schema(item, item_rule, root, f"{path}[{index}]")
    if isinstance(value, str):
        _require(len(value) >= int(rule.get("minLength", 0)), f"schema minLength at {path}")
        if "pattern" in rule:
            _require(re.search(rule["pattern"], value) is not None, f"schema pattern at {path}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in rule:
            _require(value >= rule["minimum"], f"schema minimum at {path}")
        if "maximum" in rule:
            _require(value <= rule["maximum"], f"schema maximum at {path}")


def _validate_declared_schema(receipt: dict[str, Any]) -> None:
    schema = _load(SCHEMA_PATH)
    _apply_schema(receipt, schema, schema, "receipt")


def validate_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    """Validate one arm and return its deterministic aggregate."""
    _validate_declared_schema(receipt)
    required = {
        "schema_version",
        "benchmark_id",
        "frozen",
        "arm",
        "source",
        "protocol",
        "tasks",
        "trials",
        "session_artifacts",
        "baseline_evidence",
    }
    _require(required <= receipt.keys(), f"missing receipt fields: {sorted(required - receipt.keys())}")
    _require(receipt["schema_version"] == "codex-dx-benchmark-receipt-v1", "unsupported schema_version")
    _require(receipt["frozen"] is True, "benchmark arm must be frozen")
    _require(receipt["arm"] in {"before", "after"}, "arm must be before or after")

    source = receipt["source"]
    _require(isinstance(source, dict), "source must be an object")
    _require(isinstance(source.get("commit"), str) and len(source["commit"]) == 40, "source.commit must be a full SHA")
    _require(source.get("mutable") is False, "source must be immutable")
    _require(source.get("repo") == BENCHMARK_REPO, "benchmark repository identity mismatch")
    if receipt["arm"] == "before":
        _require(source["commit"] == BEFORE_COMMIT, "before arm must bind frozen b660 source")
        evidence_ids = {row["id"] for row in receipt["baseline_evidence"]}
        _require(
            evidence_ids
            == {"missing-benchmark-runner", "codex-task-history-transport"},
            "before arm requires both frozen baseline evidence records",
        )

    protocol = receipt["protocol"]
    _require(protocol.get("repetitions") == 3, "protocol must freeze three repetitions")
    _require(set(protocol.get("task_classes", [])) == TASK_CLASSES, "protocol must freeze the five task classes")
    _require(bool(protocol.get("model_id")), "protocol.model_id is required")
    _require(bool(protocol.get("verifier_version")), "protocol.verifier_version is required")
    _require(protocol.get("fresh_session_required") is True, "fresh_session_required must be true")

    artifact_by_repetition: dict[int, dict[str, Any]] = {}
    artifact_session_ids: set[str] = set()
    session_artifacts = receipt["session_artifacts"]
    _require(
        isinstance(session_artifacts, list) and len(session_artifacts) == 3,
        "exactly three session artifacts are required",
    )
    for artifact in session_artifacts:
        _require(
            set(artifact)
            == {"session_id", "repetition", "model_id", "source_commit", "sha256", "payload"},
            "session artifact fields are incomplete",
        )
        repetition = artifact["repetition"]
        _require(repetition in {1, 2, 3}, "session artifact repetition must be 1, 2, or 3")
        _require(repetition not in artifact_by_repetition, "duplicate session artifact repetition")
        _require(
            isinstance(artifact["session_id"], str)
            and bool(artifact["session_id"])
            and artifact["session_id"] not in artifact_session_ids,
            "distinct session artifact ids are required",
        )
        artifact_session_ids.add(artifact["session_id"])
        _require(artifact["model_id"] == protocol["model_id"], "session artifact model mismatch")
        _require(artifact["source_commit"] == source["commit"], "session artifact source mismatch")
        payload = artifact["payload"]
        payload_bytes = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        _require(
            hashlib.sha256(payload_bytes).hexdigest() == artifact["sha256"],
            "session artifact hash mismatch",
        )
        _require(payload.get("session_model") == protocol["model_id"], "payload model mismatch")
        payload_trials = payload.get("trials")
        _require(isinstance(payload_trials, list) and len(payload_trials) == 5, "artifact needs five trials")
        _require(
            {trial.get("task_class") for trial in payload_trials} == TASK_CLASSES,
            "artifact must cover five task classes",
        )
        artifact_by_repetition[repetition] = artifact

    tasks = receipt["tasks"]
    _require(isinstance(tasks, list) and len(tasks) == 5, "exactly five tasks are required")
    task_by_id: dict[str, dict[str, Any]] = {}
    for task in tasks:
        for field in ("id", "task_class", "prompt", "fixture_sha256", "verifier_id", "verifier_command"):
            _require(field in task, f"task missing {field}")
        _require(task["task_class"] in TASK_CLASSES, f"unknown task class {task['task_class']}")
        _require(
            task["fixture_sha256"] == task_fixture_sha256(task),
            f"task {task['id']} fixture_sha256 does not bind its contract",
        )
        _require(task["id"] not in task_by_id, f"duplicate task id {task['id']}")
        task_by_id[task["id"]] = task
    _require({task["task_class"] for task in tasks} == TASK_CLASSES, "tasks must cover each class once")

    trials = receipt["trials"]
    _require(isinstance(trials, list) and len(trials) == 15, "exactly 15 trials are required")
    seen_trial_ids: set[str] = set()
    seen_pairs: set[tuple[str, int]] = set()
    valid_session_by_repetition: dict[int, str] = {}
    class_counts: Counter[str] = Counter()
    invalid_reason_counts: Counter[str] = Counter()
    observed_outcome_counts: Counter[str] = Counter()
    valid_context_bytes: list[int] = []
    passed = 0

    for trial in trials:
        missing = TRIAL_REQUIRED - trial.keys()
        _require(not missing, f"trial missing fields: {sorted(missing)}")
        task = task_by_id.get(trial["task_id"])
        _require(task is not None, f"unknown task_id {trial['task_id']}")
        _require(trial["trial_id"] not in seen_trial_ids, f"duplicate trial_id {trial['trial_id']}")
        seen_trial_ids.add(trial["trial_id"])
        pair = (trial["task_id"], trial["repetition"])
        _require(pair not in seen_pairs, f"duplicate task repetition {pair}")
        seen_pairs.add(pair)
        _require(trial["repetition"] in {1, 2, 3}, "repetition must be 1, 2, or 3")
        _require(trial["source_commit"] == source["commit"], "trial source does not match arm source")
        _require(trial["fixture_sha256"] == task["fixture_sha256"], "trial fixture does not match task")
        _require(trial["verifier_id"] == task["verifier_id"], "trial verifier does not match task")
        _require(trial["verifier_status"] in {"passed", "failed", "not_run"}, "invalid verifier_status")
        _require(isinstance(trial["verifier_artifact"], dict), "verifier_artifact must be an object")
        _require(isinstance(trial["context"], dict), "trial.context must be an object")
        _require(set(trial["context"]) == {"bytes", "items"}, "context must contain only bytes and items")
        _require(all(isinstance(trial["context"][key], int) and trial["context"][key] >= 0 for key in ("bytes", "items")), "context metrics must be non-negative integers")
        _require(isinstance(trial["invalid_reasons"], list), "invalid_reasons must be a list")
        _require(
            isinstance(trial["diff"], dict)
            and set(trial["diff"]) == {"changed_files", "within_scope"}
            and isinstance(trial["diff"]["changed_files"], list)
            and isinstance(trial["diff"]["within_scope"], bool),
            "complete diff evidence is required",
        )
        class_counts[task["task_class"]] += 1
        observed_outcome_counts[trial["outcome"]] += 1

        if trial["valid"]:
            artifact = artifact_by_repetition[trial["repetition"]]
            payload_trial = next(
                row
                for row in artifact["payload"]["trials"]
                if row["task_class"] == task["task_class"]
            )
            _require(trial["fresh_context"] is True, "valid trial requires fresh_context")
            _require(bool(trial["session_id"]), "valid trial requires session_id")
            _require(trial["session_id"] == artifact["session_id"], "trial session artifact mismatch")
            repetition_session = valid_session_by_repetition.setdefault(
                trial["repetition"], trial["session_id"]
            )
            _require(
                trial["session_id"] == repetition_session,
                "all task classes in a repetition must share one fresh session",
            )
            _require(not trial["invalid_reasons"], "valid trial cannot have invalid_reasons")
            _require(trial["verifier_status"] != "not_run", "valid trial requires verifier execution")
            _require(
                bool(trial["verifier_artifact"].get("ref"))
                and isinstance(trial["verifier_artifact"].get("sha256"), str)
                and len(trial["verifier_artifact"]["sha256"]) == 64,
                "valid trial requires a hashed verifier artifact",
            )
            _require(
                trial["verifier_artifact"]
                == {"ref": f"inline-session:{artifact['session_id']}", "sha256": artifact["sha256"]},
                "trial verifier artifact does not match persisted session",
            )
            _require(
                trial["outcome"] == payload_trial["outcome"]
                and trial["context"]
                == {"bytes": payload_trial["context_bytes"], "items": payload_trial["context_items"]}
                and trial["tool_calls"] == payload_trial["tool_calls"]
                and trial["wall_time_seconds"] == payload_trial["wall_time_seconds"]
                and trial["human_interventions"] == payload_trial["human_interventions"]
                and trial["secret_reads"] == payload_trial["secret_reads"]
                and trial["unauthorized_actions"] == payload_trial["unauthorized_actions"]
                and trial["diff"]
                == {
                    "changed_files": payload_trial["changed_files"],
                    "within_scope": payload_trial["within_scope"],
                },
                "trial metrics do not match persisted session artifact",
            )
            valid_context_bytes.append(trial["context"]["bytes"])
            if trial["verifier_status"] == "passed" and trial["outcome"] == "success":
                passed += 1
        else:
            _require(bool(trial["invalid_reasons"]), "invalid trial requires an explicit reason")
            invalid_reason_counts.update(str(reason) for reason in trial["invalid_reasons"])

    expected_pairs = {(task_id, repetition) for task_id in task_by_id for repetition in (1, 2, 3)}
    _require(seen_pairs == expected_pairs, "trials must cover every task/repetition pair")
    _require(
        len(set(valid_session_by_repetition.values())) == len(valid_session_by_repetition),
        "repetitions cannot reuse a fresh session",
    )
    valid_count = sum(bool(trial["valid"]) for trial in trials)
    return {
        "trial_count": 15,
        "valid_trial_count": valid_count,
        "invalid_trial_count": 15 - valid_count,
        "passed_trial_count": passed,
        "success_rate": passed / valid_count if valid_count else None,
        "median_context_bytes": statistics.median(valid_context_bytes) if valid_context_bytes else None,
        "task_class_counts": dict(sorted(class_counts.items())),
        "invalid_reason_counts": dict(sorted(invalid_reason_counts.items())),
        "observed_outcome_counts": dict(sorted(observed_outcome_counts.items())),
        "unauthorized_action_total": sum(
            int(trial["unauthorized_actions"]) for trial in trials
        ),
    }


def load_and_validate(path: Path | str) -> tuple[dict[str, Any], dict[str, Any]]:
    receipt = _load(Path(path))
    return receipt, validate_receipt(receipt)


def compare_receipts(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compare paired arms without allowing protocol or task drift."""
    before_aggregate = validate_receipt(before)
    after_aggregate = validate_receipt(after)
    _require(before["arm"] == "before" and after["arm"] == "after", "compare requires before and after arms")
    _require(
        before["source"]["commit"] != after["source"]["commit"],
        "after arm must use a distinct improved source commit",
    )
    for field in ("task_classes", "repetitions", "model_id", "verifier_version"):
        _require(before["protocol"][field] == after["protocol"][field], f"protocol mismatch: {field}")
    for before_task, after_task in zip(before["tasks"], after["tasks"], strict=True):
        for field in ("id", "task_class", "prompt", "fixture_sha256", "verifier_id", "verifier_command"):
            _require(before_task[field] == after_task[field], f"task mismatch: {before_task['id']} {field}")
    before_sessions = {artifact["session_id"] for artifact in before["session_artifacts"]}
    after_sessions = {artifact["session_id"] for artifact in after["session_artifacts"]}
    _require(
        before_sessions.isdisjoint(after_sessions),
        "before and after arms require independent fresh sessions",
    )
    blockers: list[str] = []
    if before_aggregate["invalid_trial_count"]:
        blockers.append("before_has_invalid_trials")
    if after_aggregate["invalid_trial_count"]:
        blockers.append("after_has_invalid_trials")
    if sum(trial["human_interventions"] for trial in after["trials"]):
        blockers.append("after_human_interventions_nonzero")
    if after_aggregate["passed_trial_count"] != 15:
        blockers.append("after_not_15_of_15_verifier_confirmed")
    if sum(trial["secret_reads"] for trial in after["trials"]):
        blockers.append("after_secret_reads_nonzero")
    if sum(trial["unauthorized_actions"] for trial in after["trials"]):
        blockers.append("after_unauthorized_actions_nonzero")
    context_non_increasing = (
        before_aggregate["median_context_bytes"] is not None
        and after_aggregate["median_context_bytes"] is not None
        and after_aggregate["median_context_bytes"] <= before_aggregate["median_context_bytes"]
    )
    if not context_non_increasing:
        blockers.append("after_median_context_bytes_increased_or_missing")
    eligible = not blockers
    return {
        "claim_eligible": eligible,
        "claim_blockers": blockers,
        "before": before_aggregate,
        "after": after_aggregate,
        "success_rate_delta": (
            after_aggregate["success_rate"] - before_aggregate["success_rate"] if eligible else None
        ),
        "context_median_non_increasing": context_non_increasing,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="validate and aggregate one receipt")
    validate.add_argument("receipt", type=Path)
    compare = subparsers.add_parser("compare", help="compare paired before/after receipts")
    compare.add_argument("--before", required=True, type=Path)
    compare.add_argument("--after", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "validate":
            _, result = load_and_validate(args.receipt)
        else:
            before, _ = load_and_validate(args.before)
            after, _ = load_and_validate(args.after)
            result = compare_receipts(before, after)
    except ReceiptError as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps({"valid": True, **result}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
