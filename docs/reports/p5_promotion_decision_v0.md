# P5 Promotion Decision

## Decision: B — Keep env-guarded only (P5_ENV_GUARDED_ONLY)

## Rationale

P5 diversity selector is functional and all tests pass (132/132), but promotion to shadow-default is premature:

1. **E1 effect pack passes** — counterfactual tests prove P5 beats first-valid in controlled scenarios. However, the effect pack uses synthetic candidates, not real execution data.

2. **E2 historical replay passes** — 10+ cases with 100% trace/fuzzy coverage. But `selection_changed_rate` needs examination (not computed in final report). The historical replay uses synthetic candidates derived from reports, not actual model outputs.

3. **E3 real shadow passes** — 6 realistic candidate sets with 100% metadata/trace/fuzzy coverage. Shadow-only (no apply/verifier). No metadata bugs detected.

4. **E4 failure mode audit passes** — All 8 modes assessed and detectable. FM2 (prefers wrong unique) and FM5 (target_file_match imprecise) are medium risk but explainable.

**Key concern**: P5's `selection_changed_rate` on real execution data is unknown. The effect pack and historical replay use synthetic candidates. Until P5 demonstrates meaningful delta on actual model outputs in production-like conditions, keeping it env-guarded is safer.

**Decision**: Keep `NEXUS_ENABLE_P5_DIVERSITY_SELECTION` as opt-in env guard. Do not make P5 the default selection strategy.

## Conditions Met

- [x] E1 all pass (counterfactual off/on proof)
- [x] E2 historical replay no crash
- [x] E3 real shadow no metadata bug
- [x] E4 failure modes observable and explainable
- [ ] E2 selection_changed_rate = 0 → B (no real-world delta yet) — needs verification
- [x] E3 shows no selection drift or fail_closed sensitivity issues
- [x] E4 shows no unrecoverable anti-pattern

## Conditions Not Met

- Real execution data delta unknown (synthetic candidates only)
- Production solve-rate impact unproven

## Next Action

1. Keep P5 env-guarded (`NEXUS_ENABLE_P5_DIVERSITY_SELECTION=1` to enable)
2. Deploy to staging with P5 enabled
3. Collect real execution data for 1-2 weeks
4. Re-evaluate promotion after real-world delta is measured
