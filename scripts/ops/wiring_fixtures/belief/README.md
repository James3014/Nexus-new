Belief wiring fixture: the audit seeds `.nexus/belief_state.json` through the real
`BeliefEngine.process_audit_outcome` with a failed `AuditOutcome`, then checks that the
registry path reads the lowered confidence.
