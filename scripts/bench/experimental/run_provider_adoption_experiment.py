#!/usr/bin/env python3
"""CLI runner for Provider Adoption Experiments in Nexus.

Runs the generic G0 to G6 provider adoption pipeline:
G0: Contract Validation
G1: Physical Identity Inspection
G2: Capability Probing
G3: Frozen Cohort Evaluation
G4: Operational Metrics
G5: Failure Behavior Matrix
G6: Advisory Admission Recommendation

Usage:
    python scripts/bench/experimental/run_provider_adoption_experiment.py --candidate simulated
    python scripts/bench/experimental/run_provider_adoption_experiment.py --candidate apple-fm
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from nexus.calibration.provider_adoption.adapter import (
    CandidateAdapter,
    SimulatedCandidateAdapter,
)
from nexus.calibration.provider_adoption.apple_fm_adapter import AppleFMCandidateAdapter
from nexus.calibration.provider_adoption.capability import (
    CAP_001_PLAIN_TEXT,
    CAP_002_STRUCTURED_JSON,
    CAP_004_CLASSIFICATION,
    CAP_005_EXTRACTION,
    CAP_006_SUMMARIZATION,
)
from nexus.calibration.provider_adoption.cohort import (
    CohortCase,
    CohortType,
    FrozenCohort,
    create_frozen_cohort,
)
from nexus.calibration.provider_adoption.contracts import (
    AuthorityBoundary,
    CandidateIdentity,
    DatasetRef,
    EnvironmentConstraints,
    MetricsConfig,
    PassThresholds,
    StopConditions,
    build_experiment_contract,
)
from nexus.calibration.provider_adoption.evidence_bundle import (
    build_evidence_bundle,
    generate_13_question_report,
)
from nexus.calibration.provider_adoption.orchestrator import run_provider_adoption_experiment


def build_default_fixture_cohort() -> FrozenCohort:
    cases = [
        CohortCase(
            case_id="CASE-001",
            task_class="classification",
            input_prompt="Classify the sentiment of this text: 'The build passed cleanly without errors.' Options: POSITIVE, NEGATIVE, NEUTRAL.",
            ground_truth="POSITIVE",
            acceptable_variants=("positive", "POSITIVE."),
        ),
        CohortCase(
            case_id="CASE-002",
            task_class="extraction",
            input_prompt="Extract the error code from this message: 'Process exited with code 137 (OOM killed)'",
            ground_truth="137",
            acceptable_variants=("code 137", "137 (OOM killed)"),
        ),
        CohortCase(
            case_id="CASE-003",
            task_class="summarization",
            input_prompt="Summarize this status: 'Database connection failed after 3 retries due to connection timeout.'",
            ground_truth="Database connection timed out after 3 retries.",
            acceptable_variants=(
                "database connection timed out after 3 retries.",
                "database timeout after 3 retries",
            ),
        ),
    ]
    return create_frozen_cohort(
        cohort_id="COHORT-DEVSPACE-FAILURES-FIXTURE-V1",
        cohort_revision=1,
        cohort_type=CohortType.FIXTURE_COHORT,
        cases=cases,
        ground_truth_ready=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Provider Adoption Experiment")
    parser.add_argument(
        "--candidate",
        choices=["apple-fm", "simulated"],
        default="apple-fm",
        help="Candidate adapter to evaluate",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default="",
        help="Path to write evidence bundle JSON",
    )
    parser.add_argument(
        "--output-report",
        type=str,
        default="",
        help="Path to write human markdown report",
    )
    args = parser.parse_args()

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cohort = build_default_fixture_cohort()

    if args.candidate == "apple-fm":
        candidate_identity = CandidateIdentity(
            provider_id="apple-fm",
            model_id="apple-foundation-model-v1",
            transport="apple_fm_cli",
            runtime="/usr/bin/fm",
        )
        adapter: CandidateAdapter = AppleFMCandidateAdapter()
        claim_ceiling = "L0.5"
    else:
        candidate_identity = CandidateIdentity(
            provider_id="simulated",
            model_id="sim-v1",
            transport="in_memory",
            runtime="simulated_runtime",
        )
        adapter = SimulatedCandidateAdapter()
        claim_ceiling = "L1"

    dataset_ref = DatasetRef(
        cohort_id=cohort.cohort_id,
        cohort_revision=cohort.cohort_revision,
        cohort_sha256=cohort.cohort_sha256,
        ground_truth_revision=cohort.ground_truth_revision,
        ground_truth_sha256=cohort.ground_truth_sha256,
        leakage_policy_revision=1,
        cohort_type=cohort.cohort_type,
        ground_truth_ready=cohort.ground_truth_ready,
    )

    contract = build_experiment_contract(
        experiment_id=f"EXP-{args.candidate.upper()}-PILOT-V1",
        experiment_revision=1,
        candidate=candidate_identity,
        baseline=None,
        job_to_be_done="Read-only extraction, classification, and summarization candidate qualification.",
        allowed_capabilities=(
            CAP_001_PLAIN_TEXT,
            CAP_002_STRUCTURED_JSON,
            CAP_004_CLASSIFICATION,
            CAP_005_EXTRACTION,
            CAP_006_SUMMARIZATION,
        ),
        forbidden_capabilities=(
            "file_mutation",
            "process_execution",
            "network_access",
            "routing_authority",
            "acceptance_authority",
        ),
        dataset=dataset_ref,
        metrics_config=MetricsConfig(
            latency_p50_max_ms=500,
            latency_p95_max_ms=2000,
            max_error_rate=0.05,
            min_throughput_rps=1.0,
        ),
        pass_thresholds=PassThresholds(
            accuracy_min=0.80,
            format_compliance_min=0.90,
            semantic_correctness_min=0.85,
        ),
        stop_conditions=StopConditions(
            max_consecutive_failures=3,
            max_error_rate=0.20,
            safety_abort_on_timeout=True,
            max_total_failures=5,
        ),
        environment_constraints=EnvironmentConstraints(
            required_os="Darwin",
            required_arch="arm64",
            min_memory_gb=8,
            allow_network=False,
            require_offline=False,
        ),
        authority_boundary=AuthorityBoundary(
            write_permission=False,
            process_permission=False,
            network_permission=False,
            tool_permission=False,
            routing_authority=False,
            acceptance_authority=False,
        ),
        claim_ceiling=claim_ceiling,
        created_at=now_iso,
    )

    print(
        f"Executing experiment {contract.experiment_id} for candidate {contract.candidate.provider_id}..."
    )
    receipt = run_provider_adoption_experiment(
        contract=contract,
        cohort=cohort,
        adapter=adapter,
    )

    bundle = build_evidence_bundle(contract, receipt)
    report = generate_13_question_report(bundle)

    if args.output_json:
        os.makedirs(os.path.dirname(os.path.abspath(args.output_json)), exist_ok=True)
        with open(args.output_json, "w", encoding="utf-8") as f:
            json.dump(bundle.to_dict(), f, indent=2)
        print(f"Wrote bundle JSON to {args.output_json}")

    if args.output_report:
        os.makedirs(os.path.dirname(os.path.abspath(args.output_report)), exist_ok=True)
        with open(args.output_report, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"Wrote report Markdown to {args.output_report}")

    print("\n--- Experiment Summary ---")
    print(f"Final State: {receipt.final_state.value}")
    if receipt.stop_reason:
        print(f"Stop / Blocker Reason: {receipt.stop_reason}")
    print(f"Recommended State: {receipt.recommendation.recommended_state}")
    print(f"Recommended Autonomy: {receipt.recommendation.recommended_autonomy}")
    print(f"Clamped by Ceiling: {receipt.recommendation.clamped_by_ceiling}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
