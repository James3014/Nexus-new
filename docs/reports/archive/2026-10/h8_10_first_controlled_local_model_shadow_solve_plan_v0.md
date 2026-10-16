# H8-10 First Controlled Local Model Shadow Solve Plan v0

**日期**: 2026-06-26  
**狀態**: `H8_10_FIRST_CONTROLLED_LOCAL_MODEL_SHADOW_SOLVE_PLAN_DRAFT_READY_FOR_REVIEW`  
**治理/安全**: `REPORT_ONLY=true`, `NO_LOCAL_MODEL_RUN`, `NO_OLLAMA_CALL`, `NO_QWEN_CALL`, `NO_PROVIDER_CALL`, `NO_MODEL_CALL`, `NO_MODEL_LOAD`, `NO_MODEL_EXECUTION`, `NO_RUNTIME_ROUTING_ENABLED`, `PUBLIC_CLAIM_ALLOWED=false`  

---

## 0. Status / Safety Boundary

* **status**: `H8_10_FIRST_CONTROLLED_LOCAL_MODEL_SHADOW_SOLVE_PLAN_DRAFT_READY_FOR_REVIEW`
* **report_only=true**
* **no local model run**
* **no Ollama call / Qwen call**
* **no provider call / model call / network call / model load / model execution**
* **no runtime routing enabled**
* **production_ready=false**
* **public_claim_allowed=false**

---

## 1. Entry Requirements

All must pass before H8-10A:

| Gate | Status |
| :--- | :--- |
| H8-1 deny-by-default | PASS |
| H8-2 adapter receipt schema | PASS |
| H8-3 fake adapter controlled dry-run gate | PASS |
| H8-4 fake adapter pipeline gate | PASS |
| H8-5 verifier receipt gate | PASS |
| H8-6 allowlist contract | PASS |
| H8-7 production seam proposal | PASS |
| H8-8 minimal contract stub | PASS |
| H8-9 first solve harness | PASS |

Additional requirements:
* clean or isolated worktree preferred
* one task only
* one model only
* explicit owner approval
* explicit `dry_run_approved=true`
* `model_load_allowed=true` only for this run
* `model_call_allowed=true` only for this run
* `network_allowed=false`
* `provider_call_allowed=false` unless local provider is explicitly allowlisted
* `public_claim_allowed=false`
* `production_ready=false`
* receipt required
* verifier required
* candidate isolation required

---

## 2. First Solve Candidate Task

**Option A (recommended)**: synthetic local fixture task.

Do not start with real benchmark unless owner explicitly approves.

---

## 3. Required Receipt Fields

`task_id`, `candidate_id`, `selected_candidate_hash`, `local_model_provider`, `local_model_name`, `local_model_allowed`, `local_model_loaded`, `local_model_called`, `model_load_allowed`, `model_call_allowed`, `network_allowed`, `provider_call_allowed`, `dry_run_approved`, `evidence_refs`, `verifier_result`, `candidate_output_isolated`, `public_claim_allowed=false`, `production_ready=false`

---

## 4. Hard Stop Conditions

* missing `evidence_refs`
* missing `receipt_id`
* missing `selected_candidate_hash`
* model tries network
* provider is not allowlisted
* model is not allowlisted
* more than one task requested
* runtime routing attempted
* public claim attempted
* `production_ready` attempted

---

## 5. Recommended Next Task

**H8-10A Execute First Controlled Local Model Shadow Solve on Synthetic Fixture**

Only after explicit owner approval.

---

## 6. Final State

`H8_10_FIRST_CONTROLLED_LOCAL_MODEL_SHADOW_SOLVE_PLAN_DRAFT_READY_FOR_REVIEW`

Forbidden: `H8_RUNTIME_STARTED`, `LOCAL_MODEL_ENABLED`, `OLLAMA_CALLED`, `QWEN_CALLED`, `PROVIDER_CALLED`, `MODEL_CALLED`, `MODEL_LOADED`, `ROUTING_READY`, `PRODUCTION_READY`, `PUBLIC_CLAIM_ALLOWED`
