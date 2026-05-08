#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_COMMERCIAL_LANES = Path("scripts/bench/public_benchmark_commercial_lanes_v1.json")
DEFAULT_SWE_BENCH = Path("scripts/bench/swe-bench-verified.json")
DEFAULT_DISCLOSURE = Path(".nexus/reports/sanitized_public_benchmark_nexus_value_v1.json")

DEFAULT_PUBLIC_MODELS = (
    "gemini-3-flash-preview",
    "gemini-3.1-pro-preview",
)
DEFAULT_SWE_DIFFICULTY_ORDER = (
    "<15 min fix",
    "15 min - 1 hour",
    "1-4 hours",
    ">4 hours",
)


@dataclass(frozen=True)
class SweBenchSubset:
    total_rows: int
    selected_rows: list[dict[str, Any]]
    difficulty_counts: dict[str, int]
    repo_counts: dict[str, int]


def _read_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _stable_swe_subset(
    rows: list[dict[str, Any]],
    *,
    max_tasks: int,
    difficulty_allowlist: tuple[str, ...] = DEFAULT_SWE_DIFFICULTY_ORDER[:2],
) -> list[dict[str, Any]]:
    allowed = set(difficulty_allowlist)
    candidates = [row for row in rows if str(row.get("difficulty", "")) in allowed]
    difficulty_rank = {name: idx for idx, name in enumerate(DEFAULT_SWE_DIFFICULTY_ORDER)}
    candidates.sort(
        key=lambda row: (
            difficulty_rank.get(str(row.get("difficulty", "")), 999),
            str(row.get("repo", "")),
            str(row.get("instance_id", "")),
        )
    )
    return candidates[: max(0, max_tasks)]


def build_swe_bench_subset(*, path: str | Path = DEFAULT_SWE_BENCH, max_tasks: int = 5) -> SweBenchSubset:
    rows = _read_jsonl(path)
    selected = _stable_swe_subset(rows, max_tasks=max_tasks)
    return SweBenchSubset(
        total_rows=len(rows),
        selected_rows=selected,
        difficulty_counts=dict(Counter(str(row.get("difficulty", "")) for row in rows)),
        repo_counts=dict(Counter(str(row.get("repo", "")) for row in rows)),
    )


def _capability_ab_command(
    *,
    tasks_file: str,
    output_dir: str,
    model: str,
    max_tasks: int,
    timeout_sec: int,
    disclosure_manifest: str = str(DEFAULT_DISCLOSURE),
    task_id_filter: str = "all",
    with_provider: str = "gemini",
    without_mode: str = "gemini",
) -> list[str]:
    cmd = [
        "NEXUS_VALUE_HIDDEN_VERIFIER=1",
        f"NEXUS_GEMINI_MODEL_NAME={model}",
        f"NEXUS_DIRECT_GEMINI_MODEL={model}",
        "NEXUS_GATEWAY_PROMPT_TRANSPORT=stdin",
        "NEXUS_GATEWAY_COMPACT_PROMPT=1",
        "NEXUS_LLM_SELF_HEAL_ON_PYTEST_FAIL=1",
        "uv",
        "run",
        "python",
        "scripts/bench/capability_ab_runner.py",
        "--tasks-file",
        tasks_file,
        "--public-disclosure-manifest",
        disclosure_manifest,
        "--output-dir",
        output_dir,
        "--max-tasks",
        str(max_tasks),
        "--repeat-trials",
        "1",
        "--timeout-sec",
        str(timeout_sec),
        "--total-timeout-sec",
        "7200",
        "--stop-loss-sec",
        "7200",
        "--per-task-stop-loss-sec",
        "600",
        "--difficulty",
        "all",
        "--force-flow",
        "auto",
        "--with-nexus-runner",
        "subprocess",
        "--with-llm-mode",
        "hard",
        "--with-model-provider",
        with_provider,
        "--without-mode",
        without_mode,
        "--force-learn-slo-ready",
        "--neutralize-history",
        "--disable-learning-loop",
        "--materialize-missing",
        "--isolation-mode",
        "preserve_target",
        "--enable-autoreason-executor",
        "--enable-ddtree-executor",
        "--enable-ultra-review-dry-gate",
        "--llm-candidate-cap",
        "3",
        "--enable-llm-self-heal",
        "--evidence-bundle",
        "--markdown-report",
        "auto",
        "--progress-log",
    ]
    if task_id_filter != "all":
        cmd.extend(["--task-id-filter", task_id_filter])
    return cmd


