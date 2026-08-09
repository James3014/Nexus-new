---
artifact_authority: current
owner: James Chen
status: active
purpose: Conditional workforce eligibility and admission overlay.
---

# Workforce Execution Overlay

This L2 overlay is loaded to evaluate workforce eligibility and admission
after route and capability selection, including delegation, onboarding,
calibration, promotion, demotion, or admission review.

## Admission first

For normal model work, query the machine Workforce Admission surface and consume
its compact receipt before loading policy prose or the full YAML roster. The
receipt must expose `ALLOW`, `BLOCK`, or `ESCALATE`, `worker_id`, provider,
model identity, autonomy level, context/scope, policy hash, and reasons.

Load `docs/arch/MODEL_WORKFORCE_POLICY.md` and
`nexus/config/model_workforce.yaml` fully only when changing provider/model
policy, onboarding or calibration, promotion/demotion, auditing admission, or
resolving an authority dispute. Fresh runtime discovery and signed receipts
override stale cached lists.

## Boundaries

- `CapabilityPlanner` is the sole route and capability-selection authority.
  `HybridRouteDecision` is a Planner-derived decision contract/projection, not
  a second selector, router, or planner. This overlay does not select a route,
  capability, topology, or create a router.
- Registered providers may be eligible for admission only with explicit model
  identity, adapter preflight, parser, verifier, and receipt gates. Unknown
  providers or models fail closed.
- Local output and delegated output are candidates. They cannot independently
  establish correctness, promotion, production readiness, public claims,
  merge/integration authority, push authority, or cleanup authority.
- Workforce admission only constrains worker eligibility; it does not select a
  route or capability, or authorize a worker to approve its own work.
