# AK1/AK2/AK3 Nexus Capability Invocation Forensic Audit

**Date**: 2026-06-21
**Auditor**: Independent (Agent A)
**Scope**: local_heal / local_full_nexus_repair_control_plane_v0 / optimized 3B + dual 7B route
**Status**: AK3_FORENSIC_DECISION_READY
**Classification**: INTERNAL_ONLY=true | public_claim_allowed=false | production_ready=false | training_export_allowed=false

---

## Executive Summary

**AK3 Decision: AK3_CAPABILITIES_INVOKED_BUT_PARTIALLY_NON_INFLUENTIAL**

Of 17 audited Nexus capabilities, **6 are genuinely invoked and influential**, **5 are invoked but have limited or no decision influence**, and **6 are bypassed, stubbed, or receipt-only**. The most critical finding: **Evidence Graph is hardcoded per-task and does not perform runtime AST analysis**. Memory/LanceDB scoring in Semantic Anchor Selection uses hardcoded pattern lists instead of actual retrieval. Several receipt adapters build claims from payload fields without proof of actual capability invocation.

---

## AK1 — Static Wiring Audit

**Status: AK1_PARTIAL_WIRING_FOUND**

### Capability Binding Matrix

| # | Capability | Module | Invocation | Classification | Evidence |
|---|-----------|--------|-----------|----------------|----------|
| 1 | **CodeIntel** | `nexus/services/local_heal/evidence_graph.py` | `EvidenceGraphBuilder.build()` | **STUB** | Hardcoded task_id branching (sympy-14096, django-11505, django-13455); generic fallback returns single-node graph |
| 2 | **Evidence Graph** | Same as above | Same | **STUB** | No runtime AST call-graph traversal; pre-built node/edge sets for 3 known tasks only |
| 3 | **Memory / LanceDB** | `nexus/services/local_heal/semantic_anchor_selection.py` → `_score_prior_lessons()` | Internal scoring method | **SIMULATED** | Hardcoded `success_patterns` (`__getattr__`, `_encode`, `limit`, `write_format`) and `failure_patterns` (`iterator`, `for_loop`, `mechanical`); no actual LanceDB retrieval call |
| 4 | **Autoreason** | `nexus/engine/autoreason_service.py` | `AutoreasonService.run()` | **REAL** | Deterministic Borda panel with adversarial critique; no external LLM in core path; `JudgeProvider` protocol exists but no providers injected in local_heal context |
| 5 | **DDTree** | `nexus/engine/ddtree_adapter.py` | `DDTreeAdapter.plan()` | **REAL** | Score-based sort + dual-track veto; simple but functional pruning logic |
| 6 | **Belief** | `nexus/core/belief_engine.py` | `BeliefEngine.process_audit_outcome()` | **REAL** | State persistence via JSON; semantic confidence blending; but default confidence is static 0.7 |
| 7 | **3B Judge** | `nexus/services/local_heal/local_model_policy.py` (via `LocalModelPolicy.select_model`) | Model selection | **REAL** | Selects Qwen14B/DeepSeek based on task_type; actual Ollama calls in `llm_client.py` |
| 8 | **Qwen 7B proposer** | `nexus/services/local_heal/llm_client.py` → `OllamaLLMClient` | LLM inference | **REAL** | Actual Ollama HTTP calls with timeout/model selection |
| 9 | **DeepSeek 6.7B proposer** | Same | Same | **REAL** | Same infrastructure as Qwen |
| 10 | **Action Protocol** | `nexus/services/local_heal/action_protocol.py` | `ActionProtocol.validate_protocol()` | **REAL** | Validates multi-file coordinated edits; enforces owner_approval_required for TWO_FILE_COORDINATED_EDIT |
| 11 | **Deterministic Applier** | `nexus/services/local_heal/patch_applier.py` | Patch application | **REAL** | Applies SEARCH/REPLACE intents with verification |
| 12 | **Sandbox / Replay** | `nexus/services/local_heal/sandbox.py` + `nexus/engine/ultra_review_service.py` | `SandboxExecutor.run_and_summarize()` + `UltraReviewService.run()` | **REAL (partial)** | Sandbox: basic subprocess runner. UltraReview: real git-worktree mirror + security/logic/ghost regression checks; but dry-run only |
| 13 | **Ultra Review** | `nexus/engine/ultra_review_service.py` | `UltraReviewService.run(dry_run=True)` | **REAL (dry-run only)** | 3-lane fleet: security_sentry, logic_breaker, ghost_regression; git worktree sandbox; but `dry_run=False` raises `UltraReviewError` |
| 14 | **Artifact / Claim / Delivery Gate** | `nexus/engine/capability_receipt_adapters.py` | Receipt adapters | **RECEIPT-ONLY** | Adapters build receipts from payload fields; no standalone gate executor found in local_heal pipeline |
| 15 | **Learning Closure / Meta-Opt** | No direct invocation in local_heal pipeline | Not invoked | **BYPASSED** | No writeback call in orchestrator.py, receipt.py, or pipeline.py |
| 16 | **Resource Guard** | `nexus/services/local_heal/backend_resource_policy.py` | Backend resource policy | **REAL** | Enforces resource constraints |
| 17 | **Regression Guard** | `nexus/engine/ultra_review_service.py` → `_run_ghost_regression()` | Ghost regression checks | **REAL** | Runs existing regression test candidates via pytest in sandbox |

