from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from scripts.bench.cost_evidence_classifier import LOCAL_SUCCESS_SOURCES, PROVIDER_TOKEN_SOURCES


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_detail(row: dict[str, Any], *, project_root: Path) -> dict[str, Any]:
    path_value = str(row.get("with_file") or "")
    if not path_value:
        return {}
    path = Path(path_value)
    if not path.is_absolute():
        path = project_root / path
    if not path.exists():
        return {}
    task_id = str(row.get("task_id") or "")
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            detail = json.loads(line)
        except ValueError:
            continue
        if str(detail.get("task_id") or "") == task_id and str(detail.get("mode") or "") == "with_nexus":
            return detail if isinstance(detail, dict) else {}
    return {}


def _verified(row: dict[str, Any]) -> bool:
    return (
        str(row.get("with_status") or "") == "SUCCESS"
        and str(row.get("with_semantic") or "") == "VERIFIED"
        and bool(row.get("with_eligible", True))
        and not bool(row.get("with_trust_mismatch", False))
    )


def _bare_verified(row: dict[str, Any]) -> bool:
    return (
        str(row.get("without_status") or "") == "SUCCESS"
        and str(row.get("without_semantic") or "") == "VERIFIED"
        and bool(row.get("without_eligible", True))
        and not bool(row.get("without_trust_mismatch", False))
    )


def _token_measured(row: dict[str, Any], detail: dict[str, Any]) -> bool:
    if detail:
        return bool(detail.get("token_measured", False)) or str(detail.get("token_capture_status") or "").lower() in {"ok", "measured"}
    return str(row.get("with_token_status") or "").lower() in {"ok", "measured"}


def _provider_token_measured(row: dict[str, Any], detail: dict[str, Any]) -> bool:
    source = str(detail.get("gateway_token_source") or row.get("with_gateway_token_source") or "").strip().lower()
    status = str(detail.get("token_capture_status") or row.get("with_token_status") or "").strip().lower()
    measured = bool(detail.get("token_measured", False)) or status in {"ok", "measured"}
    return bool(measured and source in PROVIDER_TOKEN_SOURCES)


def _model_calls(row: dict[str, Any], detail: dict[str, Any]) -> int:
    value = detail.get("model_calls", row.get("with_model_calls", 0)) if detail else row.get("with_model_calls", 0)
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _source(detail: dict[str, Any]) -> str:
    return str(detail.get("nexus_winner_source") or detail.get("source") or "")


def _route_controls(row: dict[str, Any]) -> dict[str, Any]:
    controls = row.get("route_cost_policy_controls")
    return controls if isinstance(controls, dict) else {}


def build_learning_ledgers(aggregate: dict[str, Any], *, project_root: Path) -> dict[str, Any]:
    rows = [row for row in aggregate.get("rows", []) or [] if isinstance(row, dict)]
    nexus_policy: list[dict[str, Any]] = []
    model_training: list[dict[str, Any]] = []
    cost_avoidance: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for row in rows:
        task_id = str(row.get("task_id") or "")
        detail = _load_detail(row, project_root=project_root)
        verified = _verified(row)
        if not verified:
            rejected.append({"task_id": task_id, "reason": "with_nexus_not_verified"})
            continue

        token_measured = _token_measured(row, detail)
        provider_token_measured = _provider_token_measured(row, detail)
        calls = _model_calls(row, detail)
        source = _source(detail)
        local_source = source in LOCAL_SUCCESS_SOURCES or bool(detail.get("model_timeout_local_fallback", False))
        bare_verified = _bare_verified(row)
        controls = _route_controls(row)
        common = {
            "task_id": task_id,
            "task_type": str(detail.get("task_type") or row.get("category") or ""),
            "verified": True,
            "bare_verified": bare_verified,
            "model_calls": calls,
            "token_measured": token_measured,
            "provider_token_measured": provider_token_measured,
            "token_source": str(detail.get("gateway_token_source") or row.get("with_gateway_token_source") or "missing"),
            "winner_source": source,
            "with_tokens": row.get("with_tokens"),
            "with_wall_sec": row.get("with_wall"),
            "route_cost_policy_controls": controls,
            "capability_selected_count": detail.get("route_decision_selected_count", None),
            "capability_required_count": detail.get("route_decision_required_count", None),
            "capability_conditional_count": detail.get("route_decision_conditional_count", None),
        }
        nexus_policy.append(
            {
                **common,
                "ledger": "nexus_policy",
                "policy_targets": ["route_weight", "capability_weight", "cost_tier"],
                "promote_runtime_policy": bool(controls) and not local_source,
            }
        )
        if calls > 0 and provider_token_measured and not local_source:
            model_training.append(
                {
                    **common,
                    "ledger": "model_training",
                    "training_targets": ["preference_pair", "reward_row"],
                    "model_uplift_eligible": not bare_verified,
                }
            )
        else:
            reason = "local_or_shadow_success" if local_source else "provider_tokens_not_measured" if not provider_token_measured else "model_calls_missing"
            cost_avoidance.append(
                {
                    **common,
                    "ledger": "cost_avoidance",
                    "reason": reason,
                    "model_uplift_eligible": False,
                }
            )

    return {
        "schema_version": "nexus_benchmark_learning_ledgers.v1",
        "source_schema": str(aggregate.get("schema_version") or ""),
        "task_count": len(rows),
        "nexus_policy_episodes": nexus_policy,
        "model_training_episodes": model_training,
        "cost_avoidance_episodes": cost_avoidance,
        "rejected_episodes": rejected,
        "summary": {
            "nexus_policy_count": len(nexus_policy),
            "model_training_count": len(model_training),
            "model_uplift_training_count": sum(1 for item in model_training if item.get("model_uplift_eligible")),
            "cost_avoidance_count": len(cost_avoidance),
            "rejected_count": len(rejected),
        },
        "claim_boundaries": [
            "Nexus policy episodes may update runtime routing and capability weights.",
            "Model training episodes require provider-measured model tokens and non-local winner sources.",
            "Cost avoidance episodes are useful Nexus evidence but are not weak-model uplift claims.",
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Benchmark Learning Ledgers",
        "",
        f"- nexus_policy_count: `{summary['nexus_policy_count']}`",
        f"- model_training_count: `{summary['model_training_count']}`",
        f"- model_uplift_training_count: `{summary['model_uplift_training_count']}`",
        f"- cost_avoidance_count: `{summary['cost_avoidance_count']}`",
        f"- rejected_count: `{summary['rejected_count']}`",
        "",
        "## Boundaries",
        "",
    ]
    lines.extend(f"- {item}" for item in payload["claim_boundaries"])
    lines.extend(["", "## Model Training Episodes", "", "| Task | Uplift eligible | Provider tokens | Token source | Source |", "| :--- | :--- | :--- | :--- | :--- |"])
    for row in payload["model_training_episodes"]:
        lines.append(
            f"| {row['task_id']} | {row['model_uplift_eligible']} | {row['provider_token_measured']} | "
            f"{row['token_source']} | {row['winner_source']} |"
        )
    lines.extend(["", "## Cost Avoidance / Hold Episodes", "", "| Task | Reason | Source |", "| :--- | :--- | :--- |"])
    for row in payload["cost_avoidance_episodes"]:
        lines.append(f"| {row['task_id']} | {row['reason']} | {row['winner_source']} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export benchmark aggregate rows into separate Nexus-policy and model-training ledgers.")
    parser.add_argument("--aggregate", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)

    payload = build_learning_ledgers(_load_json(args.aggregate), project_root=args.project_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_markdown(payload), encoding="utf-8")
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
