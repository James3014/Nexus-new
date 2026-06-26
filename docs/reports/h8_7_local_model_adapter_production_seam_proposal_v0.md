# H8-7 Local Model Adapter Production Seam Proposal v0

**日期**: 2026-06-26  
**狀態**: `H8_7_LOCAL_MODEL_ADAPTER_PRODUCTION_SEAM_PROPOSAL_DRAFT_READY_FOR_REVIEW`  
**治理/安全**: `REPORT_ONLY=true`, `READ_ONLY=true`, `NO_LOCAL_MODEL_RUN`, `NO_OLLAMA_CALL`, `NO_QWEN_CALL`, `NO_PROVIDER_CALL`, `NO_MODEL_CALL`, `NO_MODEL_LOAD`, `NO_MODEL_EXECUTION`, `NO_H8_RUNTIME`, `NO_RUNTIME_ROUTING_ENABLED`, `PUBLIC_CLAIM_ALLOWED=false`  

---

## 0. Status / Safety Boundary

* **status**: `H8_7_LOCAL_MODEL_ADAPTER_PRODUCTION_SEAM_PROPOSAL_DRAFT_READY_FOR_REVIEW`
* **report_only=true**
* **read_only=true**
* **no production code modified**
* **no tests modified**
* **no CI modified**
* **no worktree created**
* **no files deleted / restored**
* **no git clean / restore / rm**
* **no local model run**
* **no Ollama call / Qwen call**
* **no provider call / model call / network call / model load / model execution**
* **no H8 runtime / no runtime routing enabled**
* **local_model_ready=false**
* **provider_ready=false**
* **model_ready=false**
* **routing_ready=false**
* **production_ready=false**
* **public_claim_allowed=false**

---

## 1. H8 Test Gate Summary

| Gate | Tests | Status |
| :--- | :--- | :--- |
| H8-1 deny-by-default | 12 | PASS |
| H8-2 adapter receipt schema | 13 | PASS |
| H8-3 fake adapter controlled dry-run gate | 12 | PASS |
| H8-4 fake adapter pipeline gate | 12 | PASS |
| H8-5 verifier receipt gate | 12 | PASS |
| H8-6 allowlist contract | 14 | PASS |
| **H8 total** | **75** | **PASS** |
| H7 + H8 combined | 228 | PASS |

---

## 2. Proposed Minimal Production Seam

Future files/classes only. Do not implement in H8-7.

| Class | Location candidate | Purpose |
| :--- | :--- | :--- |
| `LocalModelAdapterRequest` | `nexus/services/local_heal/local_model_adapter_contract.py` | Request contract for adapter |
| `LocalModelAdapterResponse` | `nexus/services/local_heal/local_model_adapter_contract.py` | Response contract |
| `LocalModelAdapterReceipt` | `nexus/services/local_heal/local_model_adapter_receipt.py` | Receipt with deny/allow flags |
| `LocalModelResourcePolicy` | `nexus/services/local_heal/local_model_resource_policy.py` | Deny-by-default resource policy |
| `FakeLocalModelAdapter` | test-only | Controlled dry-run adapter |
| `DeniedLocalModelAdapter` | test-only | Explicitly denied adapter |

**Note**: Current `nexus/services/local_heal/` files are dirty candidate work and must not be treated as accepted base.

---

## 3. Required Safety Defaults

| Field | Default |
| :--- | :--- |
| `local_model_allowed` | `false` |
| `local_model_loaded` | `false` |
| `local_model_called` | `false` |
| `model_load_allowed` | `false` |
| `model_call_allowed` | `false` |
| `provider_call_allowed` | `false` |
| `network_allowed` | `false` |
| `public_claim_allowed` | `false` |
| `production_ready` | `false` |

---

## 4. Required Receipt Fields

`receipt_id`, `request_id`, `candidate_id`, `selected_candidate_hash`, `local_model_provider`, `local_model_name`, `local_model_allowed`, `local_model_loaded`, `local_model_called`, `local_model_denied_reason`, `provider_call_allowed`, `network_allowed`, `model_load_allowed`, `model_call_allowed`, `fake_adapter`, `adapter_output_is_route_truth`, `candidate_output_isolated`, `route_truth_source`, `evidence_refs`, `verifier_result`, `public_claim_allowed`, `production_ready`

---

## 5. H8-8 Recommended Next Task

**H8-8 Minimal Production Contract Stub Behind Deny-by-Default Tests**

This future task may modify production code only if owner approves. H8-8 must still not call model.

---

## 6. Final State

`H8_7_LOCAL_MODEL_ADAPTER_PRODUCTION_SEAM_PROPOSAL_DRAFT_READY_FOR_REVIEW`

Forbidden: `H8_RUNTIME_STARTED`, `LOCAL_MODEL_ENABLED`, `OLLAMA_CALLED`, `QWEN_CALLED`, `PROVIDER_CALLED`, `MODEL_CALLED`, `MODEL_LOADED`, `ROUTING_READY`, `PRODUCTION_READY`, `PUBLIC_CLAIM_ALLOWED`