def _shell(cmd: list[str]) -> str:
    env: list[str] = []
    rest: list[str] = []
    for token in cmd:
        if "=" in token and not rest:
            env.append(token)
        else:
            rest.append(token)
    return " ".join([*env, *rest])


def _commercial_lane_tasks(lanes: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(lane.get("id")): lane for lane in lanes.get("lanes", [])}


def build_phase_plan(
    *,
    commercial_lanes_path: str | Path = DEFAULT_COMMERCIAL_LANES,
    swe_bench_path: str | Path = DEFAULT_SWE_BENCH,
    swe_max_tasks: int = 5,
    public_models: tuple[str, ...] = DEFAULT_PUBLIC_MODELS,
) -> dict[str, Any]:
    lanes = _read_json(commercial_lanes_path)
    lane_map = _commercial_lane_tasks(lanes)
    swe = build_swe_bench_subset(path=swe_bench_path, max_tasks=swe_max_tasks)
    smoke_tasks = "nexus-value-hidden-001,nexus-value-repair-001,nexus-value-context-001"

    phases = [
        {
            "phase": 0,
            "name": "public_input_preflight",
            "claim_scope": "public_safe_preflight_only",
            "benchmark_family": "nexus_commercial_lanes",
            "acceptance": [
                "sanitized execution manifest exists",
                "disclosure manifest passes capability_ab_runner --preflight-only",
                "same-model rule is explicit",
            ],
            "commands": [
                "uv run python scripts/bench/commercial_lane_tasks.py --lane capability_lift --output .nexus/reports/phase0_capability_lift_tasks.json --execution-safe-output .nexus/reports/phase0_capability_lift.execution_safe.json --disclosure-output .nexus/reports/phase0_capability_lift.disclosure.json",
                _shell(
                    _capability_ab_command(
                        tasks_file=".nexus/reports/phase0_capability_lift.execution_safe.json",
                        output_dir=".nexus/reports/phase0_preflight",
                        model=public_models[0],
                        max_tasks=6,
                        timeout_sec=300,
                        disclosure_manifest=".nexus/reports/phase0_capability_lift.disclosure.json",
                    )
                    + ["--preflight-only"]
                ),
            ],
        },
        {
            "phase": 1,
            "name": "nexus_value_same_model_smoke",
            "claim_scope": "internal_public_candidate",
            "benchmark_family": "nexus_value",
            "task_id_filter": smoke_tasks,
            "acceptance": [
                "with_nexus and without_nexus use the same model",
                "with_nexus does not increase unnecessary_selected over regression baseline",
                "one task fail stops the loop for trace analysis",
            ],
            "commands": [
                _shell(
                    _capability_ab_command(
                        tasks_file="scripts/bench/public_benchmark_nexus_value_v1.json",
                        output_dir=f".nexus/reports/phase1_value_smoke_{model.replace('.', '_').replace('-', '_')}",
                        model=model,
                        max_tasks=3,
                        timeout_sec=300,
                        task_id_filter=smoke_tasks,
                    )
                )
                for model in public_models
            ],
        },
    ]

    commercial_specs = [
        (2, "capability_lift_smoke", "capability_lift", 6),
        (3, "capability_lift_full", "capability_lift", len(lane_map.get("capability_lift", {}).get("task_refs", []))),
        (4, "governed_delivery_smoke", "governed_delivery", 6),
        (5, "cost_efficiency_smoke", "cost_efficiency", 4),
    ]
    for phase, name, lane, max_tasks in commercial_specs:
        phases.append(
            {
                "phase": phase,
                "name": name,
                "claim_scope": "internal_public_candidate",
                "benchmark_family": "nexus_commercial_lanes",
                "commercial_lane": lane,
                "task_ref_count": len(lane_map.get(lane, {}).get("task_refs", [])),
                "acceptance": [
                    "public_claim_gate PASS",
                    "route_cost_ledger present",
                    "product_kpis present",
                    "same-model bare vs Nexus comparison only",
                ],
                "commands": [
                    f"uv run python scripts/bench/commercial_lane_tasks.py --lane {lane} --output .nexus/reports/phase{phase}_{lane}_tasks.json --execution-safe-output .nexus/reports/phase{phase}_{lane}.execution_safe.json --disclosure-output .nexus/reports/phase{phase}_{lane}.disclosure.json",
                    *[
                        _shell(
                            _capability_ab_command(
                                tasks_file=f".nexus/reports/phase{phase}_{lane}.execution_safe.json",
                                output_dir=f".nexus/reports/phase{phase}_{lane}_{model.replace('.', '_').replace('-', '_')}",
                                model=model,
                                max_tasks=max_tasks,
                                timeout_sec=300,
                            )
                        )
                        for model in public_models
                    ],
                ],
            }
        )

    phases.extend(
        [
            {
                "phase": 6,
                "name": "internal_realism_appendix",
                "claim_scope": "appendix_not_headline",
                "benchmark_family": "nexus_real_world_internal",
                "acceptance": [
                    "used only as realism appendix",
                    "not mixed with SWE-bench or commercial lane headline",
                    "schema exported with benchmark_family",
                ],
                "commands": [
                    "uv run python scripts/bench/real_world_task_runner.py --executor full_nexus --max-tasks 3 --output-dir .nexus/reports/phase6_real_world_appendix"
                ],
            },
            {
                "phase": 7,
                "name": "swe_bench_verified_wiring_smoke",
                "claim_scope": "external_wiring_smoke_not_public_uplift",
                "benchmark_family": "swe_bench_verified",
                "external_benchmark": True,
                "dataset": "SWE-bench Verified",
                "selected_instance_ids": [str(row.get("instance_id")) for row in swe.selected_rows],
                "acceptance": [
                    "same instance_id denominator for all arms",
                    "bare arm and Nexus arm both emit predictions.jsonl",
                    "official SWE-bench harness result is required before any external solve-rate claim",
                ],
                "commands": [
                    "uv run python scripts/bench/swe_bench_harness.py --max-tasks 5 --output-dir .nexus/reports/phase7_swe_bench_wiring --jsonl-output .nexus/reports/phase7_swe_bench_wiring/predictions.jsonl"
                ],
            },
            {
                "phase": 8,
                "name": "swe_bench_verified_25_task_subset",
                "claim_scope": "external_subset_after_official_harness",
                "benchmark_family": "swe_bench_verified",
                "external_benchmark": True,
                "acceptance": [
                    "25 fixed tasks",
                    "official harness pass/fail captured",
                    "infra-invalid denominator rule documented before running",
                ],
                "commands": [
                    "uv run python scripts/bench/swe_bench_harness.py --max-tasks 25 --output-dir .nexus/reports/phase8_swe_bench_25 --jsonl-output .nexus/reports/phase8_swe_bench_25/predictions.jsonl"
                ],
            },
            {
                "phase": 9,
                "name": "swe_bench_verified_external_headline_gate",
                "claim_scope": "external_public_headline_only_after_official_harness",
                "benchmark_family": "swe_bench_verified",
                "external_benchmark": True,
                "acceptance": [
                    "100 or 500 fixed tasks",
                    "official harness result available",
                    "same-model bare vs Nexus if uplift is claimed",
                    "commercial lane claims remain separate from SWE-bench claims",
                ],
                "commands": [
                    "uv run python scripts/bench/swe_bench_harness.py --max-tasks 100 --output-dir .nexus/reports/phase9_swe_bench_100 --jsonl-output .nexus/reports/phase9_swe_bench_100/predictions.jsonl"
                ],
            },
        ]
    )

    return {
        "schema": "nexus_public_credibility_phase_plan_v1",
        "public_models": list(public_models),
        "rules": {
            "nexus_is_battlesuit_not_agent": True,
            "same_model_ab_required_for_uplift_claim": True,
            "external_benchmark_claim_requires_official_harness": True,
            "do_not_mix_internal_and_external_headlines": True,
            "fail_fast_on_first_task_failure": True,
        },
        "commercial_lanes": {
            "benchmark_id": lanes.get("benchmark_id"),
            "lane_ids": sorted(lane_map),
            "task_ref_counts": {lane: len(payload.get("task_refs", [])) for lane, payload in lane_map.items()},
        },
        "swe_bench_verified": {
            "source": str(swe_bench_path),
            "total_rows": swe.total_rows,
            "selected_rows": len(swe.selected_rows),
            "difficulty_counts": swe.difficulty_counts,
            "repo_counts": dict(sorted(swe.repo_counts.items())),
            "selected_instance_ids": [str(row.get("instance_id")) for row in swe.selected_rows],
        },
        "phases": phases,
        "residual_debt": [
            "swe_bench_harness is currently a wiring/reference lane, not yet a same-model public uplift runner",
            "Phase 0-5 are enough for a Nexus public-candidate commercial report; Phase 7-9 upgrade external credibility",
        ],
    }


