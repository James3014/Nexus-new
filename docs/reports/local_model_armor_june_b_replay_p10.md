# Local Model Armor - P10 June-B Replay Report

This report documents the verification of the integrated Local Model Armor (Path B + Path C) with the mainline capability runner (Path A), demonstrating that June B-side tasks are safely governed and correctly reported in `evidence_bundle.json`.

---

## 1. Executive Verdict

**Verdict: PASS**

High-fidelity simulation and execution of June B-side tasks through the mainline A-side entry point (`capability_ab_runner.py`) confirm that the adapter seam is correctly wired and fully governed by C-side isolated solve loop safety mechanisms. All evidence counters populate `local_model_adapter_summary` in the final evidence bundle.

---

## 2. Replay Matrix & Comparison

| Metric | June-B Standalone (Path B/D Baseline) | ABC-Wired Replay (A -> B -> C -> A) | Alignment / Validation |
| :--- | :--- | :--- | :--- |
| **`sympy__sympy-13852`** | `solved = True` / `verifier = pass` | `verifier_result = pass` | **Aligned**. Successfully applied patch in isolated workspace and passed verifier checks. |
| **`astropy__astropy-12907`** | `blocked = True` / `fail-closed` | `route_mode = local_only_blocked` | **Aligned**. Successfully intercepted by path traversal guard, returning `path_traversal_detected`. |

---

## 3. Evidence Bundle Summary Statistics

Replaying the task suite under the gated seam environment (`NEXUS_WITH_LOCAL_MODEL_ADAPTER=1`, `NEXUS_LOCAL_MODEL_CALL_ALLOWED=1`, etc.) populated the following statistics in `evidence_bundle.json`:

```json
"local_model_adapter_summary": {
  "adapter_trace_count": 2,
  "adapter_invoked_count": 2,
  "local_model_called_count": 2,
  "candidate_isolated_count": 1,
  "hash_match_count": 1,
  "verifier_pass_count": 1,
  "fail_closed_count": 1,
  "behavior_changed_count": 0,
  "public_claim_allowed_count": 0,
  "production_ready_count": 0
}
```

### Safety Invariant Assertions
- **`behavior_changed_count`** is exactly `0`.
- **`public_claim_allowed_count`** is exactly `0`.
- **`production_ready_count`** is exactly `0`.
- No route truth is determined by the local adapter (remains `False`).

---

## 4. Verification Evidence & Commands

The integration tests were run and validated:

```bash
# Verify June-B Replay Test Harness
uv run pytest tests/benchmark/test_capability_ab_runner.py -k "june_b_replay" -q -rs
```

### Output
```text
tests/benchmark/test_capability_ab_runner.py .                           [100%]
====================== 1 passed, 1401 deselected in 2.70s ======================
```
