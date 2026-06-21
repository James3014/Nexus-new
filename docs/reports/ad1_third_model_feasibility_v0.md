# AD1 — Third Model Feasibility and Diversity Audit

**Status**: `AD1_NO_SAFE_THIRD_MODEL_AVAILABLE`
**Date**: 2026-06-21
**Owner Decision**: Pending

---

## Executive Summary

No safe third heterogeneous 7B/8B model is available for evaluation. All candidate model pulls from ollama registry failed or timed out. The resource guard correctly blocks models that would exceed RAM budget.

---

## Candidate Model Matrix

| Model | Family | Priority | Availability | Pull Status | Diversity |
|-------|--------|----------|--------------|-------------|-----------|
| IBM Granite Code 8B | IBM Granite | 1 | NOT AVAILABLE | FAILED | HIGH |
| CodeGemma 7B IT | Google Gemma | 2 | NOT AVAILABLE | FAILED | HIGH |
| Codestral Mamba 7B | Mistral/Mamba | 3 | NOT AVAILABLE | FAILED | HIGHEST |
| Mistral 7B | Mistral | 3 | NOT AVAILABLE | TIMEOUT | HIGH |

---

## Availability Report

### Currently Available Models

| Model | Size | Family | Eligible |
|-------|------|--------|----------|
| qwen2.5-coder:7b | 4.7 GB | Qwen | NO (primary proposer) |
| qwen2.5:3b | 1.9 GB | Qwen | NO (judge) |
| deepseek-r1-14b-q4km | 9.0 GB | DeepSeek | NO (secondary proposer) |
| qwen2.5-coder:14b-instruct-q3_K_M | 7.3 GB | Qwen | NO (same family) |
| gemma4-coder-12b-q4km | 7.4 GB | Google Gemma | NO (too large) |

### Candidate Pull Attempts

| Model | Status | Error |
|-------|--------|-------|
| granite3.1-code:8b-instruct-q4_K_M | FAILED | file does not exist |
| codegemma:7b-it | FAILED | file does not exist |
| codestral:7b | FAILED | file does not exist |
| mistral:7b | TIMEOUT | Network timeout (4.4GB) |
| mistral:7b-instruct-v0.3 | FAILED | file does not exist |
| phi3:mini | TIMEOUT | Network timeout |
| phi3:3.8b | TIMEOUT | Network timeout |
| starcoder2:3b | TIMEOUT | Network timeout |

---

## Resource Guard

| Metric | Value |
|--------|-------|
| System RAM | 16.0 GB |
| Peak RAM Allowed | 12.0 GB |
| Current RAM in Use | 6.6 GB |
| RAM Headroom | 5.4 GB |
| Third Model Budget | 5.4 GB |

### Candidates Within Budget

| Model | Estimated RAM | Fits | Available |
|-------|---------------|------|-----------|
| Mistral 7B | 6.0 GB | NO | NO |
| Phi3 Mini 3.8B | 4.5 GB | YES | NO |
| StarCoder2 3B | 3.5 GB | YES | NO |

---

## JSON Compliance Probe

**Status**: NOT EXECUTED

No third model available for probing. Planned probes:
1. Constrained JSON output
2. Abstain capability
3. Evidence citation
4. Single-anchor repair
5. No-prose contract

---

## Diversity Probe

**Status**: NOT EXECUTED

No third model available for diversity comparison. Measurable dimensions:
1. Training data diversity
2. Architecture diversity
3. Reasoning style diversity
4. Error pattern diversity

---

## Conclusion

**AD1_NO_SAFE_THIRD_MODEL_AVAILABLE**

No third heterogeneous 7B/8B model is available. All candidate pulls from ollama registry failed or timed out. The resource guard correctly identifies that available models either exceed RAM budget or are the same family as current proposers.

---

## Recommendation

Proceed to AD2 with current model stack only. The third model evaluation cannot proceed without an available candidate.

---

## Artifacts

- `candidate_model_matrix.json`
- `availability_report.json`
- `resource_guard_report.json`
- `json_compliance_probe.json`
- `diversity_probe.json`
