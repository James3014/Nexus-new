# V4-F.0 Internal Dogfood Repair Run Design

## Status: V4F0_DOGFOOD_RUN_DESIGN_READY

## Design

3-5 internal Nexus tasks for controlled dogfood run.

### Roles
- 7B: default executor
- 14B: manual strict-prompt fallback only
- 3B: optional advisory receipt/lane audit only
- Deterministic checker: final compliance authority
- Owner: final acceptance authority

### Task Selection Criteria
- Source checkout available
- Bounded verifier
- Task-scoped context available
- No credentials required
- No network-dependent tests
- Must pass compliance checker

### Workflow
1. Task intake → eligibility check
2. Source checkout verification
3. Env taxonomy classification
4. Baseline reproduction
5. 7B model execution
6. Patch authority validation
7. Task-scoped verification
8. S2T export classification
9. 3B advisory receipt audit (optional)
10. Compliance checker validation
11. Owner acceptance

### Stop Rules
- All Roadmap v3 / V4-A / V4-B / V4-D.2 stop rules apply
- Compliance checker must pass before acceptance
- Owner must approve before any claim
