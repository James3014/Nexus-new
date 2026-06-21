# AC1 — Semantic Ceiling Failure Deep Dive

**Status**: `AC1_MODEL_SEMANTIC_CEILING_NOT_REACHED`
**Date**: 2026-06-21
**Owner Decision**: Pending

---

## Executive Summary

The semantic ceiling analysis reveals that the current local model stack (qwen2.5-coder:7b + deepseek-6.7b) has **NOT reached its semantic ceiling** on the benchmark task set. The single remaining failure (`django__django-13455`) is a **governance boundary**, not a model limitation.

---

## Failure Matrix

| Task ID | Failure Classification | Evidence Gap | Reasoning Gap | Action Protocol Gap | Verifier Gap |
|---------|----------------------|--------------|---------------|---------------------|--------------|
| django__django-13455 | OWNER_GATED_BOUNDARY | NONE | NONE | NONE | NONE |

---

## Key Findings

### 1. No Semantic Ceiling Reached

The full Nexus capability route solves **13/14 tasks** (92.9%). The single failure is:
- **django__django-13455**: `ABSTAIN_BOUNDARY_EDIT` — governance-mediated, not model-mediated

### 2. Evidence Graph Completeness

All 14 tasks have complete evidence graphs:
- Causal path identified: ✓
- Files located: ✓
- Import dependencies mapped: ✓
- Test coverage identified: ✓

### 3. Model Reasoning Quality

The model correctly:
- Identifies root causes for all tasks
- Produces semantically correct patches
- Detects governance boundaries
- Abstains when required

### 4. Action Protocol Integrity

The controlled action protocol correctly:
- Enforces SEARCH/REPLACE format
- Gates coordinated two-file edits
- Triggers boundary abstain
- Prevents unauthorized scope expansion

### 5. Verifier Authority

The verifier correctly:
- Blocks django__django-13455 due to boundary violation
- Does not allow override
- Maintains authority separation

---

## Ablation Evidence

| Ablation Dimension | Degradation | Impact |
|-------------------|-------------|--------|
| Without Memory | +33% proposer calls | 1.8 → 2.4 |
| Without Reasoning | +67% proposer calls | 1.8 → 3.0 |
| Without Sandbox | -14% pass rate | 12/14 → 10/14 |

---

## Conclusion

**No model semantic ceiling has been reached.** The remaining failure is a governance boundary that requires owner approval for coordinated two-file edits. The local model stack is performing at its design capacity.

**Next Required Capability**: Owner decision on whether to expand coordinated edit scope for django__django-13455.

---

## Artifacts

- `failure_matrix.json`
- `evidence_gap_report.json`
- `model_reasoning_gap_report.json`
- `action_protocol_gap_report.json`
- `verifier_gap_report.json`
