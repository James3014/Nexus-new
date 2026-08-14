---
task_id: github-issue-293-external-memory-admission-order-20260815
issue: 293
repository: James3014/Nexus-new
baseline_revision: cdf2570ede5ae218f36f886b696c8da45458043a
status: ACTIVE
readiness_marker: EXTERNAL_MEMORY_ADMISSION_ORDER_SOURCE_FROZEN
AUTO_CHAIN: false
claim_ceiling: external_memory_admission_order_candidate_pr_only
implementation_files:
  - nexus/research/learn/ingest_service.py
  - nexus/research/learn/learn_models.py
  - nexus/research/learn_mode.py
  - nexus/services/mem_palace.py
  - tests/research/test_external_memory_admission_gate.py
  - tests/research/test_learn_ingest_channels.py
governance_files:
  - tasks/github-issue-293-external-memory-admission-order-20260815/INDEX.md
  - tasks/github-issue-293-external-memory-admission-order-20260815/github-issue-293-external-memory-admission-order-20260815.md
allowed_files:
  - nexus/research/learn/ingest_service.py
  - nexus/research/learn/learn_models.py
  - nexus/research/learn_mode.py
  - nexus/services/mem_palace.py
  - tests/research/test_external_memory_admission_gate.py
  - tests/research/test_learn_ingest_channels.py
max_files: 6
authorized_deletions: []
worker_may_commit: false
worker_may_push: false
worker_may_approve: false
worker_may_integrate: false
worker_may_merge: false
candidate_lane:
  worker: opencode_deepseek_v4_flash
  model: opencode/deepseek-v4-flash-free
  role: bounded_candidate_generation
  mutation_intent: false
  autonomy: L1
  external_verification_required: true
  admission_policy_hash: 8bc154848ac95b2478045c0d4568fcbb208263d4f46232d8b671a88b4a13bdca
  admission_binding_hash: bff35a27645eb9a09e42574da9adf514dc76101cdf170f0c15f0209ebb78f049
  admission_aggregate_hash: 2e20ea1d9edc0f8b5c8c600dbcfc412d31f15b164cabaeedf08dc86cbfa6a132
---

# Issue #293 — fail closed before external memory becomes retrievable

## Objective

Generate one bounded Candidate that makes admission state authoritative before
externally sourced claims can enter the canonical retrievable claim store.
MemPalace remains the existing verification owner; this slice changes ordering
and durable admission metadata, not verification authority.

## Frozen source finding

On baseline main, `IngestService.ingest` snapshots and splits external source
text, calls `_append_claims(claims)`, and only afterwards calls
`MemPalace.verify`. The append writes to
`.nexus/knowledge/learn_claims.jsonl`; downstream learn-mode retrieval has no
admission-state gate and may inject those records as prior art. Therefore an
unverified external claim can become durable and retrievable before the
existing verifier has decided its status.

## Required behavior

- Every newly ingested external claim carries a canonical, explicit admission
  state before it can be appended to or read from the retrievable claim store.
- Only claims accepted by the existing MemPalace verification result are
  retrievable.
- Rejected, missing, malformed, unknown, contradictory, tampered, or
  unverifiable admission state fails closed and is not injected as prior art.
- Historical records without an admission state are normalized as
  `legacy_unverified` and remain non-retrievable until independently admitted;
  they are not silently trusted or deleted.
- Existing ingest result fields, multi-source behavior, snapshots, Findings
  cards, and learning-closure reporting remain compatible.
- Repeated reads are deterministic and read-only.

## Forbidden

- A second verifier, truth ledger, Planner, Router, scheduler, store, or
  promotion authority.
- Weakening or bypassing MemPalace verification.
- Provider/model routing, Workforce policy, lifecycle, approval, integration,
  merge, runtime activation, release, or production changes.
- File deletion, migration outside the six allowed paths, or scope widening.

## Verification

```text
uv run pytest -q tests/research/test_external_memory_admission_gate.py tests/research/test_learn_ingest_channels.py tests/core/test_mem_palace.py
git diff --check
```

Hostile witnesses must cover rejection before retrieval, unknown/malformed and
legacy records failing closed, tampered admission metadata, accepted records
remaining retrievable, repeated read determinism, and preservation of the
existing ingest response contract. Audit exactly the six allowed files and
zero deletions.

## Exit

A bounded isolated Candidate diff in no more than the six allowed files with
all focused tests passing. The DeepSeek worker cannot commit, push, approve,
integrate, merge, or claim runtime/release/production truth. Publication and
acceptance remain separate coordinator gates.

`AUTO_CHAIN=false`. Claim ceiling:
`external_memory_admission_order_candidate_pr_only`.
