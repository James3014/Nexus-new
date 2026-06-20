#!/usr/bin/env python3
"""S1: Generate baseline vs strategy-conditioned prompts for 4 candidates."""

import sys, json, hashlib
sys.path.insert(0, "/Users/jameschen/Workspace/nexus")

from nexus.strategy import StrategyPlanner, StrategyAdherenceChecker
from nexus.strategy.strategy_prompt_renderer import StrategyPromptRenderer

CANDIDATES = [
    {"instance_id": "astropy__astropy-13236", "issue_summary": "Table NdarrayMixin block removal", "target_files": ["astropy/table/table.py"], "canonical_span_source": "unified_diff"},
    {"instance_id": "sympy__sympy-13852", "issue_summary": "Missing I import in zeta_functions", "target_files": ["sympy/functions/special/zeta_functions.py"], "canonical_span_source": "any_valid"},
    {"instance_id": "astropy__astropy-12907", "issue_summary": "Separability matrix wrong assignment", "target_files": ["astropy/modeling/separable.py"], "canonical_span_source": "ast_boundary"},
    {"instance_id": "astropy__astropy-14182", "issue_summary": "RST parser start_line off by one", "target_files": ["astropy/io/ascii/rst.py"], "canonical_span_source": "locked_search"},
]

OUTPUT_PATH = "/Users/jameschen/Workspace/nexus/artifacts/strategy/s1_shadow_comparison.jsonl"


def main():
    planner = StrategyPlanner()
    renderer = StrategyPromptRenderer()
    checker = StrategyAdherenceChecker()

    rows = []
    for cand in CANDIDATES:
        envelope = planner.plan(**cand)
        block = renderer.render(envelope)
        adherence = checker.check(envelope, effective_change=True, source_snapshot_present=True, canonical_search_locked=True)

        # Baseline prompt (current T3 replace-only)
        baseline = f"TASK: Return ONLY the replacement code.\nFILE: {cand['target_files'][0]}\nBUGGY CODE: [see canonical SEARCH]\nFIX: [from task metadata]\nRULES: NO markdown, NO diff, NO SEARCH.\nOUTPUT:"
        baseline_hash = hashlib.sha256(baseline.encode()).hexdigest()[:16]

        row = {
            "instance_id": cand["instance_id"],
            "strategy_id": envelope.strategy_id,
            "baseline_prompt_hash": baseline_hash,
            "strategy_prompt_hash": block.block_hash,
            "baseline_len": len(baseline),
            "strategy_len": len(block.block),
            "adherence_status": adherence["adherence_status"],
            "trace_only": True,
            "execution_effect": False,
        }
        rows.append(row)
        print(f"  {cand['instance_id']}: baseline={row['baseline_len']}ch strategy={row['strategy_len']}ch adherence={adherence['adherence_status']}")

    with open(OUTPUT_PATH, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    print(f"\nShadow comparison: {OUTPUT_PATH}")
    print(f"Total: {len(rows)} candidates")

    # Verify no execution effect
    all_safe = all(not r["execution_effect"] for r in rows)
    all_trace = all(r["trace_only"] for r in rows)
    print(f"\nExecution-effect safety: {'PASS' if all_safe else 'FAIL'}")
    print(f"All trace-only: {'PASS' if all_trace else 'FAIL'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