### Critical Findings (AK1)

**FINDING AK1-01: Evidence Graph is Hardcoded (STUB)**
- File: `nexus/services/local_heal/evidence_graph.py:92-219`
- `EvidenceGraphBuilder.build()` branches on hardcoded task_id strings:
  - `"sympy-14096"` → pre-built 3-node graph
  - `"django-11505"` → pre-built 3-node graph
  - `"django-13455"` → pre-built 2-node graph
  - All others → single generic node graph
- **No runtime AST call-graph traversal exists**
- Source hashes are hardcoded (`hash_l1`, `hash_p1`, `hash_gen`)

**FINDING AK1-02: Memory/LanceDB Scoring is Simulated**
- File: `nexus/services/local_heal/semantic_anchor_selection.py:311-326`
- `_score_prior_lessons()` uses hardcoded pattern lists:
  - `success_patterns = ["__getattr__", "_encode", "limit", "write_format"]`
  - `failure_patterns = ["iterator", "for_loop", "mechanical"]`
- No actual LanceDB or vector retrieval call
- No `import lancedb` or similar in the file

**FINDING AK1-03: Receipt Adapters Lack Invocation Proof**
- File: `nexus/engine/capability_receipt_adapters.py`
- Many adapters (ClaimGateReceiptAdapter, DeliveryGateReceiptAdapter, ArtifactGateReceiptAdapter) build receipts from payload dict fields
- `gate_passed` is derived from `_as_bool(payload.get("claim_gate_passed"))` — settable by caller
- No adapter verifies that the capability was actually executed before accepting the claim

**FINDING AK1-04: Learning Closure Not Wired**
- `orchestrator.py` does not import or call any learning/writeback module
- `receipt.py` does not write learning closure notes
- `pipeline.py` has no learning closure phase

---

## AK2 — Dynamic Invocation Trace Audit

**Status: AK2_CAPABILITY_INVOKED_BUT_NO_INFLUENCE (partial)**

### Trace Analysis

Based on static analysis of the code paths (no runtime execution per audit constraints):

**Route Decision Flow:**
1. `HealOrchestrator.run()` → `_run_linear_phases()` (Reproduction → Planning → Localization)
2. `_run_repair_loop()` → Patch Synthesis → Verification
3. `GovernanceGate.audit()` → `ReceiptWriter`

**Capability Invocation During Repair:**

| Phase | Capability | Actually Called? | Influences Decision? |
|-------|-----------|-----------------|---------------------|
| Planning | CodeIntel (evidence_graph) | Yes (if invoked) | **NO** — returns hardcoded graph for known tasks, generic for others |
| Planning | Semantic Anchor Selection | Yes | **PARTIAL** — real AST scoring, but prior_lessons scoring is simulated |
| Planning | DDTree | Yes (if candidates > max) | **YES** — actually prunes candidates by score |
| Planning | Autoreason | **NO** — not called in local_heal pipeline | **N/A** |
| Patch | Qwen/DeepSeek proposer | Yes | **YES** — actual LLM inference |
| Patch | Action Protocol | Yes (for multi-file) | **YES** — enforces owner approval |
| Patch | Deterministic Applier | Yes | **YES** — applies patches |
| Verification | Sandbox | Yes | **YES** — runs tests |
| Verification | Ultra Review | **DRY-RUN ONLY** | **PARTIAL** — security/logic checks run, but `dry_run=False` not supported |
| Post-verify | Belief Engine | **NO** — not called in local_heal | **N/A** |
| Post-verify | Memory/LanceDB | **NO** — not called in local_heal | **N/A** |
| Post-verify | Learning Closure | **NO** — not called in local_heal | **N/A** |
| Post-verify | Claim/Delivery Gate | **NO** — receipt only | **N/A** |

