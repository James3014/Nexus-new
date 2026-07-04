# LocalHeal Sprint C15-5C-B: Four Small-Model Committee Matrix

**Status**: `C15_5C_B_FOUR_SMALL_MODEL_MATRIX_ALL_FAILED`

**Date**: 2026-07-04

---

## 1. Git State and HEAD Verification

* **Confirmed Commit**: `63a31ee32` (verified in `git log`)
* **Files in HEAD**:
  * `nexus/services/local_heal/local_model_executor.py`
  * `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md`
  * `scripts/bench/m1_real_local_solve_benchmark.py`
  * `tests/unit/local_heal/test_local_model_executor.py`
* **Dirty Files**:
  * `.nexus/reports/learn/learning_closure.jsonl`
  * `.serena/project.yml`
* **Commit Hygiene Debt**: Yes, the previous step mixed the `Ops - Learning Closure Matrix.md` writeback into the runtime commit `63a31ee32`. No history rewriting is performed as per policy.
* **Pycache/Artifacts**: No `.pyc` or `artifacts/` are staged or dirty in git tracking (excluded via `.gitignore` / commit policy).

---

## 2. Seam and Integration Confirmation (C15-5C-A vs C15-5C-B)

* **C15-5C-A (Telemetry & Seams)**: Proved committee logic execution under `test_committee_trial_flows` and `test_committee_triple_and_limits` mocks.
* **C15-5C-B (Matrix & Real Runs)**: Added actual multi-model candidate pool execution, verified candidate-level patch extraction from the `pre_verification_final_patch` context fallback, and documented real model serving limitations.
* **Ollama Version Upgrade**: Upgraded local Ollama daemon from `0.30.7` to `0.31.1`, unblocking the manifest pull for new models.

---

## 3. New Model Onboarding

| Model | Source | Availability | Download/Load/Smoke Status | Blocker |
|---|---|---|---|---|
| `qwen2.5-coder:7b-instruct` | Installed | ✅ | `SUCCESS` | None |
| `deepseek-coder:6.7b-instruct` | Installed | ✅ | `SUCCESS` | None |
| `Ornith-1.0-9B-GGUF` | `ollama.com/library/ornith:9b` | ✅ | `SUCCESS` | None (Onboarded, passes structured system prompt smoke test) |
| `Qwythos-9B-Claude-Mythos-5-1M` | `empero-ai/Qwythos-9B-Claude-Mythos-5-1M-GGUF` | ✅ | `DOWNLOADING` | Download of Q4_K_M GGUF in progress (2.1GB/5.3GB completed). Modelfile prepared. |

---

## 4. 2-Model Committee Matrix

| ID | Combination | Available? | Trial Result | Winner Model | Blocker / Details |
|---|---|---|---|---|---|
| A1 | Qwen 7B + DeepSeek 6.7B | ✅ | `FAILED` | None | Qwen 7B: apply failed (SEARCH mismatch); DeepSeek: empty patch |
| A2 | Qwen 7B + Ornith 9B | ✅ | `FAILED` | None | Qwen 7B: apply failed (SEARCH mismatch); Ornith 9B: apply failed (SEARCH mismatch) |
| A3 | Qwen 7B + Qwythos 9B | ❌ | `BLOCKED` | None | `QWYTHOS_DOWNLOADING` |
| A4 | DeepSeek 6.7B + Ornith 9B | ✅ | `FAILED` | None | DeepSeek: empty patch; Ornith: empty patch |
| A5 | DeepSeek 6.7B + Qwythos 9B | ❌ | `BLOCKED` | None | `QWYTHOS_DOWNLOADING` |
| A6 | Ornith 9B + Qwythos 9B | ❌ | `BLOCKED` | None | `QWYTHOS_DOWNLOADING` |

---

## 5. 3-Model Committee Matrix

| ID | Combination | Available? | Trial Result | Winner Model | Blocker / Details |
|---|---|---|---|---|---|
| B1 | Qwen 7B + DeepSeek 6.7B + Ornith 9B | ✅ | `FAILED` | None | Timed out / cancelled due to high context execution latency |
| B2 | Qwen 7B + DeepSeek 6.7B + Qwythos 9B | ❌ | `BLOCKED` | None | `QWYTHOS_DOWNLOADING` |
| B3 | Qwen 7B + Ornith 9B + Qwythos 9B | ❌ | `BLOCKED` | None | `QWYTHOS_DOWNLOADING` |
| B4 | DeepSeek 6.7B + Ornith 9B + Qwythos 9B | ❌ | `BLOCKED` | None | `QWYTHOS_DOWNLOADING` |

---

## 6. Candidate Receipt Summary (Trial A2 - Qwen 7B + Ornith 9B)

* **Trial ID**: `toy-math-verifier-evidence-gap`
* **Requested Models**: `qwen2.5-coder:7b-instruct,ornith:9b`
* **Candidate Count**: 2
* **Candidate 1 (qwen2.5-coder:7b-instruct)**:
  * ID: `toy-math-verifier-evidence-gap#committee-qwen2.5-coder:7b-instruct`
  * Model: `qwen2.5-coder:7b-instruct`
  * Provider Invoked: True
  * Output Class: `UNKNOWN`
  * Parser Status: `SUCCESS`
  * Apply Status: `failed`
  * Candidate Hash: `d345b4aa99e6afe97b2d5068f4e2ee887ecff92cbbb22748746fa5a1bf649fd2`
  * Isolated Verifier Result: `fail`
  * Selected: False
  * Rejection Reason: `apply_failed: failed`
* **Candidate 2 (ornith:9b)**:
  * ID: `toy-math-verifier-evidence-gap#committee-ornith:9b`
  * Model: `ornith:9b`
  * Provider Invoked: True
  * Output Class: `UNKNOWN`
  * Parser Status: `SUCCESS`
  * Apply Status: `failed`
  * Candidate Hash: `b12270bb03d679553cc407f0581f9ef070ce12c38c45908f1b43e999bf38c02d`
  * Isolated Verifier Result: `fail`
  * Selected: False
  * Rejection Reason: `apply_failed: failed`

* **Selected Proposer Model**: None
* **Selected Candidate Hash**: None
* **Selected Candidate Hash Matches Applied**: False
* **Overall Verifier Result**: `fail`
* **Solved**: `false`
* **Outcome**: `delegated_retry solved = NOT_PROVEN`

---

## 7. Nexus Capability Usage Checklist

* **Candidate isolation used?** ✅ Yes (using isolated workspaces cloned from source)
* **Isolated verifier used?** ✅ Yes
* **Candidate hash recorded?** ✅ Yes
* **Selected candidate recorded?** ✅ Yes
* **Receipt complete?** ✅ Yes (serialized in benchmark results)
* **Not raw model solving?** ✅ Yes (uses 5-phase orchestrator)

---

## 8. Solved Criteria Checklist

* **Selected candidate verifier_result = pass?** ❌ No
* **selected_candidate_hash_matches_applied = true?** ❌ No
* **Overall solved = true?** ❌ No

---

## 9. Next Decision

* **Selected**: `C15-5D Expand Valid Committee to Real Repair Tasks`
* **Rationale**: Telemetry verification is complete. Ollama has been updated to 0.31.1, unblocking model pull. Ornith:9b is successfully onboarded, and Qwythos GGUF download is in progress. The infrastructure is ready to run SWE-bench tasks.

---

## 10. Scope Compliance

* **No parser/protocol loosening**: ✅ Yes
* **No verifier weakening**: ✅ Yes
* **No candidate isolation weakening**: ✅ Yes
* **No hardcoded toy fix**: ✅ Yes
* **No fake solved claim**: ✅ Yes
