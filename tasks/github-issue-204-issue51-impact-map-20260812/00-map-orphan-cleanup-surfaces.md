# Task Card: Issue 204 Map Issue-51 Orphan Cleanup Surfaces

## Objective

Repair exact-base test-impact routing for the four production paths that make
PR #71 fail closed as `IMPACT_UNKNOWN`, without broadening cleanup or product authority.

## Authority

- Owner request: finish Issue #51 prerequisites, then complete #51.
- Issue: `#204`
- Exact baseline: `bdcc427f6249406079c85f9725b3af6cd62ab1f1`
- AUTO_CHAIN: `false`

## Allowed files

- `docs/testing/test_impact_map.md`
- `tests/ops/test_issue51_cleanup_impact_map.py`
- this Task Card and INDEX

## Required mapping

Exact-file rules only:
- `nexus/committee/diversity_sampler.py` -> live committee tests plus architecture safety checks;
- `nexus/env/diff_report.py` -> architecture safety checks;
- `nexus/env/snapshot.py` -> architecture safety checks;
- `nexus/policy/compatibility.py` -> policy and architecture safety checks.

All four rules are high risk, so the selector's existing high-risk escalation
continues to add the canonical policy-gate target.

## Acceptance

- every exact path has `unmatched_paths=[]` and `fallback_used=false`;
- combined selection for all four exact paths remains explicit and high risk;
- unrelated unknown `nexus/*` path still uses fail-closed fallback;
- no broad `nexus/committee`, `nexus/env`, or `nexus/policy` prefix is introduced;
- exact-head CI and trusted verifier pass;
- independent exact-head acceptance finds no false-green broadening.

## Forbidden

No PR #71 deletion mutation, selector algorithm change, runtime/API change,
ruleset/bypass change, merge/approval authority, Workforce/lifecycle/route change,
or release/production claim.

Maximum pre-merge claim: `ISSUE_51_IMPACT_MAP_PREREQUISITE_CANDIDATE`.
