# M0 Nondeterminism Policy — S4.8

**Date**: 2026-06-18

---

## 1. Purpose

Local Qwen14B model generation is nondeterministic. This policy defines how Nexus handles fresh M0 replay failures vs stored-output (R0) consolidation.

## 2. Definitions

- **R0 (Stored-Output Replay)**: Apply previously captured model output to clean source. Does not count as fresh model success.
- **M0 (Fresh Model Replay)**: Rerun Qwen14B with same prompt. Counts as fresh model success only if reproducible.
- **M0不稳定 (M0 Unstable)**: M0 succeeded once but failed to reproduce. Not a stable verified candidate.

## 3. Rules

### R0 Consolidation
- R0 replay validates historical replayability
- R0 does NOT count as fresh model_patch_reward=1.0
- R0 is useful for fixture validation
- R0 success → mark as `stored_output_replayable`

### M0 Fresh Success
- M0 fresh success requires model_calls>0 with captured output
- M0 fresh success must be reproducible (≥2/3 runs)
- If M0 fails to reproduce: mark as `m0_unstable`
- M0 unstable is NOT model failure — it's nondeterminism

### M0 Reproducibility Requirement
For M0 to count as stable fresh success:
- Run ≥3 times with same prompt
- ≥2/3 runs must produce model_patch_reward=1.0
- Record: temperature, seed, model digest, sampling params
- If <2/3 reproducible: mark as `m0_nondeterministic`

## 4. Candidate Status Classification

| Status | Meaning | Fresh Success |
|--------|---------|---------------|
| fixture_backed_verified | R0 + M0 both pass | YES |
| stored_output_replayable | R0 pass, M0 unstable | NO (historical only) |
| m0_unstable | M0 passed once, failed to reproduce | NO |
| m0_nondeterministic | M0 <2/3 reproducible | NO |
| fresh_m0_verified | M0 ≥2/3 reproducible | YES |

## 5. S4.6 Classification

- astropy__astropy-13579: `stored_output_replayable` (R0 pass, M0 unstable)
- sympy__sympy-13031: `stored_output_replayable` (R0 pass, M0 unstable)

## 6. Future M0 Reproducibility

To improve M0 reproducibility:
- Fix temperature=0
- Fix seed (if model supports)
- Record model digest (ollama show)
- Record sampling params
- Use same prompt hash
