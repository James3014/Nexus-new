---
artifact_authority: current
owner: James Chen
status: active
purpose: Conditional workforce admission and model-selection overlay.
---

# Workforce Execution Overlay

This L2 overlay is loaded for model/provider selection, delegation, routing,
onboarding, calibration, promotion, demotion, or admission review.

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

- `CapabilityPlanner` and `HybridRouteDecision` remain the only route
  authorities; this overlay does not select topology or create a router.
- Registered providers may be selectable only with explicit model identity,
  adapter preflight, parser, verifier, and receipt gates. Unknown providers or
  models fail closed.
- Local output and delegated output are candidates. They cannot independently
  establish correctness, promotion, production readiness, public claims,
  merge/integration authority, push authority, or cleanup authority.
- Workforce policy constrains eligible workers and escalation; it does not
  authorize a worker to approve its own work.
