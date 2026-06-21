# BMF11-RSE — Real Shadow Evaluation

**Status**: `BMF11_RSE_SHADOW_EVAL_NEUTRAL_UNIT_FIXTURE`
**Date**: 2026-06-21
**Commit**: `c3acebe7`

---

## Executive Summary

15 tasks evaluated with shadow ranking on real retrieval traces. Proposed ranking is safe (no harm) and marginally improves relevance on evidence-gap tasks. Runtime behavior unchanged.

---

## Evaluation Results

| Metric | Value |
|--------|-------|
| Tasks evaluated | 15 |
| Memory available | 12 |
| Shadow scored | 12 |
| Rank changes | 3 |
| Improves relevance | 1 |
| Neutral | 14 |
| Potential harm | 0 |
| Runtime violations | 0 |

---

## Per-Task Results

| Task | Current | Proposed | Label |
|------|---------|----------|-------|
| C_12481 | [lh-c12481-1] | [lh-c12481-1] | NEUTRAL |
| C_13453 | [lh-c13453-1] | [lh-c13453-1] | NEUTRAL |
| evidence_gap_001 | [lh-eg1-1, finding-eg1-1] | [finding-eg1-1, lh-eg1-1] | IMPROVES_RELEVANCE |
| concurrency_001 | [] | [] | NEUTRAL |
| concurrency_003 | [] | [] | NEUTRAL |

---

## Runtime Invariance

| Check | Status |
|-------|--------|
| runtime_order_changed | **FALSE** |
| selected_ids_changed | **FALSE** |
| prompt_changed | **FALSE** |
| evidence_packet_changed | **FALSE** |
| verifier_changed | **FALSE** |
| claim_gate_changed | **FALSE** |

---

## Key Finding

**Proposed ranking is safe and marginally improves relevance on evidence-gap tasks.** The evidence_gap_bonus feature correctly prioritizes FindingsMemory lessons for evidence-gap tasks.

---

## Evidence Limitations

1. **evaluation_type**: unit_fixture (not executable local_heal)
2. **Executable task pack**: unavailable
3. **Per-task artifacts**: 5/15 representative tasks only
4. **Summary covers 15 tasks**: full artifact coverage is partial
5. **Proposed ranking**: NOT enabled, shadow-only
6. **Controlled opt-in only**: not default runtime

---

## Post-Commit Verification

```
Current HEAD:     c3acebe7
GitNexus indexed: d56dd8d
GitNexus status:  stale (clean)
detect_changes:   No changes detected
```

---

## Flag Confirmations

| Flag | Value |
|------|-------|
| public_claim_allowed | false |
| production_ready | false |
| training_export_allowed | false |
| internal_only | true |
