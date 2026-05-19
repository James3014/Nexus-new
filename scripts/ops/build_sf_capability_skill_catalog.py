#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from nexus.learning.skill_fit_closure import (
    build_capability_local_test_matrix,
    build_final_capability_skill_catalog,
    build_sf_paired_delta_report,
    build_sf_evidence_gate_schema,
    read_json,
    run_sf_bounded_probe,
    write_json,
)


DEFAULT_FINAL_PAIRING = Path("docs/reports/NEXUS_SF_FINAL_PAIRING_V2_2026-05-18.json")
DEFAULT_BUCKETS = Path("docs/reports/NEXUS_SF_CANONICAL_CAPABILITY_BUCKETS_2026-05-18.json")
DEFAULT_MATRIX = Path("docs/reports/NEXUS_SF_CAPABILITY_LOCAL_TEST_MATRIX_2026-05-18.json")
DEFAULT_GATE = Path("docs/reports/NEXUS_SF_EVIDENCE_GATE_SCHEMA_2026-05-18.json")
DEFAULT_PROBE = Path("docs/reports/NEXUS_SF_BOUNDED_PROBE_RESULT_2026-05-18.json")
DEFAULT_CATALOG = Path("docs/reports/NEXUS_SF_FINAL_CAPABILITY_SKILL_CATALOG_V2_2026-05-18.json")
DEFAULT_DELTA = Path("docs/reports/NEXUS_SF_PAIRED_DELTA_REPORT_2026-05-18.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build SF capability-local matrix and final skill catalog.")
    parser.add_argument("--final-pairing", default=str(DEFAULT_FINAL_PAIRING))
    parser.add_argument("--buckets", default=str(DEFAULT_BUCKETS))
    parser.add_argument("--matrix-output", default=str(DEFAULT_MATRIX))
    parser.add_argument("--evidence-gate-output", default=str(DEFAULT_GATE))
    parser.add_argument("--bounded-probe-output", default=str(DEFAULT_PROBE))
    parser.add_argument("--catalog-output", default=str(DEFAULT_CATALOG))
    parser.add_argument("--paired-delta-output", default=str(DEFAULT_DELTA))
    parser.add_argument("--max-alternates-per-capability", type=int, default=3)
    args = parser.parse_args(argv)

    final_pairing = read_json(args.final_pairing)
    buckets = read_json(args.buckets)
    matrix = build_capability_local_test_matrix(
        final_pairing=final_pairing,
        capability_buckets=buckets,
        max_alternates_per_capability=args.max_alternates_per_capability,
    )
    evidence_gate = build_sf_evidence_gate_schema()
    bounded_probe = run_sf_bounded_probe(matrix)
    catalog = build_final_capability_skill_catalog(
        bounded_probe=bounded_probe,
        evidence_gate=evidence_gate,
    )
    delta = build_sf_paired_delta_report(
        matrix=matrix,
        bounded_probe=bounded_probe,
        catalog=catalog,
    )

    write_json(args.matrix_output, matrix)
    write_json(args.evidence_gate_output, evidence_gate)
    write_json(args.bounded_probe_output, bounded_probe)
    write_json(args.catalog_output, catalog)
    write_json(args.paired_delta_output, delta)

    print(
        json.dumps(
            {
                "status": "PASS" if catalog["status"] == "PASS" else "PARTIAL",
                "matrix_status": matrix["status"],
                "bounded_probe_status": bounded_probe["status"],
                "catalog_status": catalog["status"],
                "paired_delta_status": delta["status"],
                "capability_count": catalog["summary"]["capability_count"],
                "capability_with_primary_count": catalog["summary"]["capability_with_primary_count"],
                "flash_compare_required_count": catalog["summary"]["flash_compare_required_count"],
                "bounded_positive_delta_count": delta["summary"]["bounded_positive_delta_count"],
                "live_delta_measured_count": delta["summary"]["live_delta_measured_count"],
                "public_benchmark_allowed": False,
            },
            ensure_ascii=False,
        )
    )
    return 0 if catalog["status"] in {"PASS", "PARTIAL"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
