# V4-A.1R Capability Acceptance Packet

## Status: V4A1R_CAPABILITY_ACCEPTED_INTERNAL_ONLY

## Frozen Commit

`0da97cf3` — feat: V4-A.1R real replay pass — FUZZY_CANDIDATE_ONLY precedence fix + MC001 real execution receipt

## Capability Statement

"Nexus has internally validated local 7B/14B repair capability on one fresh real astropy task with verifier-backed receipt and claim separation. This is internal-only and not a public benchmark claim."

## Checks

### Real Execution Proof ✅
- execution_mode: real
- source: astropy v5.2.1 (SHA: 95df21d)
- model_calls: 1
- verifier: passed

### Local Model Proof ✅
- provider: Ollama
- model: qwen2.5-coder:7b
- cloud_api_used: false

### Attribution Proof ✅
- match_authority: verbatim
- success_attribution: model_patch_success
- export_classification: model_patch_success_candidate
- FUZZY_CANDIDATE_ONLY cannot silently override

### Verifier Proof ✅
- task_scoped: true
- env_taxonomy used
- no silent generic python3 fallback

### Governance Proof ✅
- public_claim_allowed: false
- training_eligible: false
- runtime_integration_enabled: false
- routing_integration_enabled: false

### Bug Fix Audit ✅
- FUZZY_CANDIDATE_ONLY precedence bug documented and fixed
- 17/17 tests pass

## Boundaries

1. Internal-only
2. Not public benchmark claim
3. Not training export
4. Not runtime/routing enablement
