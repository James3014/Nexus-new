# Campaign Index: ASTRA-P6B-EFFECT-JOURNAL-20260907

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Implement opt-in source-owned durable effect reservation and UNKNOWN reconciliation on qualified source 4887d8f6a3faf50d6b600f2c170526e08d4bf408 plus independently accepted P6-A 94aaced105ac33a475eb61323b816379633f708d. Coordinator may transport exact card/INDEX bytes to an isolated branch with this dependency. Luna implements source only; no formal local lifecycle Candidate, approval, integration, push, merge, deployment, production activation, API-key/SDK/model/provider/network calls. Journal effect_journal.py is canonical writer under P6-A event_store_lock/generation guard. Persist PENDING before dispatch; states PENDING/DISPATCHED/COMPLETED/UNKNOWN with schema,operation_id,subject,request_digest,generation,effect_id,result,result_digest,reason,record_digest. Operation identity is canonical structured digest of validated task/workspace/planner/attempt/action/subject revision/full request digest. Generate deterministic effect ID before dispatch, bind exact observation. Separate dispatch and reconcile ports required in fenced mode; bare callable invalid there. Fence actual UnifiedRuntime local and online call seams after existing authority checks and only explicitly classified effectful capability invokers; exclude verifier/learning evidence callbacks. No second planner/provider selector. Legacy mode remains compatible; selected fenced mode with absent journal/token, malformed identity, generation drift, persistence failure never falls back. Hold atomic generation guard through reservation and effect start/dispatch; unlocked precheck insufficient. Existing uncertain intent must only reconcile via supplied readback port, never blind resend; unavailable/malformed/conflicting readback stays UNKNOWN. Completed replay returns exact persisted original result, no second effect. Result, subject, request, effect ID and generation binding mismatch denies. Preserve run_replan parent receipt identity and attempt budget; final receipt/root hash carries journal binding. UNKNOWN never becomes receipt_complete or public_claim_allowed, terminal INCOMPLETE. Durable atomic writes, no-follow paths, valid mapping/result serialization, released locks on exceptions. Verify actual two-process os._exit after durable effect marker, restart reconcile without redispatch, replay exact result, cross-binding/generation denial and persistence failures; local test effects only. Existing P6-A files additive guarded helpers only; no schema migration or live opt-in. Independent controller diff and full verifier required.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `astra-runtime-effect-journal-20260907` | `00-astra-runtime-effect-journal-20260907.md` | ACTIVE | Owner confirmation |
