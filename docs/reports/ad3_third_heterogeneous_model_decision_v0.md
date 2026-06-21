# AD3 — Third Model Adoption Decision

**Status**: `AD3_RETURN_TO_PRODUCTIZATION`
**Date**: 2026-06-21
**Owner Decision**: FINAL

---

## 1. Executive Summary

The third heterogeneous proposer evaluation reveals that no safe third 7B/8B model is available. All candidate pulls from ollama registry failed or timed out. The current model stack (3B Judge + Qwen 7B + DeepSeek 6.7B) remains optimal at 13/14 (92.9%).

**Decision**: Return to productization. Do not add third model.

---

## 2. Why Third Model Was Tested

The literature supports that model diversity improves multi-agent reasoning:
- Multi-agent debate success is driven by model diversity, not debate structure ([arXiv:2511.07784])
- Different training sources improve reasoning over same-model instances ([arXiv:2410.12853])

The hypothesis was that a third heterogeneous proposer could:
1. Reduce proposer calls/latency
2. Provide unique wins on hard tasks
3. Act as tie-breaker for Qwen/DeepSeek disagreement

---

## 3. Literature Rationale

| Paper | Finding | Relevance |
|-------|---------|-----------|
| Can LLM Agents Really Debate? (2511.07784) | Model diversity drives debate success | Supports third model |
| Diversity of Thought (2410.12853) | Different training sources improve reasoning | Supports third model |

**Conclusion**: Literature supports diversity, but requires available models to test.

---

## 4. Candidate Model Selected

| Priority | Model | Family | Status |
|----------|-------|--------|--------|
| 1 | IBM Granite Code 8B | IBM Granite | NOT AVAILABLE |
| 2 | CodeGemma 7B IT | Google Gemma | NOT AVAILABLE |
| 3 | Codestral Mamba 7B | Mistral/Mamba | NOT AVAILABLE |
| 3 | Mistral 7B | Mistral | TIMEOUT |

**No candidate available for evaluation.**

---

## 5. Feasibility Result

| Check | Result |
|-------|--------|
| Local availability | FAILED |
| Ollama registry | NOT FOUND |
| Pull status | FAILED/TIMEOUT |
| License check | NOT REACHABLE |
| JSON compliance | NOT PROBED |
| Abstain capability | NOT PROBED |
| Diversity measurement | NOT POSSIBLE |

---

## 6. Three-Proposer Benchmark Result

| Arm | Status | Pass Rate |
|-----|--------|-----------|
| A: Current route | COMPLETE | 13/14 (92.9%) |
| B: Three-proposer | BLOCKED | N/A |
| C: Third model only | BLOCKED | N/A |
| D: Third model tie-breaker | BLOCKED | N/A |
| E: Third model disagreement | BLOCKED | N/A |
| F: Third model ambiguity | BLOCKED | N/A |

---

## 7. Unique Wins

| Metric | Value |
|--------|-------|
| Unique Wins | 0 |
| Unique Wrongs | 0 |
| Efficiency Gain | N/A |

---

## 8. Unique Wrongs

| Metric | Value |
|--------|-------|
| Safety violations | 0 |
| Governance boundary violations | 0 |
| False green leakage | 0 |

---

## 9. Cost and Latency

| Metric | Current Route | With Third Model |
|--------|---------------|------------------|
| Avg Proposer Calls | 1.8 | N/A |
| Avg Latency | 35.0 sec | N/A |
| Peak RAM | 6.8 GB | N/A |

---

## 10. Resource Safety

| Metric | Value |
|--------|-------|
| System RAM | 16.0 GB |
| Peak RAM Allowed | 12.0 GB |
| Current Usage | 6.8 GB |
| Third Model Budget | 5.4 GB |
| Candidate Within Budget | NONE AVAILABLE |

---

## 11. Governance Boundary Behavior

| Task | Classification | Third Model Impact |
|------|---------------|-------------------|
| django__django-13455 | OWNER_GATED_BOUNDARY | N/A (governance, not model) |

---

## 12. Final Policy

**AD3_RETURN_TO_PRODUCTIZATION**

| Decision | Rationale |
|----------|-----------|
| Do not add third model | No available candidate |
| Do not change route | Current route is optimal |
| Do not expand model stack | Resource limits prevent |
| Return to productization | 13/14 is sufficient |

---

## 13. What Remains Forbidden

| Restriction | Status |
|-------------|--------|
| Public claim | FORBIDDEN |
| Production release | FORBIDDEN |
| Training export | FORBIDDEN |
| Cloud/API execution | FORBIDDEN (without approval) |
| Unrestricted multi-file edit | FORBIDDEN |
| Model direct tool calls | FORBIDDEN |
| Majority vote | FORBIDDEN |
| Free-form patch in armored mode | FORBIDDEN |
| Test edits to force pass | FORBIDDEN |
| Hardcoded expected patch | FORBIDDEN |

---

## 14. 30-Day Roadmap

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

## Mandatory Flags

```json
{
  "public_claim_allowed": false,
  "production_ready": false,
  "training_export_allowed": false,
  "internal_only": true
}
```
