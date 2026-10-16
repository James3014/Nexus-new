# P5 Promotion Decision v2

## Decision: B — Keep env-guarded only (P5_ENV_GUARDED_ONLY)

## Rationale

P5 diversity selector is functional (137/137 tests pass), all EA-R0–R8 infrastructure is in place, but promotion to shadow-default remains premature.

**Key findings from EA-R0–R8:**

1. **R0 (Memory Stack Map)**: 14 existing memory capabilities inventoried. P5/P6 must consume existing substrate, not build parallel stack.

2. **R1 (Effect Ledger)**: Ledger created as evaluation artifact. Claim_level defaults to "controlled" — no verified cases yet.

3. **R2 (Memory Bridge)**: Bridge payload created. `eligible_for_findings_memory=False` for all controlled/shadow cases.

4. **R3 (Memory Context)**: Memory context adapter wraps existing MemoryRetrievalAdapter. `decision_mode="audit_only"` by default.

5. **R4 (Copyability Telemetry)**: Copyability scoring added to shadow_memory_ranking. Telemetry-only, no behavior change.

6. **R5 (Memory Decision Gate)**: Gate blocks low-copyability and unverified memory. Allowed memory does NOT override P4 gate.

7. **R6 (Belief Signal)**: Read-only signal. `used_for_selection=False` always. No runtime impact.

8. **R7 (Branch Replay)**: Memory-on CANNOT change selection in audit_only mode. Verified.

9. **R8 (P6 Simulator)**: Memory cannot override quota_exhausted. Memory only affects diagnostic_confidence.

**Decision factors:**

- **Real execution data**: Insufficient. Effect pack and replay use synthetic candidates.
- **Memory audit path**: All memory is audit-only (`decision_eligible_memory_count = 0`). No memory affects selection.
- **Selection changed rate**: Unknown on real execution data.
- **Failure modes**: Observable and explainable (E4).
- **Copyability telemetry**: Collected but no verified cases.
- **Memory influence**: Not allowed until copyability >= 0.80 AND verified outcome.

## Conditions Met

- [x] E1 all pass (counterfactual off/on proof)
- [x] E2 historical replay no crash
- [x] E3 real shadow no metadata bug
- [x] E4 failure modes observable and explainable
- [x] EA-R0–R8 infrastructure in place
- [x] Memory audit-only mode verified (no selection impact)
- [x] Copyability telemetry collected

## Conditions Not Met

- [ ] Real execution data delta unknown (synthetic candidates only)
- [ ] `decision_eligible_memory_count = 0` (all memory audit-only)
- [ ] `selection_changed_rate` on real execution data unknown
- [ ] No verified apply/verifier/claim cases for memory influence

## Next Action

1. Keep P5 env-guarded (`NEXUS_ENABLE_P5_DIVERSITY_SELECTION=1` to enable)
2. Deploy to staging with P5 enabled
3. Collect real execution data for 1-2 weeks
4. Monitor copyability scores on real cases
5. When `decision_eligible_memory_count > 0` AND real execution data shows meaningful delta → re-evaluate promotion
