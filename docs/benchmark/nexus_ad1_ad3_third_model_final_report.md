# Nexus AD1-AD3 Third Heterogeneous Proposer Evaluation — Final Report

**Date**: 2026-06-21
**Status**: COMPLETE
**Decision**: AD3_RETURN_TO_PRODUCTIZATION

---

## Executive Summary

The third heterogeneous proposer evaluation reveals that no safe third 7B/8B model is available. All candidate pulls from ollama registry failed or timed out. The current model stack (3B Judge + Qwen 7B + DeepSeek 6.7B) remains optimal at 13/14 (92.9%).

**Decision**: Return to productization. Do not add third model.

---

## AD1: Third Model Feasibility

**Status**: `AD1_NO_SAFE_THIRD_MODEL_AVAILABLE`

### Candidate Models

| Model | Family | Priority | Availability | Pull Status |
|-------|--------|----------|--------------|-------------|
| IBM Granite Code 8B | IBM Granite | 1 | NOT AVAILABLE | FAILED |
| CodeGemma 7B IT | Google Gemma | 2 | NOT AVAILABLE | FAILED |
| Codestral Mamba 7B | Mistral/Mamba | 3 | NOT AVAILABLE | FAILED |
| Mistral 7B | Mistral | 3 | NOT AVAILABLE | TIMEOUT |

### Resource Guard

| Metric | Value |
|--------|-------|
| System RAM | 16.0 GB |
| Peak RAM Allowed | 12.0 GB |
| Current Usage | 6.8 GB |
| Third Model Budget | 5.4 GB |
| Candidate Within Budget | NONE AVAILABLE |

### Conclusion

No third heterogeneous 7B/8B model is available. All candidate pulls failed or timed out.

---

## AD2: Three-Proposer Shadow Benchmark

**Status**: `AD2_THIRD_PROPOSER_NO_MATERIAL_GAIN`

### Arms

| Arm | Status | Pass Rate |
|-----|--------|-----------|
| A: Current route | COMPLETE | 13/14 (92.9%) |
| B: Three-proposer | BLOCKED | N/A |
| C: Third model only | BLOCKED | N/A |
| D: Third model tie-breaker | BLOCKED | N/A |
| E: Third model disagreement | BLOCKED | N/A |
| F: Third model ambiguity | BLOCKED | N/A |

### Unique Wins

| Metric | Value |
|--------|-------|
| Unique Wins | 0 |
| Unique Wrongs | 0 |
| Efficiency Gain | N/A |

### Conclusion

Benchmark cannot proceed without available third model.

---

## AD3: Third Model Adoption Decision

**Status**: `AD3_RETURN_TO_PRODUCTIZATION`

### Decision

| Action | Rationale |
|--------|-----------|
| Do not add third model | No available candidate |
| Do not change route | Current route is optimal |
| Do not expand model stack | Resource limits prevent |
| Return to productization | 13/14 is sufficient |

### Literature Support

| Paper | Finding | Relevance |
|-------|---------|-----------|
| Can LLM Agents Really Debate? (2511.07784) | Model diversity drives debate success | Supports diversity |
| Diversity of Thought (2410.12853) | Different training sources improve reasoning | Supports diversity |

**Note**: Literature supports diversity, but requires available models to test.

---

## Current Route Performance

| Metric | Value |
|--------|-------|
| Pass Rate | 13/14 (92.9%) |
| Avg Proposer Calls | 1.8 |
| Avg Latency | 35.0 sec |
| Peak RAM | 6.8 GB |
| Timeout Rate | 0% |

---

## What Remains Forbidden

- Public claim: **FORBIDDEN**
- Production release: **FORBIDDEN**
- Training export: **FORBIDDEN**
- Cloud/API execution: **FORBIDDEN** (without approval)
- Unrestricted multi-file edit: **FORBIDDEN**
- Model direct tool calls: **FORBIDDEN**
- Majority vote: **FORBIDDEN**
- Free-form patch in armored mode: **FORBIDDEN**
- Test edits to force pass: **FORBIDDEN**
- Hardcoded expected patch: **FORBIDDEN**

---

## 30-Day Roadmap

### Week 1-2: Productization Design
- Design internal API surface
- Define deployment topology
- Create user documentation
- Establish monitoring baseline

### Week 3-4: Internal Deployment
- Deploy to internal staging
- Run 7-day canary
- Collect user feedback
- Iterate on UX

### Out of Scope
- Third model addition (deferred)
- Public release
- Marketing claims
- Training data export

---

## Artifacts

| Path | Description |
|------|-------------|
| `artifacts/runtime/ad1_third_model_feasibility_v0/` | AD1 feasibility analysis |
| `artifacts/runtime/ad2_three_proposer_shadow_benchmark_v0/` | AD2 benchmark (blocked) |
| `docs/reports/ad1_third_model_feasibility_v0.md` | AD1 report |
| `docs/reports/ad2_three_proposer_shadow_benchmark_v0.md` | AD2 report |
| `docs/reports/ad3_third_heterogeneous_model_decision_v0.md` | AD3 decision |

---

## Mandatory Flags

```json
{
  "public_claim_allowed": false,
  "production_ready": false,
  "training_export_allowed": false,
  "internal_only": true
}
```