def render_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# Nexus Public Credibility Phase Plan",
        "",
        "## Rules",
        "",
    ]
    for key, value in plan["rules"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(
        [
            "",
            "## External Benchmark",
            "",
            f"- SWE-bench Verified rows: {plan['swe_bench_verified']['total_rows']}",
            f"- Phase 7 smoke rows: {plan['swe_bench_verified']['selected_rows']}",
            f"- Selected instance IDs: {', '.join(plan['swe_bench_verified']['selected_instance_ids'])}",
            "",
            "## Phases",
            "",
        ]
    )
    for phase in plan["phases"]:
        lines.append(f"### P{phase['phase']}: {phase['name']}")
        lines.append(f"- claim_scope: `{phase['claim_scope']}`")
        lines.append(f"- benchmark_family: `{phase['benchmark_family']}`")
        if phase.get("commercial_lane"):
            lines.append(f"- commercial_lane: `{phase['commercial_lane']}`")
        if phase.get("external_benchmark"):
            lines.append("- external_benchmark: `true`")
        lines.append("- acceptance:")
        for item in phase.get("acceptance", []):
            lines.append(f"  - {item}")
        lines.append("- commands:")
        for command in phase.get("commands", []):
            lines.append("")
            lines.append("```bash")
            lines.append(str(command))
            lines.append("```")
        lines.append("")
    lines.append("## Residual Debt")
    lines.append("")
    for item in plan.get("residual_debt", []):
        lines.append(f"- {item}")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Phase 0-9 public credibility benchmark plan.")
    parser.add_argument("--commercial-lanes", default=str(DEFAULT_COMMERCIAL_LANES))
    parser.add_argument("--swe-bench", default=str(DEFAULT_SWE_BENCH))
    parser.add_argument("--swe-max-tasks", type=int, default=5)
    parser.add_argument("--output-json", default="")
    parser.add_argument("--output-md", default="")
    args = parser.parse_args(argv)

    plan = build_phase_plan(
        commercial_lanes_path=args.commercial_lanes,
        swe_bench_path=args.swe_bench,
        swe_max_tasks=args.swe_max_tasks,
    )
    if args.output_json:
        out = Path(args.output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.output_md:
        out = Path(args.output_md)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_markdown(plan), encoding="utf-8")
    if not args.output_json and not args.output_md:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
