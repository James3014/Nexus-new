"""Metrics aggregation for Capability Lift Validation."""
import json
from pathlib import Path
from typing import Dict, Any, List
from collections import defaultdict


def aggregate_metrics(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate metrics from a list of eval results."""
    if not results:
        return {}
    
    total = len(results)
    verified = sum(1 for r in results if r.get("verified_success", False))
    first_pass = sum(1 for r in results if r.get("first_pass_success", False))
    abstain = sum(1 for r in results if r.get("abstain", False))
    trust_mismatch = sum(1 for r in results if r.get("trust_mismatch", False))
    
    wall_times = [r.get("wall_time_sec", 0) for r in results if r.get("wall_time_sec", 0) > 0]
    tokens = [r.get("token_usage", 0) for r in results if r.get("token_usage", 0) > 0]
    retries = [r.get("retry_count", 0) for r in results]
    
    return {
        "count": total,
        "verified_success_rate": verified / total,
        "first_pass_rate": first_pass / total,
        "abstain_rate": abstain / total,
        "trust_mismatch_rate": trust_mismatch / total,
        "avg_wall_time": sum(wall_times) / max(1, len(wall_times)),
        "avg_tokens": sum(tokens) / max(1, len(tokens)),
        "avg_retries": sum(retries) / total,
    }


def compare_groups(
    baseline: List[Dict[str, Any]],
    variant: List[Dict[str, Any]],
    variant_name: str,
) -> Dict[str, Any]:
    """Compare baseline vs variant metrics."""
    base_metrics = aggregate_metrics(baseline)
    var_metrics = aggregate_metrics(variant)
    
    return {
        "variant": variant_name,
        "baseline": base_metrics,
        "variant_metrics": var_metrics,
        "lift": {
            "verified_success_rate": var_metrics.get("verified_success_rate", 0) - base_metrics.get("verified_success_rate", 0),
            "first_pass_rate": var_metrics.get("first_pass_rate", 0) - base_metrics.get("first_pass_rate", 0),
            "avg_wall_time": base_metrics.get("avg_wall_time", 0) - var_metrics.get("avg_wall_time", 0),
            "avg_tokens": base_metrics.get("avg_tokens", 0) - var_metrics.get("avg_tokens", 0),
            "avg_retries": base_metrics.get("avg_retries", 0) - var_metrics.get("avg_retries", 0),
        },
    }


def generate_shadow_report(
    eval_results: Dict[str, List[Dict[str, Any]]],
    output_path: Path,
) -> None:
    """Generate shadow adoption report."""
    report = {
        "schema_version": "nexus.eval.shadow_report.v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "groups": {},
        "summary": {},
    }
    
    baseline = eval_results.get("baseline", [])
    
    for group_name, results in eval_results.items():
        if group_name == "baseline":
            continue
        
        comparison = compare_groups(baseline, results, group_name)
        report["groups"][group_name] = comparison
    
    # Generate verdict
    verdict = "No measurable lift"
    for group_name, comparison in report["groups"].items():
        lift = comparison.get("lift", {})
        if lift.get("verified_success_rate", 0) > 0.05:  # >5% improvement
            verdict = "Capability lift confirmed for limited scope"
            break
        elif lift.get("avg_wall_time", 0) > 5 or lift.get("avg_tokens", 0) > 100:
            verdict = "Cost/clarity lift only"
    
    report["summary"]["verdict"] = verdict
    report["summary"]["trust_mismatch_rate"] = sum(
        r.get("trust_mismatch", False) for results in eval_results.values() for r in results
    ) / max(1, sum(len(results) for results in eval_results.values()))
    
    # Write report
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


import time
