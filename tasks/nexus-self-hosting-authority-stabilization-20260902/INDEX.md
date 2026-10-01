# Nexus Self-Hosting Authority Stabilization

- campaign_id: `nexus-self-hosting-authority-stabilization-20260902`
- owner: James Chen
- status: COMPLETE
- AUTO_CHAIN: false
- source_decision: Owner explicitly approved the transitional authority policy in the 2026-09-02 controller conversation after G10 completion.
- frontier: none

## Mission

Persist the post-G10 transitional authority policy while Nexus remains in self-hosting stabilization. Do not treat G10 success as an automatic cutover to NEXUS_GOVERNED-by-default. Preserve bounded direct development/bootstrap/recovery authority during stabilization, prohibit silent downgrade of an already-governed attempt, and define an explicit Owner-gated readiness milestone before any future default-authority switch.

## Completion

COMPLETE. `TASK-001.md` was implemented through policy PR #706, required protected-main checks passed on exact Candidate `eed4af89084a7d0cfe8f3320f26f7481550ee948`, and the accepted policy merged to `main` as `a770e60ac11ef950aba4042cc1631906e36f5576` without runtime or executable-code changes. Any future transition to governed-by-default work requires the separate Owner-only `NEXUS_GOVERNANCE_DEFAULT_READY` decision and a new policy change.
