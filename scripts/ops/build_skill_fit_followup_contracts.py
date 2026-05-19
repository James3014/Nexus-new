#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_followup import (
    write_governance_candidate_v2_report,
    write_governance_mutant_lane_contract,
    write_governance_taskset_expansion_contract,
    write_research_candidate_v2_report,
    write_research_candidate_v3_report,
    write_research_external_candidate_pool,
    write_research_external_ingest_guard,
    write_research_skill_supply_gap_contract,
    write_research_source_discipline_skill_specs,
    write_skill_fit_cost_phase_contract,
    write_skill_fit_redesign_contract,
    write_skill_fit_row_level_rca,
)
from nexus.learning.governance_mutants import (
    write_governance_candidate_bound_mutant_catalog,
    write_governance_candidate_bound_mutant_matrix,
    write_governance_mutant_live_sealing,
    write_governance_mutant_matrix_preflight,
    write_governance_mutant_promotion_gate,
)


DEFAULT_GOV_SUMMARY = Path("/private/tmp/nexus_skill_fit_governance_full_live_20260516/live_summary.json")
DEFAULT_GOV_CATALOG = Path("docs/reports/NEXUS_SKILL_FIT_CATALOG_GOVERNANCE_AND_TRUST_FULL_LIVE_2026-05-16.json")
DEFAULT_GOV_RCA = Path("docs/reports/NEXUS_SKILL_FIT_ROW_LEVEL_RCA_GOVERNANCE_AND_TRUST_2026-05-17.json")
DEFAULT_POOL = Path("docs/reports/NEXUS_FAIR_SKILL_CANDIDATE_POOL_2026-05-15.json")
DEFAULT_RESEARCH_CATALOG = Path(
    "docs/reports/NEXUS_SKILL_FIT_CATALOG_RESEARCH_AND_SOURCE_DISCIPLINE_FULL_LIVE_2026-05-16.json"
)
DEFAULT_RESEARCH_REPORT = Path("docs/reports/NEXUS_RESEARCH_CANDIDATE_V2_REPORT_2026-05-17.json")
DEFAULT_RESEARCH_POOL = Path("docs/reports/NEXUS_RESEARCH_CANDIDATE_POOL_V2_2026-05-17.json")
DEFAULT_RESEARCH_V3_REPORT = Path("docs/reports/NEXUS_RESEARCH_CANDIDATE_V3_REPORT_2026-05-17.json")
DEFAULT_RESEARCH_V3_POOL = Path("docs/reports/NEXUS_RESEARCH_CANDIDATE_POOL_V3_2026-05-17.json")
DEFAULT_RESEARCH_SUPPLY_GAP = Path("docs/reports/NEXUS_RESEARCH_SKILL_SUPPLY_GAP_CONTRACT_2026-05-17.json")
DEFAULT_RESEARCH_SOURCE_DISCIPLINE_SPECS = Path(
    "docs/reports/NEXUS_RESEARCH_SOURCE_DISCIPLINE_SKILL_SPECS_2026-05-17.json"
)
DEFAULT_RESEARCH_EXTERNAL_INGEST_GUARD = Path(
    "docs/reports/NEXUS_RESEARCH_EXTERNAL_INGEST_GUARD_2026-05-17.json"
)
DEFAULT_RESEARCH_EXTERNAL_CANDIDATE_POOL = Path(
    "docs/reports/NEXUS_RESEARCH_EXTERNAL_CANDIDATE_POOL_2026-05-17.json"
)
DEFAULT_GOV_V2_REPORT = Path("docs/reports/NEXUS_GOVERNANCE_CANDIDATE_V2_REPORT_2026-05-17.json")
DEFAULT_GOV_V2_POOL = Path("docs/reports/NEXUS_GOVERNANCE_CANDIDATE_POOL_V2_2026-05-17.json")
DEFAULT_REDESIGN_CONTRACT = Path("docs/reports/NEXUS_SKILL_FIT_REDESIGN_CONTRACT_2026-05-17.json")
DEFAULT_COST_PHASE_CONTRACT = Path("docs/reports/NEXUS_SKILL_FIT_COST_PHASE_CONTRACT_2026-05-17.json")
DEFAULT_GOV_TASKSET_EXPANSION = Path("docs/reports/NEXUS_GOVERNANCE_TASKSET_EXPANSION_CONTRACT_2026-05-17.json")
DEFAULT_GOV_MUTANT_LANE = Path("docs/reports/NEXUS_GOVERNANCE_MUTANT_LANE_CONTRACT_2026-05-17.json")
DEFAULT_GOV_MUTANT_MATRIX = Path("docs/reports/NEXUS_GOVERNANCE_MUTANT_MATRIX_PREFLIGHT_2026-05-17.json")
DEFAULT_GOV_MUTANT_PROMOTION = Path("docs/reports/NEXUS_GOVERNANCE_MUTANT_PROMOTION_GATE_2026-05-17.json")
DEFAULT_GOV_MUTANT_LIVE_SEALING = Path("docs/reports/NEXUS_GOVERNANCE_MUTANT_LIVE_SEALING_2026-05-17.json")
DEFAULT_GOV_CANDIDATE_MUTANT_MATRIX = Path(
    "docs/reports/NEXUS_GOVERNANCE_CANDIDATE_BOUND_MUTANT_MATRIX_2026-05-17.json"
)
DEFAULT_GOV_CANDIDATE_MUTANT_LIVE_SUMMARY = Path(
    "/private/tmp/nexus_governance_candidate_bound_mutant_live_20260517/live_summary.json"
)
DEFAULT_GOV_CANDIDATE_MUTANT_CATALOG = Path(
    "docs/reports/NEXUS_GOVERNANCE_CANDIDATE_BOUND_MUTANT_CATALOG_2026-05-17.json"
)
DEFAULT_GOV_TASKSET_MANIFESTS = (
    "scripts/bench/public_benchmark_nexus_value_v1.json",
    "scripts/bench/public_benchmark_rlm_harder_v2.json",
    "scripts/bench/public_benchmark_model_required_uplift_v1.json",
    "scripts/bench/public_benchmark_pilot_v1.json",
    "scripts/bench/public_benchmark_commercial_expansion_v1.json",
    "scripts/bench/public_benchmark_docs_lane_v1.json",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build skill-fit follow-up RCA and candidate-v2 contracts.")
    parser.add_argument("--governance-summary", default=str(DEFAULT_GOV_SUMMARY))
    parser.add_argument("--governance-catalog", default=str(DEFAULT_GOV_CATALOG))
    parser.add_argument("--governance-rca-output", default=str(DEFAULT_GOV_RCA))
    parser.add_argument("--candidate-pool", default=str(DEFAULT_POOL))
    parser.add_argument("--research-catalog", default=str(DEFAULT_RESEARCH_CATALOG))
    parser.add_argument("--research-v2-output", default=str(DEFAULT_RESEARCH_REPORT))
    parser.add_argument("--research-v2-pool-output", default=str(DEFAULT_RESEARCH_POOL))
    parser.add_argument("--research-v3-output", default=str(DEFAULT_RESEARCH_V3_REPORT))
    parser.add_argument("--research-v3-pool-output", default=str(DEFAULT_RESEARCH_V3_POOL))
    parser.add_argument("--research-supply-gap-output", default=str(DEFAULT_RESEARCH_SUPPLY_GAP))
    parser.add_argument("--research-source-discipline-specs-output", default=str(DEFAULT_RESEARCH_SOURCE_DISCIPLINE_SPECS))
    parser.add_argument("--research-external-ingest-guard-output", default=str(DEFAULT_RESEARCH_EXTERNAL_INGEST_GUARD))
    parser.add_argument("--research-external-candidate-pool-output", default=str(DEFAULT_RESEARCH_EXTERNAL_CANDIDATE_POOL))
    parser.add_argument("--research-supply-gap-catalog", action="append", default=[])
    parser.add_argument("--governance-v2-output", default=str(DEFAULT_GOV_V2_REPORT))
    parser.add_argument("--governance-v2-pool-output", default=str(DEFAULT_GOV_V2_POOL))
    parser.add_argument("--redesign-output", default=str(DEFAULT_REDESIGN_CONTRACT))
    parser.add_argument("--cost-phase-summary")
    parser.add_argument("--cost-phase-catalog")
    parser.add_argument("--cost-phase-output", default=str(DEFAULT_COST_PHASE_CONTRACT))
    parser.add_argument("--cost-phase-capability", default="")
    parser.add_argument("--governance-taskset-output", default=str(DEFAULT_GOV_TASKSET_EXPANSION))
    parser.add_argument("--governance-mutant-output", default=str(DEFAULT_GOV_MUTANT_LANE))
    parser.add_argument("--governance-mutant-matrix-output", default=str(DEFAULT_GOV_MUTANT_MATRIX))
    parser.add_argument("--governance-mutant-promotion-output", default=str(DEFAULT_GOV_MUTANT_PROMOTION))
    parser.add_argument("--governance-mutant-live-sealing-output", default=str(DEFAULT_GOV_MUTANT_LIVE_SEALING))
    parser.add_argument("--governance-candidate-mutant-matrix-output", default=str(DEFAULT_GOV_CANDIDATE_MUTANT_MATRIX))
    parser.add_argument("--governance-candidate-mutant-live-summary", default=str(DEFAULT_GOV_CANDIDATE_MUTANT_LIVE_SUMMARY))
    parser.add_argument("--governance-candidate-mutant-catalog-output", default=str(DEFAULT_GOV_CANDIDATE_MUTANT_CATALOG))
    parser.add_argument("--governance-candidate-mutant-max-candidates", type=int, default=2)
    parser.add_argument("--governance-mutant-min-per-bucket", type=int, default=1)
    parser.add_argument("--governance-taskset-manifest", action="append", default=[])
    parser.add_argument("--governance-taskset-min-total", type=int, default=15)
    parser.add_argument("--governance-taskset-max-total", type=int, default=20)
    parser.add_argument("--governance-taskset-min-per-bucket", type=int, default=3)
    parser.add_argument("--max-research-candidates", type=int, default=4)
    parser.add_argument("--min-research-v3-behavior-groups", type=int, default=2)
    parser.add_argument("--max-governance-candidates", type=int, default=4)
    parser.add_argument("--skip-governance-rca", action="store_true")
    parser.add_argument("--skip-governance-v2", action="store_true")
    parser.add_argument("--skip-research-v2", action="store_true")
    parser.add_argument("--skip-research-v3", action="store_true")
    parser.add_argument("--skip-research-supply-gap", action="store_true")
    parser.add_argument("--skip-research-source-discipline-specs", action="store_true")
    parser.add_argument("--skip-research-external-ingest-guard", action="store_true")
    parser.add_argument("--skip-research-external-candidate-pool", action="store_true")
    parser.add_argument("--skip-redesign", action="store_true")
    parser.add_argument("--skip-cost-phase", action="store_true")
    parser.add_argument("--skip-governance-taskset", action="store_true")
    parser.add_argument("--skip-governance-mutant", action="store_true")
    parser.add_argument("--skip-governance-mutant-matrix", action="store_true")
    parser.add_argument("--skip-governance-mutant-promotion", action="store_true")
    parser.add_argument("--skip-governance-mutant-live-sealing", action="store_true")
    parser.add_argument("--skip-governance-candidate-mutant-matrix", action="store_true")
    parser.add_argument("--skip-governance-candidate-mutant-catalog", action="store_true")
    args = parser.parse_args(argv)

    outputs: dict[str, object] = {"status": "PASS"}
    if not args.skip_governance_rca:
        gov_rca = write_skill_fit_row_level_rca(
            run_summary_path=args.governance_summary,
            catalog_path=args.governance_catalog,
            output_path=args.governance_rca_output,
            capability="governance_and_trust",
        )
        outputs["governance_rca"] = {
            "output": args.governance_rca_output,
            "status": gov_rca["status"],
            "summary": gov_rca["summary"],
            "root_cause": gov_rca["root_cause"],
        }
        if gov_rca["status"] != "PASS":
            outputs["status"] = "RETURN"

    if not args.skip_research_v2:
        research_v2 = write_research_candidate_v2_report(
            candidate_pool_path=args.candidate_pool,
            previous_catalog_path=args.research_catalog,
            output_path=args.research_v2_output,
            candidate_pool_v2_path=args.research_v2_pool_output,
            max_candidates=args.max_research_candidates,
        )
        outputs["research_candidate_v2"] = {
            "output": args.research_v2_output,
            "candidate_pool_output": args.research_v2_pool_output,
            "status": research_v2["status"],
            "summary": research_v2["summary"],
            "selected_skill_ids": [item["skill_id"] for item in research_v2["selected_candidates"]],
        }
        if research_v2["status"] != "PASS":
            outputs["status"] = "RETURN"

    if not args.skip_research_v3:
        research_v3 = write_research_candidate_v3_report(
            candidate_pool_path=args.candidate_pool,
            previous_catalog_path=args.research_catalog,
            output_path=args.research_v3_output,
            candidate_pool_v3_path=args.research_v3_pool_output,
            max_candidates=args.max_research_candidates,
            min_behavior_groups=args.min_research_v3_behavior_groups,
        )
        outputs["research_candidate_v3"] = {
            "output": args.research_v3_output,
            "candidate_pool_output": args.research_v3_pool_output,
            "status": research_v3["status"],
            "summary": research_v3["summary"],
            "selected_skill_ids": [item["skill_id"] for item in research_v3["selected_candidates"]],
        }
        if research_v3["status"] != "PASS":
            outputs["status"] = "RETURN"

    if not args.skip_research_supply_gap:
        supply_gap_catalogs = args.research_supply_gap_catalog or [
            args.research_catalog,
            "docs/reports/NEXUS_SKILL_FIT_CATALOG_RESEARCH_AND_SOURCE_DISCIPLINE_V2_FULL_LIVE_2026-05-17.json",
        ]
        supply_gap = write_research_skill_supply_gap_contract(
            candidate_pool_path=args.candidate_pool,
            previous_catalog_paths=supply_gap_catalogs,
            output_path=args.research_supply_gap_output,
            v3_report_path=args.research_v3_output,
            min_behavior_groups=args.min_research_v3_behavior_groups,
        )
        outputs["research_skill_supply_gap"] = {
            "output": args.research_supply_gap_output,
            "status": supply_gap["status"],
            "summary": supply_gap["summary"],
            "research_live_allowed": supply_gap["research_live_allowed"],
        }

    if not args.skip_research_source_discipline_specs:
        source_specs = write_research_source_discipline_skill_specs(
            supply_gap_contract_path=args.research_supply_gap_output,
            output_path=args.research_source_discipline_specs_output,
        )
        outputs["research_source_discipline_skill_specs"] = {
            "output": args.research_source_discipline_specs_output,
            "status": source_specs["status"],
            "summary": source_specs["summary"],
            "research_live_allowed": source_specs["research_live_allowed"],
        }
        if source_specs["status"] != "PASS":
            outputs["status"] = "RETURN"

    if not args.skip_research_external_ingest_guard:
        ingest_guard = write_research_external_ingest_guard(
            source_specs_contract_path=args.research_source_discipline_specs_output,
            output_path=args.research_external_ingest_guard_output,
        )
        outputs["research_external_ingest_guard"] = {
            "output": args.research_external_ingest_guard_output,
            "status": ingest_guard["status"],
            "summary": ingest_guard["summary"],
            "runtime_update_allowed": ingest_guard["runtime_update_allowed"],
        }
        if ingest_guard["status"] != "PASS":
            outputs["status"] = "RETURN"

    if not args.skip_research_external_candidate_pool:
        external_pool = write_research_external_candidate_pool(
            source_specs_contract_path=args.research_source_discipline_specs_output,
            output_path=args.research_external_candidate_pool_output,
        )
        outputs["research_external_candidate_pool"] = {
            "output": args.research_external_candidate_pool_output,
            "status": external_pool["status"],
            "summary": external_pool["summary"],
        }
        if external_pool["status"] != "PASS":
            outputs["status"] = "RETURN"

    if not args.skip_governance_v2:
        governance_v2 = write_governance_candidate_v2_report(
            candidate_pool_path=args.candidate_pool,
            previous_catalog_path=args.governance_catalog,
            output_path=args.governance_v2_output,
            candidate_pool_v2_path=args.governance_v2_pool_output,
            max_candidates=args.max_governance_candidates,
        )
        outputs["governance_candidate_v2"] = {
            "output": args.governance_v2_output,
            "candidate_pool_output": args.governance_v2_pool_output,
            "status": governance_v2["status"],
            "summary": governance_v2["summary"],
            "selected_skill_ids": [item["skill_id"] for item in governance_v2["selected_candidates"]],
        }
        if governance_v2["status"] != "PASS":
            outputs["status"] = "RETURN"

    if not args.skip_cost_phase and args.cost_phase_summary and args.cost_phase_catalog:
        cost_phase = write_skill_fit_cost_phase_contract(
            run_summary_path=args.cost_phase_summary,
            catalog_path=args.cost_phase_catalog,
            output_path=args.cost_phase_output,
            capability=args.cost_phase_capability,
        )
        outputs["cost_phase_contract"] = {
            "output": args.cost_phase_output,
            "status": cost_phase["status"],
            "summary": cost_phase["summary"],
        }
        if cost_phase["status"] != "PASS":
            outputs["status"] = "RETURN"

    if not args.skip_governance_taskset:
        manifests = args.governance_taskset_manifest or list(DEFAULT_GOV_TASKSET_MANIFESTS)
        governance_taskset = write_governance_taskset_expansion_contract(
            manifest_paths=manifests,
            output_path=args.governance_taskset_output,
            min_total_tasks=args.governance_taskset_min_total,
            max_total_tasks=args.governance_taskset_max_total,
            min_tasks_per_bucket=args.governance_taskset_min_per_bucket,
        )
        outputs["governance_taskset_expansion"] = {
            "output": args.governance_taskset_output,
            "status": governance_taskset["status"],
            "live_ready": governance_taskset["live_ready"],
            "summary": governance_taskset["summary"],
        }
        if governance_taskset["status"] != "PASS":
            outputs["status"] = "RETURN"

    if not args.skip_governance_mutant:
        mutant_lane = write_governance_mutant_lane_contract(
            taskset_contract_path=args.governance_taskset_output,
            output_path=args.governance_mutant_output,
            min_mutants_per_bucket=args.governance_mutant_min_per_bucket,
        )
        outputs["governance_mutant_lane"] = {
            "output": args.governance_mutant_output,
            "status": mutant_lane["status"],
            "live_ready": mutant_lane["live_ready"],
            "summary": mutant_lane["summary"],
        }
        if mutant_lane["status"] != "PASS":
            outputs["status"] = "RETURN"

    if not args.skip_governance_mutant_matrix:
        mutant_matrix = write_governance_mutant_matrix_preflight(
            mutant_lane_path=args.governance_mutant_output,
            taskset_contract_path=args.governance_taskset_output,
            output_path=args.governance_mutant_matrix_output,
        )
        outputs["governance_mutant_matrix_preflight"] = {
            "output": args.governance_mutant_matrix_output,
            "status": mutant_matrix["status"],
            "live_ready": mutant_matrix["live_ready"],
            "summary": mutant_matrix["summary"],
        }
        if mutant_matrix["status"] != "PASS":
            outputs["status"] = "RETURN"

    if not args.skip_governance_mutant_live_sealing:
        mutant_live = write_governance_mutant_live_sealing(
            mutant_matrix_path=args.governance_mutant_matrix_output,
            output_path=args.governance_mutant_live_sealing_output,
        )
        outputs["governance_mutant_live_sealing"] = {
            "output": args.governance_mutant_live_sealing_output,
            "status": mutant_live["status"],
            "summary": mutant_live["summary"],
            "promotion_allowed": mutant_live["promotion_allowed"],
        }
        if mutant_live["status"] != "PASS":
            outputs["status"] = "RETURN"

    if not args.skip_governance_candidate_mutant_matrix:
        candidate_mutant_matrix = write_governance_candidate_bound_mutant_matrix(
            mutant_matrix_path=args.governance_mutant_matrix_output,
            candidate_report_path=args.governance_v2_output,
            output_path=args.governance_candidate_mutant_matrix_output,
            max_candidates=args.governance_candidate_mutant_max_candidates,
        )
        outputs["governance_candidate_bound_mutant_matrix"] = {
            "output": args.governance_candidate_mutant_matrix_output,
            "status": candidate_mutant_matrix["status"],
            "summary": candidate_mutant_matrix["summary"],
        }
        if candidate_mutant_matrix["status"] != "PASS":
            outputs["status"] = "RETURN"

    if not args.skip_governance_candidate_mutant_catalog and Path(args.governance_candidate_mutant_live_summary).exists():
        candidate_mutant_catalog = write_governance_candidate_bound_mutant_catalog(
            run_summary_path=args.governance_candidate_mutant_live_summary,
            output_path=args.governance_candidate_mutant_catalog_output,
        )
        outputs["governance_candidate_bound_mutant_catalog"] = {
            "output": args.governance_candidate_mutant_catalog_output,
            "status": candidate_mutant_catalog["status"],
            "promotion_allowed": candidate_mutant_catalog["promotion_allowed"],
            "summary": candidate_mutant_catalog["summary"],
        }

    if not args.skip_governance_mutant_promotion:
        mutant_promotion = write_governance_mutant_promotion_gate(
            mutant_matrix_path=args.governance_mutant_matrix_output,
            output_path=args.governance_mutant_promotion_output,
        )
        outputs["governance_mutant_promotion_gate"] = {
            "output": args.governance_mutant_promotion_output,
            "status": mutant_promotion["status"],
            "gate_verdict": mutant_promotion["gate_verdict"],
            "promotion_allowed": mutant_promotion["promotion_allowed"],
            "summary": mutant_promotion["summary"],
        }

    if not args.skip_redesign:
        redesign = write_skill_fit_redesign_contract(
            catalog_paths={
                "governance": args.governance_catalog,
                "research": args.research_catalog,
            },
            output_path=args.redesign_output,
        )
        outputs["redesign_contract"] = {
            "output": args.redesign_output,
            "status": redesign["status"],
            "summary": redesign["summary"],
            "flash100_allowed": redesign["flash100_allowed"],
        }
        if redesign["status"] != "PASS":
            outputs["status"] = "RETURN"

    print(json.dumps(outputs, ensure_ascii=False, sort_keys=True))
    return 0 if outputs["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
