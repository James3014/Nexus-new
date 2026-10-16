# V4-E.0 3B Auxiliary Feasibility Planning

## Status: 3B_AUXILIARY_FEASIBILITY_PLAN_READY

## Allowed 3B Roles
- Lane prediction (advisory only)
- Env blocker classification (advisory only)
- Receipt consistency audit (advisory only)
- Patch risk scoring (advisory only)
- Verifier risk prediction (advisory only)
- Source-anchor risk prediction (advisory only)
- Model escalation recommendation (advisory only)

## Forbidden 3B Roles
- Patch generation
- Repair execution
- Verifier execution
- Public claim generation
- Training export
- Runtime/routing enablement

## Safety Boundaries
- 3B is advisory only — never overrides deterministic checker
- 3B cannot mark public_claim_allowed=true
- 3B cannot mark training_eligible=true
- 3B cannot claim repair success
- 3B output is informational, not actionable without owner review