### Critical Findings (AK2)

**FINDING AK2-01: Autoreason Not Invoked in local_heal**
- `AutoreasonService` exists and is well-implemented
- But `orchestrator.py` does not import or call it
- Candidate selection goes through `DDTreeAdapter.plan()` instead

**FINDING AK2-02: Belief Engine Not Invoked in local_heal**
- `BeliefEngine` exists with state persistence
- But no code path in local_heal calls `process_audit_outcome()` or `assess_confidence()`
- Belief uncertainty does not affect selector scores

**FINDING AK2-03: Memory/LanceDB Not Invoked**
- `MemoryReceiptAdapter` exists but is never populated by local_heal
- `_score_prior_lessons()` in SemanticAnchorScorer is hardcoded, not backed by retrieval

**FINDING AK2-04: Learning Closure Not Invoked**
- No writeback call exists in the pipeline
- `learning_closure_note.json` files found in artifacts are from prior 3B shadow advisory tracks, not from local_heal

**FINDING AK2-05: Ultra Review Dry-Run Only**
- `UltraReviewService.run()` raises `UltraReviewError` when `dry_run=False`
- Security sentry, logic breaker, ghost regression all execute
- But the gate cannot block promotion in production mode

---

## AK3 — Ablation and Sentinel Verification

**Status: AK3_CAPABILITIES_INVOKED_BUT_PARTIALLY_NON_INFLUENTIAL**

### Ablation Test Results (Static Analysis)

| Test | Expected | Actual | Verdict |
|------|----------|--------|---------|
| Disable Memory | Selector loses prior lesson scoring | **No change** — `_score_prior_lessons()` is hardcoded, never backed by retrieval | **PASS (no-op ablation)** |
| Disable DDTree | Candidate count increases | **Correct** — DDTree actually prunes candidates by score | **CONFIRMED INFLUENTIAL** |
| Disable CodeIntel graph | Evidence graph quality drops | **No change** — graph is already hardcoded/generic | **FAIL (no-op ablation)** |
| Disable Sandbox/Ultra Review | Owner-gated tasks cannot be promoted | **Partially correct** — Sandbox runs tests; Ultra Review is dry-run only | **PARTIAL** |
| Disable Claim/Delivery | Final accepted status cannot be produced | **No change** — receipt-only, not wired as gate | **FAIL (no-op ablation)** |
| Disable Learning Closure | Writeback missing | **No change** — already not wired | **FAIL (no-op ablation)** |

### Sentinel Test Results (Static Analysis)

| Test | Expected | Actual | Verdict |
|------|----------|--------|---------|
| Fake memory lesson | Must not be accepted without provenance | **N/A** — memory not invoked | **N/A** |
| Fake CodeIntel node | Must fail source_hash/provenance check | **FAIL** — hardcoded hashes cannot be verified at runtime | **FAIL** |
| Fake verifier pass | Must not become claim success | **PARTIAL** — `claim_eligible` requires `reached_verification` AND `actually_solved` | **PARTIAL** |
| Fake sandbox pass | Must not override verifier | **PASS** — verification is independent phase | **CONFIRMED** |
| Fake owner approval | Must not allow broad edit | **PASS** — `ActionProtocol` validates `owner_approval_required` | **CONFIRMED** |
| Task_id perturbation | Must not trigger hardcoded route | **FAIL** — Evidence Graph branches on task_id strings | **FAIL** |

### Critical Findings (AK3)

**FINDING AK3-01: Evidence Graph Has No Provenance Verification**
- Hardcoded `source_hash` values (`hash_l1`, `hash_p1`) cannot be verified against actual source
- Task_id branching means any perturbed task_id produces a generic graph
- No runtime source_hash computation exists in `EvidenceGraphBuilder.build()`

**FINDING AK3-02: Receipt Adapters Accept Self-Reported Claims**
- `ClaimGateReceiptAdapter.build()` sets `gate_passed = bool(refs and claim_verified)` where `claim_verified` comes from caller
- No external verification that the claim was actually validated
- `DeliveryGateReceiptAdapter` follows same pattern

