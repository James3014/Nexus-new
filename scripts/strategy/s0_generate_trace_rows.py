#!/usr/bin/env python3
"""S0: Generate trace-only sample rows for T4.10 final candidates."""

import sys, json
sys.path.insert(0, "/Users/jameschen/Workspace/nexus")

from nexus.strategy import StrategyPlanner, StrategyAdherenceChecker, AbortConditionEvaluator

CANDIDATES = [
    {"instance_id": "astropy__astropy-13236", "issue_summary": "Table NdarrayMixin block removal", "target_files": ["astropy/table/table.py"], "canonical_span_source": "unified_diff"},
    {"instance_id": "sympy__sympy-13852", "issue_summary": "Missing I import in zeta_functions", "target_files": ["sympy/functions/special/zeta_functions.py"], "canonical_span_source": "any_valid"},
    {"instance_id": "astropy__astropy-12907", "issue_summary": "Separability matrix wrong assignment", "target_files": ["astropy/modeling/separable.py"], "canonical_span_source": "ast_boundary"},
    {"instance_id": "astropy__astropy-14182", "issue_summary": "RST parser start_line off by one", "target_files": ["astropy/io/ascii/rst.py"], "canonical_span_source": "locked_search"},
]

OUTPUT_PATH = "/Users/jameschen/Workspace/nexus/artifacts/strategy/s0_strategy_trace_sample_rows.jsonl"


def main():
    planner = StrategyPlanner()
    checker = StrategyAdherenceChecker()
    evaluator = AbortConditionEvaluator()

    rows = []
    for cand in CANDIDATES:
        envelope = planner.plan(**cand)

        adherence = checker.check(envelope, effective_change=True, source_snapshot_present=True, canonical_search_locked=True)
        abort = evaluator.evaluate(envelope, target_file_exists=True, canonical_search_locked=True, source_snapshot_present=True, effective_change=True, verification_available=True, public_claim_boundary_present=True)

        row = {
            "instance_id": cand["instance_id"],
            "strategy_id": envelope.strategy_id,
            "adherence_status": adherence["adherence_status"],
            "abort_condition_triggered": abort["abort_condition_triggered"],
            "execution_effect": envelope.has_execution_effect(),
            "trace_only": envelope.trace_only,
            "public_claim_allowed": envelope.public_claim_allowed,
        }
        rows.append(row)
        print(f"  {cand['instance_id']}: strategy_id={envelope.strategy_id} adherence={adherence['adherence_status']} abort={abort['would_abort']}")

    with open(OUTPUT_PATH, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    print(f"\nSample rows: {OUTPUT_PATH}")
    print(f"Total: {len(rows)} candidates processed")

    # Verify no execution effect
    all_safe = all(not r["execution_effect"] for r in rows)
    all_no_claim = all(not r["public_claim_allowed"] for r in rows)
    all_trace = all(r["trace_only"] for r in rows)

    print(f"\nExecution-effect safety: {'PASS' if all_safe else 'FAIL'}")
    print(f"No public claim: {'PASS' if all_no_claim else 'FAIL'}")
    print(f"All trace-only: {'PASS' if all_trace else 'FAIL'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
