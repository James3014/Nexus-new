#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_route_taxonomy import (
    build_sf2_ablation_matrix_plan,
    build_sf2_candidate_materialization_bundle,
    build_sf2_candidate_spec_overlay,
    build_sf2_candidate_quality_screen,
    build_sf2_closure_gate,
    build_sf2_bounded_probe_plan,
    build_sf2_bounded_probe_preflight,
    build_sf2_bounded_probe_task_manifest,
    build_sf2_bounded_probe_execution_manifest,
    build_sf2_bounded_probe_chunk_plan,
    build_sf2_materialization_batch_plan,
    build_route_capability_taxonomy,
    build_sf2_capability_candidate_selection,
    build_sf2_metadata_repair_plan,
    build_sf2_spec_repaired_candidate_pool,
    build_skill_route_reclassification,
    write_json_report,
)


DEFAULT_POOL = Path("docs/reports/NEXUS_FAIR_SKILL_CANDIDATE_POOL_2026-05-17_SF_REFRESH.json")
DEFAULT_TAXONOMY = Path("docs/reports/NEXUS_SF2_ROUTE_CAPABILITY_TAXONOMY_2026-05-18.json")
DEFAULT_RECLASSIFICATION = Path("docs/reports/NEXUS_SF2_SKILL_RECLASSIFICATION_2026-05-18.json")
DEFAULT_SELECTION = Path("docs/reports/NEXUS_SF2_CAPABILITY_CANDIDATE_SELECTION_2026-05-18.json")
DEFAULT_REPAIR_PLAN = Path("docs/reports/NEXUS_SF2_METADATA_REPAIR_PLAN_2026-05-18.json")
DEFAULT_MATRIX_PLAN = Path("docs/reports/NEXUS_SF2_ABLATION_MATRIX_PLAN_2026-05-18.json")
DEFAULT_QUALITY_SCREEN = Path("docs/reports/NEXUS_SF2_CANDIDATE_QUALITY_SCREEN_2026-05-18.json")
DEFAULT_SPEC_OVERLAY = Path("docs/reports/NEXUS_SF2_CANDIDATE_SPEC_OVERLAY_2026-05-18.json")
DEFAULT_SPEC_POOL = Path("docs/reports/NEXUS_SF2_SPEC_REPAIRED_CANDIDATE_POOL_2026-05-18.json")
DEFAULT_SPEC_QUALITY = Path("docs/reports/NEXUS_SF2_SPEC_REPAIRED_QUALITY_SCREEN_2026-05-18.json")
DEFAULT_SPEC_MATRIX = Path("docs/reports/NEXUS_SF2_SPEC_REPAIRED_ABLATION_MATRIX_PLAN_2026-05-18.json")
DEFAULT_MATERIALIZATION = Path("docs/reports/NEXUS_SF2_CANDIDATE_MATERIALIZATION_BUNDLE_2026-05-18.json")
DEFAULT_MATERIALIZATION_BATCH_PLAN = Path("docs/reports/NEXUS_SF2_MATERIALIZATION_BATCH_PLAN_2026-05-18.json")
DEFAULT_CLOSURE_GATE = Path("docs/reports/NEXUS_SF2_CLOSURE_GATE_2026-05-18.json")
DEFAULT_ASSET_STATUS = Path("docs/reports/NEXUS_SF2_CANDIDATE_ASSET_STATUS_2026-05-18.json")
DEFAULT_BOUNDED_PROBE_PLAN = Path("docs/reports/NEXUS_SF2_BOUNDED_PROBE_PLAN_2026-05-18.json")
DEFAULT_BOUNDED_PROBE_PREFLIGHT = Path("docs/reports/NEXUS_SF2_BOUNDED_PROBE_PREFLIGHT_2026-05-18.json")
DEFAULT_BOUNDED_PROBE_TASK_MANIFEST = Path("docs/reports/NEXUS_SF2_BOUNDED_PROBE_TASK_MANIFEST_2026-05-18.json")
DEFAULT_BOUNDED_PROBE_EXECUTION_MANIFEST = Path(
    "docs/reports/NEXUS_SF2_BOUNDED_PROBE_EXECUTION_MANIFEST_2026-05-18.json"
)
DEFAULT_BOUNDED_PROBE_CHUNK_PLAN = Path("docs/reports/NEXUS_SF2_BOUNDED_PROBE_CHUNK_PLAN_2026-05-18.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build SF-v2 route taxonomy and skill reclassification reports.")
    parser.add_argument("--candidate-pool", default=str(DEFAULT_POOL))
    parser.add_argument("--taxonomy-output", default=str(DEFAULT_TAXONOMY))
    parser.add_argument("--reclassification-output", default=str(DEFAULT_RECLASSIFICATION))
    parser.add_argument("--selection-output", default=str(DEFAULT_SELECTION))
    parser.add_argument("--metadata-repair-output", default=str(DEFAULT_REPAIR_PLAN))
    parser.add_argument("--ablation-matrix-output", default=str(DEFAULT_MATRIX_PLAN))
    parser.add_argument("--quality-screen-output", default=str(DEFAULT_QUALITY_SCREEN))
    parser.add_argument("--spec-overlay-output", default=str(DEFAULT_SPEC_OVERLAY))
    parser.add_argument("--spec-repaired-pool-output", default=str(DEFAULT_SPEC_POOL))
    parser.add_argument("--spec-repaired-quality-output", default=str(DEFAULT_SPEC_QUALITY))
    parser.add_argument("--spec-repaired-matrix-output", default=str(DEFAULT_SPEC_MATRIX))
    parser.add_argument("--candidate-materialization-output", default=str(DEFAULT_MATERIALIZATION))
    parser.add_argument("--materialization-batch-plan-output", default=str(DEFAULT_MATERIALIZATION_BATCH_PLAN))
    parser.add_argument("--closure-gate-output", default=str(DEFAULT_CLOSURE_GATE))
    parser.add_argument("--asset-status-input", default=str(DEFAULT_ASSET_STATUS))
    parser.add_argument("--bounded-probe-plan-output", default=str(DEFAULT_BOUNDED_PROBE_PLAN))
    parser.add_argument("--bounded-probe-preflight-output", default=str(DEFAULT_BOUNDED_PROBE_PREFLIGHT))
    parser.add_argument("--bounded-probe-task-manifest-output", default=str(DEFAULT_BOUNDED_PROBE_TASK_MANIFEST))
    parser.add_argument("--bounded-probe-execution-manifest-output", default=str(DEFAULT_BOUNDED_PROBE_EXECUTION_MANIFEST))
    parser.add_argument("--bounded-probe-chunk-plan-output", default=str(DEFAULT_BOUNDED_PROBE_CHUNK_PLAN))
    parser.add_argument("--max-candidates-per-capability", type=int, default=8)
    parser.add_argument("--max-skill-arms-per-capability", type=int, default=4)
    parser.add_argument(
        "--no-metadata-repair-overlay",
        action="store_true",
        help="Keep metadata-repair-only capabilities blocked instead of planning ablation-only repaired arms.",
    )
    args = parser.parse_args(argv)

    candidate_pool = json.loads(Path(args.candidate_pool).read_text(encoding="utf-8"))
    taxonomy = build_route_capability_taxonomy()
    reclassification = build_skill_route_reclassification(candidate_pool)
    selection = build_sf2_capability_candidate_selection(
        reclassification,
        max_candidates_per_capability=args.max_candidates_per_capability,
    )
    metadata_repair = build_sf2_metadata_repair_plan(selection)
    ablation_matrix = build_sf2_ablation_matrix_plan(
        selection,
        max_skill_arms_per_capability=args.max_skill_arms_per_capability,
        allow_metadata_repair_overlay=not args.no_metadata_repair_overlay,
    )
    quality_screen = build_sf2_candidate_quality_screen(reclassification, selection)
    spec_overlay = build_sf2_candidate_spec_overlay(quality_screen)
    spec_pool = build_sf2_spec_repaired_candidate_pool(candidate_pool, spec_overlay)
    spec_reclassification = build_skill_route_reclassification(spec_pool)
    spec_selection = build_sf2_capability_candidate_selection(
        spec_reclassification,
        max_candidates_per_capability=args.max_candidates_per_capability,
    )
    spec_quality_screen = build_sf2_candidate_quality_screen(spec_reclassification, spec_selection)
    spec_ablation_matrix = build_sf2_ablation_matrix_plan(
        spec_selection,
        max_skill_arms_per_capability=args.max_skill_arms_per_capability,
        allow_metadata_repair_overlay=not args.no_metadata_repair_overlay,
    )
    materialization = build_sf2_candidate_materialization_bundle(spec_overlay)
    materialization_batch_plan = build_sf2_materialization_batch_plan(materialization)
    closure_gate = build_sf2_closure_gate(spec_quality_screen, spec_ablation_matrix, materialization)
    asset_status_path = Path(args.asset_status_input)
    asset_status = json.loads(asset_status_path.read_text(encoding="utf-8")) if asset_status_path.exists() else {}
    bounded_probe_plan = build_sf2_bounded_probe_plan(spec_ablation_matrix, asset_status)
    bounded_probe_preflight = build_sf2_bounded_probe_preflight(spec_ablation_matrix, asset_status)
    bounded_probe_task_manifest = build_sf2_bounded_probe_task_manifest(taxonomy)
    bounded_probe_execution_manifest = build_sf2_bounded_probe_execution_manifest(
        spec_ablation_matrix,
        bounded_probe_task_manifest,
    )
    bounded_probe_chunk_plan = build_sf2_bounded_probe_chunk_plan(bounded_probe_execution_manifest)
    write_json_report(taxonomy, args.taxonomy_output)
    write_json_report(reclassification, args.reclassification_output)
    write_json_report(selection, args.selection_output)
    write_json_report(metadata_repair, args.metadata_repair_output)
    write_json_report(ablation_matrix, args.ablation_matrix_output)
    write_json_report(quality_screen, args.quality_screen_output)
    write_json_report(spec_overlay, args.spec_overlay_output)
    write_json_report(spec_pool, args.spec_repaired_pool_output)
    write_json_report(spec_quality_screen, args.spec_repaired_quality_output)
    write_json_report(spec_ablation_matrix, args.spec_repaired_matrix_output)
    write_json_report(materialization, args.candidate_materialization_output)
    write_json_report(materialization_batch_plan, args.materialization_batch_plan_output)
    write_json_report(closure_gate, args.closure_gate_output)
    write_json_report(bounded_probe_plan, args.bounded_probe_plan_output)
    write_json_report(bounded_probe_preflight, args.bounded_probe_preflight_output)
    write_json_report(bounded_probe_task_manifest, args.bounded_probe_task_manifest_output)
    write_json_report(bounded_probe_execution_manifest, args.bounded_probe_execution_manifest_output)
    write_json_report(bounded_probe_chunk_plan, args.bounded_probe_chunk_plan_output)
    print(
        json.dumps(
            {
                "status": "PASS",
                "taxonomy_output": args.taxonomy_output,
                "reclassification_output": args.reclassification_output,
                "selection_output": args.selection_output,
                "metadata_repair_output": args.metadata_repair_output,
                "ablation_matrix_output": args.ablation_matrix_output,
                "quality_screen_output": args.quality_screen_output,
                "spec_overlay_output": args.spec_overlay_output,
                "spec_repaired_pool_output": args.spec_repaired_pool_output,
                "spec_repaired_quality_output": args.spec_repaired_quality_output,
                "spec_repaired_matrix_output": args.spec_repaired_matrix_output,
                "candidate_materialization_output": args.candidate_materialization_output,
                "materialization_batch_plan_output": args.materialization_batch_plan_output,
                "closure_gate_output": args.closure_gate_output,
                "bounded_probe_plan_output": args.bounded_probe_plan_output,
                "bounded_probe_preflight_output": args.bounded_probe_preflight_output,
                "bounded_probe_task_manifest_output": args.bounded_probe_task_manifest_output,
                "bounded_probe_execution_manifest_output": args.bounded_probe_execution_manifest_output,
                "bounded_probe_chunk_plan_output": args.bounded_probe_chunk_plan_output,
                "taxonomy_capabilities": taxonomy["summary"]["capability_count"],
                "classified_skill_count": reclassification["summary"]["classified_skill_count"],
                "low_confidence_primary_count": reclassification["summary"]["low_confidence_primary_count"],
                "metadata_repair_item_count": metadata_repair["summary"]["repair_item_count"],
                "ablation_matrix_status": ablation_matrix["status"],
                "ablation_ready_capability_count": ablation_matrix["summary"]["ready_capability_count"],
                "ablation_blocked_capability_count": ablation_matrix["summary"]["blocked_capability_count"],
                "ablation_planned_row_count": ablation_matrix["summary"]["planned_row_count"],
                "quality_screen_status": quality_screen["status"],
                "quality_review_candidate_count": quality_screen["summary"]["review_candidate_count"],
                "spec_candidate_count": spec_overlay["summary"]["spec_candidate_count"],
                "spec_repaired_quality_status": spec_quality_screen["status"],
                "spec_repaired_capabilities_without_clean_candidates": spec_quality_screen["summary"][
                    "capabilities_without_clean_candidates"
                ],
                "spec_repaired_ablation_ready_capability_count": spec_ablation_matrix["summary"][
                    "ready_capability_count"
                ],
                "spec_repaired_ablation_planned_row_count": spec_ablation_matrix["summary"]["planned_row_count"],
                "materialization_asset_count": materialization["summary"]["asset_count"],
                "materialization_batch_count": materialization_batch_plan["summary"]["batch_count"],
                "closure_gate_status": closure_gate["status"],
                "bounded_probe_allowed": closure_gate["summary"]["bounded_probe_allowed"],
                "bounded_probe_plan_status": bounded_probe_plan["status"],
                "bounded_probe_plan_allowed": bounded_probe_plan["summary"]["bounded_probe_allowed"],
                "bounded_probe_preflight_status": bounded_probe_preflight["status"],
                "bounded_probe_live_allowed": bounded_probe_preflight["summary"]["bounded_probe_live_allowed"],
                "bounded_probe_task_count": bounded_probe_task_manifest["summary"]["task_count"],
                "bounded_probe_execution_row_count": bounded_probe_execution_manifest["summary"]["row_count"],
                "bounded_probe_execution_ready": bounded_probe_execution_manifest["summary"]["ready_for_sf2_live_probe"],
                "bounded_probe_chunk_count": bounded_probe_chunk_plan["summary"]["chunk_count"],
                **selection["summary"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