**FINDING AK3-03: Autoreason+Belt Belief Not Connected**
- Both capabilities exist and are well-implemented
- Neither is wired into the local_heal pipeline
- The pipeline uses a simpler DDTree + heuristic selection path

---

## Capability Classification Summary

### Genuinely Invoked and Influential (6)
1. **DDTree** — Actually prunes candidates by score; influences selection
2. **Qwen 7B proposer** — Real LLM inference via Ollama
3. **DeepSeek 6.7B proposer** — Real LLM inference via Ollama
4. **Action Protocol** — Enforces multi-file edit governance
5. **Deterministic Applier** — Applies patches with verification
6. **Sandbox/Regression Guard** — Runs test suites in isolated environment

### Invoked But Limited Influence (5)
1. **Semantic Anchor Selection** — Real AST scoring, but prior_lessons is simulated
2. **Ultra Review** — Real 3-lane checks, but dry-run only (cannot block)
3. **Reasoning Router** — Real routing, but only 2 heuristic rules
4. **Resource Guard** — Exists but minimal influence on repair decisions
5. **3B Judge (LocalModelPolicy)** — Model selection works, but no multi-judge deliberation

### Bypassed / Stubbed / Receipt-Only (6)
1. **CodeIntel (Evidence Graph)** — Hardcoded per-task; no runtime AST traversal
2. **Memory / LanceDB** — Hardcoded pattern scoring; no retrieval
3. **Autoreason** — Not wired into local_heal pipeline
4. **Belief Engine** — Not wired into local_heal pipeline
5. **Learning Closure** — Not wired into local_heal pipeline
6. **Claim / Delivery Gate** — Receipt adapters only; no gate executor

---

## Decision

**AK3_CAPABILITIES_INVOKED_BUT_PARTIALLY_NON_INFLUENTIAL**

### Rationale
- Core repair capabilities (LLM proposer, patch applier, verifier, DDTree) are genuinely invoked
- Evidence Graph, Memory, Autoreason, Belief, Learning Closure are **not connected** to the local_heal decision path
- Receipt adapters exist for all capabilities but many accept self-reported claims without independent verification
- Ultra Review runs but cannot gate promotion (dry-run only)

### Agent B Fix Track Required

**Must-fix gaps:**
1. Evidence Graph must perform runtime AST call-graph analysis (not hardcoded)
2. Memory/LanceDB must provide actual retrieval-backed prior lesson scoring
3. Autoreason must be wired into candidate selection or advisory path
4. Belief Engine must be wired into confidence tracking
5. Learning Closure must write back lessons from repair outcomes
6. Claim/Delivery Gate must verify invocation before accepting claims

### Flags
```
public_claim_allowed=false
production_ready=false
training_export_allowed=false
internal_only=true
```

---

## Appendix: File Index

| File | Lines | Role |
|------|-------|------|
| `nexus/services/local_heal/orchestrator.py` | 508 | Main repair orchestrator |
| `nexus/services/local_heal/evidence_graph.py` | 219 | **STUB** — hardcoded evidence graphs |
| `nexus/services/local_heal/semantic_anchor_selection.py` | 823 | Anchor selection with simulated memory |
| `nexus/services/local_heal/action_protocol.py` | 159 | Multi-file edit protocol |
| `nexus/engine/ddtree_adapter.py` | 101 | Candidate pruning |
| `nexus/engine/autoreason_service.py` | 482 | Deterministic autoreason (not wired) |
| `nexus/core/belief_engine.py` | 85 | Belief state (not wired) |
| `nexus/engine/ultra_review_service.py` | 875 | Ultra review (dry-run only) |
| `nexus/services/local_heal/sandbox.py` | 57 | Basic sandbox executor |
| `nexus/engine/capability_receipt_adapters.py` | 1196+ | Receipt adapters (receipt-only) |
| `nexus/engine/capability_wiring_audit.py` | 183 | Static wiring metadata |
| `nexus/services/local_heal/receipt.py` | 562 | Receipt builder |
| `nexus/services/local_heal/candidate_generation.py` | 403 | Narrow-span candidate generation |
| `nexus/services/local_heal/reasoning_router.py` | 45 | Heuristic reasoning mode router |
| `nexus/services/local_heal/native_validation_bridge.py` | 86 | Validation receipt binding |
| `nexus/services/local_heal/verifier_replay_gate.py` | 90 | Verifier replay eligibility |

---

**End of forensic audit.**
**Commit rule**: Audit reports only. No product code edits. Agent B fix track opened.
