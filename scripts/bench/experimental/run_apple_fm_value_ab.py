#!/usr/bin/env python3
"""Physical FM x0/x2/x4 value A/B on source-bound Nexus small tasks."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
import random
import re
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from nexus.calibration.provider_adoption.apple_fm_adapter import AppleFMCandidateAdapter
from nexus.calibration.provider_adoption.apple_fm_worker_pool import (
    NETWORK_DENY_PROFILE,
    AppleFMReadOnlyTask,
    AppleFMReadOnlyWorkerPool,
    AppleFMTaskKind,
)
from tests.golden_behavior.corpus import CASES as GOLDEN_CASES

SCHEMA = "nexus.experiment.apple_fm_value_ab.v1"
CLASS_LABELS = ("security", "invariant", "compatibility", "regression")
SENSITIVE_KEY = re.compile(r"(secret|password|credential|cookie|api.?key|access.?token|refresh.?token)", re.I)
ESCALATE_WORDS = re.compile(
    r"(authority|merge|retry|replay|mutation|production|release|workforce|routing|approval|deploy)",
    re.I,
)


@dataclass(frozen=True)
class Case:
    case_id: str
    kind: str
    source_group: str
    source_path: str
    source_sha256: str
    prompt: str
    ground_truth: str
    split: str
    eligible_candidate: bool


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def json_scalar_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    raise ValueError(f"unsupported structured scalar: {type(value).__name__}")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scalar_leaves(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key in sorted(value):
            if SENSITIVE_KEY.search(str(key)):
                continue
            child = value[key]
            p = f"{prefix}.{key}" if prefix else str(key)
            out.extend(scalar_leaves(child, p))
    elif isinstance(value, list):
        for index, child in enumerate(value[:5]):
            p = f"{prefix}[{index}]"
            out.extend(scalar_leaves(child, p))
    elif value is None or isinstance(value, (bool, int, float, str)):
        if isinstance(value, str) and (len(value) > 120 or "\n" in value):
            return out
        out.append((prefix, value))
    return out


def build_source_bound_cases(root: Path) -> list[Case]:
    golden = sorted(GOLDEN_CASES, key=lambda c: sha256_text(c.case_id))
    escalation = [
        c for c in golden
        if ESCALATE_WORDS.search(f"{c.title} {c.scenario} {c.expected_behavior}")
    ][:20]
    escalation_ids = {c.case_id for c in escalation}
    classification = [c for c in golden if c.case_id not in escalation_ids][:60]

    raw: list[tuple[str, str, str, str, str, bool]] = []
    for c in classification:
        prompt = (
            "Classify this real Nexus golden-behavior case into exactly one label: "
            + ", ".join(CLASS_LABELS)
            + f". Title: {c.title}. Scenario: {c.scenario}. Return only the label."
        )
        raw.append((
            f"G-{c.case_id}", "golden_classification", f"golden:{c.case_id}",
            "tests/golden_behavior/corpus.py", prompt, c.classification, True,
        ))

    for c in escalation:
        prompt = (
            "Safety-gate classification. A bounded local preprocessor must not decide routing, "
            "workforce, retry, merge, release, production, mutation, or approval authority. "
            f"Real Nexus case: {c.title}. Scenario: {c.scenario}. "
            "Return only ESCALATE or LOCAL_OK."
        )
        raw.append((
            f"E-{c.case_id}", "mandatory_escalation", f"golden:{c.case_id}",
            "tests/golden_behavior/corpus.py", prompt, "ESCALATE", False,
        ))

    json_paths = sorted(
        [
            p for base in (root / "tests", root / "nexus", root / "docs")
            for p in base.rglob("*.json")
            if "__pycache__" not in p.parts
        ],
        key=lambda p: sha256_text(str(p.relative_to(root))),
    )
    json_cases = 0
    for path in json_paths:
        if json_cases >= 70:
            break
        rel = str(path.relative_to(root))
        if SENSITIVE_KEY.search(rel):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        leaves = [(k, v) for k, v in scalar_leaves(payload) if k]
        if len(leaves) < 3:
            continue
        supported = []
        for key, value in leaves:
            if value is None or not isinstance(value, (bool, int, float, str)):
                continue
            if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._:/-]{1,120}", value) is None:
                continue
            supported.append((key, value))
        if len(supported) < 3:
            continue
        target_path, target_value = supported[0]
        context_items = supported[: min(6, len(supported))]
        context = {k: v for k, v in context_items}
        truth = canonical_json(target_value) if not isinstance(target_value, str) else target_value
        prompt = (
            "From this real Nexus JSON artifact excerpt, extract the scalar value at path "
            f"{target_path}. Return only the scalar value with no quotes and no explanation. "
            f"Artifact excerpt: {canonical_json(context)}"
        )
        raw.append((
            f"J-{json_cases+1:03d}", "literal_extraction", f"file:{rel}", rel,
            prompt, truth, True,
        ))
        json_cases += 1

    if len(raw) != 150:
        raise RuntimeError(f"expected 150 cases, built {len(raw)}")

    # Source-group deterministic split: 50 calibration / 100 holdout.
    by_kind: dict[str, list[tuple[str, str, str, str, str, str, bool]]] = {}
    for row in raw:
        by_kind.setdefault(row[1], []).append(row)
    targets = {
        "golden_classification": 20,
        "literal_extraction": 20,
        "mandatory_escalation": 10,
    }
    calibration_ids: set[str] = set()
    for kind, rows in by_kind.items():
        ordered = sorted(rows, key=lambda r: sha256_text(r[2]))
        n = targets[kind]
        calibration_ids.update(r[0] for r in ordered[:n])

    result: list[Case] = []
    corpus_sha = file_sha256(root / "tests/golden_behavior/corpus.py")
    for case_id, kind, group, rel, prompt, truth, eligible in raw:
        source_sha = corpus_sha if rel == "tests/golden_behavior/corpus.py" else file_sha256(root / rel)
        split = "calibration" if case_id in calibration_ids else "holdout"
        result.append(Case(case_id, kind, group, rel, source_sha, prompt, truth, split, eligible))
    assert sum(c.split == "calibration" for c in result) == 50
    assert sum(c.split == "holdout" for c in result) == 100
    return sorted(result, key=lambda c: c.case_id)


def write_cohort(path: Path, cases: list[Case]) -> str:
    lines = [canonical_json(asdict(c)) for c in cases]
    text = "\n".join(lines) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return sha256_text(text)


def parse_exact(kind: str, text: str) -> str:
    value = text.strip()
    if kind == "golden_classification":
        tokens = re.findall(r"[A-Za-z_]+", value.lower())
        for label in CLASS_LABELS:
            if label in tokens:
                return label
        return value.lower()
    if kind == "mandatory_escalation":
        return "ESCALATE" if "ESCALATE" in value.upper() else value.upper()
    if kind == "literal_extraction":
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", value, flags=re.I | re.S)
        if fenced:
            value = fenced.group(1).strip()
        try:
            parsed = json.loads(value)
        except Exception:
            return value.strip("'\"")
        return parsed if isinstance(parsed, str) else canonical_json(parsed)
    return value


def fm_task(case: Case) -> AppleFMReadOnlyTask:
    if case.kind == "golden_classification":
        return AppleFMReadOnlyTask(
            case.case_id,
            AppleFMTaskKind.CLASSIFICATION,
            case.prompt,
            allowed_outputs=CLASS_LABELS,
        )
    if case.kind == "literal_extraction":
        return AppleFMReadOnlyTask(
            case.case_id,
            AppleFMTaskKind.LITERAL_EXTRACTION,
            case.prompt,
            output_pattern=r"-?[A-Za-z0-9._:/]+",
        )
    raise ValueError(f"not FM-eligible: {case.case_id}")


def verify_network_denial() -> dict[str, Any]:
    direct = subprocess.run(
        ["/usr/bin/curl", "--max-time", "3", "-sS", "https://example.com"],
        capture_output=True, text=True, timeout=5,
    )
    sandboxed = subprocess.run(
        ["/usr/bin/sandbox-exec", "-p", NETWORK_DENY_PROFILE,
         "/usr/bin/curl", "--max-time", "3", "-sS", "https://example.com"],
        capture_output=True, text=True, timeout=5,
    )
    return {
        "direct_reachable": direct.returncode == 0,
        "sandboxed_exit_code": sandboxed.returncode,
        "network_denial_verified": direct.returncode == 0 and sandboxed.returncode != 0,
    }


def online_one(root: Path, case: Case, model: str, effort: str) -> dict[str, Any]:
    argv = [
        os.path.expanduser("~/.local/bin/nexus-agy-dispatch"),
        "--cwd", str(root),
        "--mode", "plan",
        "--model", model,
        "--effort", effort,
        "--timeout", "120",
        "--max-calls", "3",
        "--pool-wait-timeout", "180",
        "--prompt",
        "BENCHMARK MODE. Do not call tools, do not read files, and do not inspect the "
        "workspace. Answer solely from the text below. " + case.prompt,
    ]
    started = time.perf_counter()
    cp = subprocess.run(argv, capture_output=True, text=True, timeout=240)
    elapsed = int((time.perf_counter() - started) * 1000)
    lines = [line.strip() for line in cp.stdout.splitlines() if line.strip()]
    meta: dict[str, Any] = {}
    answer_lines = list(lines)
    for line in cp.stderr.splitlines():
        line = line.strip()
        if line.startswith("NEXUS_AGY_DISPATCH "):
            try:
                meta = json.loads(line.split(" ", 1)[1])
            except Exception:
                pass
    answer = "\n".join(answer_lines).strip()
    parsed = parse_exact(case.kind, answer)
    tool_denied = "no output produced" in (cp.stderr or "").lower()
    transport_ok = cp.returncode == 0 and bool(answer) and not tool_denied
    return {
        "case_id": case.case_id,
        "status": "PASS" if transport_ok else "INFRA_ERROR",
        "returncode": cp.returncode,
        "answer": answer,
        "parsed": parsed,
        "correct": transport_ok and parsed == case.ground_truth,
        "latency_ms": elapsed,
        "dispatch_meta": meta,
        "stderr_tail": cp.stderr.strip()[-500:],
    }


def online_batch(root: Path, cases: list[Case], model: str, effort: str, workers: int) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(online_one, root, c, model, effort): c.case_id for c in cases}
        for fut in concurrent.futures.as_completed(futures):
            result = fut.result()
            out[result["case_id"]] = result
    return out


def fm_batch(cases: list[Case], concurrency: int) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    if not cases:
        return {}, {"wall_time_ms": 0, "throughput_rps": 0.0}
    receipt = AppleFMReadOnlyWorkerPool().run_batch(
        [fm_task(c) for c in cases], concurrency=concurrency
    )
    out: dict[str, dict[str, Any]] = {}
    case_map = {c.case_id: c for c in cases}
    for result in receipt.results:
        case = case_map[result.task_id]
        parsed = parse_exact(case.kind, result.output_text)
        out[result.task_id] = {
            "case_id": result.task_id,
            "answer": result.output_text,
            "parsed": parsed,
            "contract_valid": result.output_contract_valid,
            "correct": result.output_contract_valid and parsed == case.ground_truth,
            "latency_ms": result.latency_ms,
            "needs_escalation": result.needs_escalation,
            "error_code": result.error_code,
        }
    return out, receipt.to_dict()


def percentile(values: list[int], p: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    rank = max(1, math.ceil(p * len(ordered)))
    return float(ordered[rank - 1])


def bootstrap_ci(values: list[float], seed: int = 20260929, draws: int = 4000) -> list[float]:
    if not values:
        return [float("nan"), float("nan")]
    rng = random.Random(seed)
    n = len(values)
    stats = []
    for _ in range(draws):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        stats.append(statistics.fmean(sample))
    stats.sort()
    return [stats[int(0.025 * draws)], stats[int(0.975 * draws) - 1]]


def summarize_arm(name: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    correctness = [1.0 if r["final_correct"] else 0.0 for r in rows]
    calls = [1.0 if r["online_called"] else 0.0 for r in rows]
    latencies = [int(r["end_to_end_latency_ms"]) for r in rows]
    local_rows = [r for r in rows if r["accepted_local"]]
    false_local = [r for r in local_rows if not r["final_correct"]]
    return {
        "arm": name,
        "tasks": len(rows),
        "final_accuracy": statistics.fmean(correctness),
        "online_calls": int(sum(calls)),
        "online_call_fraction": statistics.fmean(calls),
        "p50_latency_ms": percentile(latencies, 0.50),
        "p95_latency_ms": percentile(latencies, 0.95),
        "mean_latency_ms": statistics.fmean(latencies),
        "local_accepts": len(local_rows),
        "false_local_passes": len(false_local),
        "local_accept_precision": (
            sum(1 for r in local_rows if r["final_correct"]) / len(local_rows)
            if local_rows else None
        ),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cohort", type=Path, required=True)
    ap.add_argument("--output-json", type=Path, required=True)
    ap.add_argument("--online-model", default="gemini-3.8-flash")
    ap.add_argument("--online-effort", default="low", choices=("low", "medium", "high"))
    ap.add_argument("--online-workers", type=int, default=4)
    ap.add_argument("--online-cwd", type=Path)
    ap.add_argument("--build-only", action="store_true")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[3]
    online_root = (args.online_cwd or root).resolve()
    cases = build_source_bound_cases(root)
    cohort_sha = write_cohort(args.cohort, cases)
    if args.build_only:
        print(canonical_json({"status": "COHORT_BUILT", "cases": len(cases), "cohort_sha256": cohort_sha}))
        return 0

    network = verify_network_denial()
    if not network["network_denial_verified"]:
        raise SystemExit("network denial preflight failed")
    identity = AppleFMCandidateAdapter().inspect_identity().to_dict()

    calibration = [c for c in cases if c.split == "calibration"]
    holdout = [c for c in cases if c.split == "holdout"]

    cal_eligible = [c for c in calibration if c.eligible_candidate]
    cal_fm, cal_fm_receipt = fm_batch(cal_eligible, 2)

    kind_policy: dict[str, bool] = {}
    for kind in ("golden_classification", "literal_extraction"):
        members = [c for c in cal_eligible if c.kind == kind]
        acc = sum(1 for c in members if cal_fm[c.case_id]["correct"]) / max(1, len(members))
        kind_policy[kind] = len(members) >= 10 and acc >= 0.95
    kind_policy["mandatory_escalation"] = False

    rows_by_arm: dict[str, list[dict[str, Any]]] = {"A0": [], "A2": [], "A4": []}
    fm_receipts: dict[str, list[dict[str, Any]]] = {"A2": [], "A4": []}
    # Physical A0 is measured once per holdout case. A2/A4 reuse the exact same
    # A0 witness only when they would escalate the unchanged original prompt.
    blocks = [holdout[i:i+10] for i in range(0, len(holdout), 10)]

    for block in blocks:
        online = online_batch(online_root, block, args.online_model, args.online_effort, args.online_workers)
        for c in block:
            o = online[c.case_id]
            rows_by_arm["A0"].append({
                "case_id": c.case_id, "kind": c.kind, "online_called": True,
                "physical_online_called": True, "accepted_local": False, "fm_correct": None,
                "final_correct": bool(o["correct"]),
                "end_to_end_latency_ms": o["latency_ms"],
                "online_witness_mode": "PHYSICAL_A0",
                "online": o,
            })

        for arm, concurrency in (("A2", 2), ("A4", 4)):
            local_candidates = [
                c for c in block
                if c.eligible_candidate and kind_policy.get(c.kind, False)
            ]
            fm, receipt = fm_batch(local_candidates, concurrency)
            fm_receipts[arm].append(receipt)
            for c in block:
                local_attempt = fm.get(c.case_id)
                accepted_local = bool(local_attempt and local_attempt["contract_valid"])
                if accepted_local:
                    final_correct = bool(local_attempt["correct"])
                    latency = int(local_attempt["latency_ms"])
                    online_result = None
                    witness_mode = "LOCAL_PHYSICAL"
                else:
                    # Same model, same effort, same original prompt: reuse the paired A0
                    # physical witness instead of spending a duplicate online call.
                    online_result = online[c.case_id]
                    final_correct = bool(online_result["correct"])
                    fm_latency = int(local_attempt["latency_ms"]) if local_attempt else 0
                    latency = fm_latency + int(online_result["latency_ms"])
                    witness_mode = "COUNTERFACTUAL_REPLAY_FROM_A0_PHYSICAL"
                rows_by_arm[arm].append({
                    "case_id": c.case_id, "kind": c.kind,
                    "online_called": not accepted_local,
                    "physical_online_called": False,
                    "accepted_local": accepted_local,
                    "fm_correct": None if local_attempt is None else bool(local_attempt["correct"]),
                    "final_correct": final_correct,
                    "end_to_end_latency_ms": latency,
                    "online_witness_mode": witness_mode,
                    "fm": local_attempt,
                    "online": online_result,
                })

    summaries = {arm: summarize_arm(arm, rows) for arm, rows in rows_by_arm.items()}
    baseline = {r["case_id"]: r for r in rows_by_arm["A0"]}
    comparisons: dict[str, Any] = {}
    for arm in ("A2", "A4"):
        paired = []
        for row in rows_by_arm[arm]:
            b = baseline[row["case_id"]]
            paired.append({
                "case_id": row["case_id"],
                "accuracy_delta": float(row["final_correct"]) - float(b["final_correct"]),
                "online_call_delta": float(row["online_called"]) - 1.0,
                "latency_delta_ms": float(row["end_to_end_latency_ms"] - b["end_to_end_latency_ms"]),
            })
        comparisons[arm] = {
            "accuracy_delta_mean": statistics.fmean(x["accuracy_delta"] for x in paired),
            "accuracy_delta_95ci": bootstrap_ci([x["accuracy_delta"] for x in paired]),
            "online_call_reduction": 1.0 - summaries[arm]["online_call_fraction"],
            "online_call_reduction_95ci": [
                -x for x in reversed(bootstrap_ci([x["online_call_delta"] for x in paired]))
            ],
            "latency_delta_mean_ms": statistics.fmean(x["latency_delta_ms"] for x in paired),
            "latency_delta_95ci_ms": bootstrap_ci([x["latency_delta_ms"] for x in paired]),
        }

    oracle_safe = 0
    eligible_holdout = 0
    a2_rows = {r["case_id"]: r for r in rows_by_arm["A2"]}
    for c in holdout:
        if c.eligible_candidate and kind_policy.get(c.kind, False):
            eligible_holdout += 1
            if a2_rows[c.case_id]["fm_correct"]:
                oracle_safe += 1

    baseline_ok = summaries["A0"]["final_accuracy"] >= 0.95
    gates: dict[str, Any] = {"baseline_accuracy_ge_0_95": baseline_ok}
    for arm in ("A2", "A4"):
        gates[f"{arm}_zero_false_local_pass"] = summaries[arm]["false_local_passes"] == 0
        gates[f"{arm}_quality_noninferior_1pp"] = (
            summaries[arm]["final_accuracy"] >= summaries["A0"]["final_accuracy"] - 0.01
        )
        gates[f"{arm}_online_calls_reduced_ge_30pct"] = comparisons[arm]["online_call_reduction"] >= 0.30
        gates[f"{arm}_p95_no_gt_20pct_regression"] = (
            summaries[arm]["p95_latency_ms"] <= summaries["A0"]["p95_latency_ms"] * 1.20
        )

    a4_vs_a2_p95_improvement = (
        (summaries["A2"]["p95_latency_ms"] - summaries["A4"]["p95_latency_ms"])
        / summaries["A2"]["p95_latency_ms"]
        if summaries["A2"]["p95_latency_ms"] else 0.0
    )
    verdict = "REJECT"
    if all(gates.values()):
        verdict = "2_WORKER_PILOT"
        if a4_vs_a2_p95_improvement >= 0.15:
            verdict = "2_PLUS_4_BURST_PILOT"

    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], text=True).strip()
    payload = {
        "schema": SCHEMA,
        "status": "COMPLETE",
        "claim_ceiling": "EXPERIMENT_ONLY_NO_ROUTING_AUTHORITY",
        "source_commit": commit,
        "source_tree": tree,
        "cohort_sha256": cohort_sha,
        "cohort_counts": {
            "total": len(cases), "calibration": len(calibration), "holdout": len(holdout),
        },
        "apple_fm_identity": identity,
        "network_control": network,
        "online_route": {
            "transport": "~/.local/bin/nexus-agy-dispatch",
            "model": args.online_model,
            "effort": args.online_effort,
            "parallelism": args.online_workers,
            "cwd": str(online_root),
            "token_usage": "UNKNOWN_NOT_EXPOSED_BY_WRAPPER",
            "holdout_physical_online_calls": len(holdout),
            "counterfactual_escalation_replay": True,
        },
        "calibration": {
            "kind_policy": kind_policy,
            "fm_receipt": cal_fm_receipt,
            "fm_accuracy_by_kind": {
                kind: (
                    sum(1 for c in cal_eligible if c.kind == kind and cal_fm[c.case_id]["correct"])
                    / max(1, sum(1 for c in cal_eligible if c.kind == kind))
                )
                for kind in ("golden_classification", "literal_extraction")
            },
            "online_accuracy": "NOT_RUN_GROUND_TRUTH_IS_DETERMINISTIC",
        },
        "holdout": {
            "summaries": summaries,
            "latency_evidence_mode": "A0_PHYSICAL_PLUS_PAIRED_FM_PHYSICAL_COUNTERFACTUAL_ESCALATION",
            "comparisons_vs_A0": comparisons,
            "oracle_safe_local_fraction_of_all_holdout": oracle_safe / len(holdout),
            "oracle_safe_local_fraction_of_eligible_holdout": (
                oracle_safe / eligible_holdout if eligible_holdout else 0.0
            ),
            "eligible_holdout": eligible_holdout,
            "oracle_safe_local": oracle_safe,
            "a4_vs_a2_p95_improvement": a4_vs_a2_p95_improvement,
            "gates": gates,
            "verdict": verdict,
            "rows": rows_by_arm,
            "fm_batch_receipts": fm_receipts,
        },
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "cohort_sha256": cohort_sha,
        "summaries": summaries,
        "comparisons": comparisons,
        "gates": gates,
        "verdict": verdict,
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
