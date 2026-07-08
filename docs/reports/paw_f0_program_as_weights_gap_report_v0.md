# PAW-F0: Program-as-Weights Gap Report

## Status: PAW_F0_GAP_REPORT_COMPLETE

## Paper: arXiv:2607.02512 Program-as-Weights

PAW compiles natural-language fuzzy function specs into local neural artifacts:
- 4B compiler model trained on FuzzyBench 10M examples
- Produces parameter-efficient adapters for frozen lightweight interpreter
- 0.6B Qwen3 interpreter executes PAW programs
- Approaches Qwen3-32B direct prompt performance
- ~1/50 memory, 30 tokens/s on MacBook M3

## PAW Core Components vs Nexus Current State

| PAW Component | PAW Implementation | Nexus Current | Gap |
|---------------|-------------------|---------------|-----|
| Fuzzy function specification | NL spec → compiler input | Deterministic functions | ⚠️ Partial |
| Compiler model | 4B trained on FuzzyBench | Not implemented | ❌ Missing |
| Reusable neural artifact | Parameter-efficient adapters | Not implemented | ❌ Missing |
| Frozen lightweight interpreter | 0.6B Qwen3 | Not implemented | ❌ Missing |
| Local/offline execution | 30 tokens/s on M3 | Deterministic only | ⚠️ Partial |
| Calibration dataset | FuzzyBench 10M examples | fuzzy_reward_calibration_v0.json (25 cases) | ⚠️ Partial |
| Deterministic fallback | Always available | Always available | ✅ Implemented |

## Nexus Fuzzy Function Mapping

| Function | Deterministic | Calibration | PAW-compatible | True PAW |
|----------|---------------|-------------|----------------|----------|
| candidate_quality_v1 | ✅ | ✅ | ✅ | ❌ |
| duplicate_similarity_v1 | ✅ | ✅ | ✅ | ❌ |
| popularity_trap_risk_v1 | ✅ | ✅ | ✅ | ❌ |
| memory_usefulness_v1 | ✅ | ✅ (placeholder) | ✅ | ❌ |
| quota_degradation_risk_v1 | ✅ | ✅ | ✅ | ❌ |

## What Nexus Has (PAW-compatible surface)

1. **Deterministic fuzzy functions** — hand-written scoring rules
2. **Calibration fixtures** — 25 test cases in `fuzzy_reward_calibration_v0.json`
3. **FuzzyFunctionSpec registry** — versioned, typed, deterministic backend
4. **Runtime consumption** — P5 selector calls `fuzzy_evaluate()`
5. **Receipt versioning** — `fuzzy_calibration_version` in shadow receipt

## What Nexus Lacks (true PAW)

1. **Natural-language fuzzy function spec** — currently hardcoded rules, not NL-readable
2. **Compiler model** — no 4B or similar compiler to produce adapters
3. **Reusable neural artifact** — no parameter-efficient adapters
4. **Frozen lightweight interpreter** — no local neural execution
5. **FuzzyBench calibration dataset** — only 25 cases, not 10M
6. **Performance benchmarking** — no token/s or memory comparison

## Risk Assessment

| Risk | Level | Mitigation |
|------|-------|------------|
| Deterministic functions may not capture complex NL semantics | Medium | Accept for now; PAW-F1 registry documents limitations |
| Missing calibration dataset | Low | 25 cases sufficient for deterministic validation |
| No neural compiler | High (for PAW goal) | Deferred to PAW-F2/F3 |
| Runtime dependency on deterministic | Low | Deterministic is safe fallback |

## Recommendation for PAW-F1

Create fuzzy function spec registry with:
- NL spec for each function
- Input/output schemas
- Deterministic backend (current)
- PAW backend placeholder (future)
- Safety scope
- Receipt fields

This provides the interface contract for future PAW compiler integration without requiring the compiler itself.
