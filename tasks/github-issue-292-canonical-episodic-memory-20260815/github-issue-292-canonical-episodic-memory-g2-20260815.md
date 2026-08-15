---
task_id: github-issue-292-canonical-episodic-memory-g2-20260815
issue: 292
repository: James3014/Nexus-new
baseline_revision: 19d815954ff72e99ed50734410cd2342a0b62bc7
status: COMPLETE
frontier_status: TERMINAL_RECONCILIATION
completion_marker: CANONICAL_EPISODIC_MEMORY_G2_APPLICABILITY_PROVEN
reconciled_main: d181a653d4a155266bf9e97fdfe35b69d3f08991
AUTO_CHAIN: false
claim_ceiling: canonical_episodic_memory_g2_source_and_tests_only
implementation_files:
  - nexus/services/local_heal/memory_retrieval_adapter.py
  - tests/unit/local_heal/test_memory_retrieval_adapter.py
governance_files:
  - tasks/github-issue-292-canonical-episodic-memory-20260815/INDEX.md
  - tasks/github-issue-292-canonical-episodic-memory-20260815/github-issue-292-canonical-episodic-memory-g2-20260815.md
allowed_files:
  - nexus/services/local_heal/memory_retrieval_adapter.py
  - tests/unit/local_heal/test_memory_retrieval_adapter.py
max_files: 2
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
  admission_binding_hash: 0f9953adf47df887193ddd5c56690027f071086a4f94251c662b92eee1dc349e
  admission_aggregate_hash: 0de383f087c83a2e6d303679235ba33b65c2ac4c824a94af7b4243007566a9ff
---

# Issue #292 G2 — deterministic current-state applicability

## Objective

Generate one bounded Candidate that filters canonical cross-task episodic
memory against explicitly supplied current-state identity and revision inputs.
G1 retrieval remains the only source seam. G2 is deterministic and read-only;
qualification of Task A alone never authorizes use in Task B.

## Frozen source finding

The existing G1 `CanonicalEpisodicMemoryLessonStore` already owns canonical
episode validation, terminal provenance, same-task exclusion, deduplication,
and read-only retrieval. Existing repository equivalents also provide
`MemoryHit.state_version` ordering and recency/trust/specificity semantics.
The smallest G2 seam is therefore the existing adapter plus its focused test
module; no contract, writer, schema, store, route, or planner change is needed.

## Required behavior

- Add an optional `current_state` mapping to the canonical retrieval path.
  `current_state=None` preserves G1 behavior.
- The accepted current-state vocabulary is exactly `state_version` (integer),
  `source_revision` (string), `contract_revision` (string),
  `runtime_identity` (string), and `max_age_days` (integer). Unknown keys,
  wrong types, or malformed values fail closed.
- Canonical episodes may supply additive `state_version`, `source_hash`,
  `contract_revision`, `runtime_identity`, and ISO-8601 `created_at` evidence.
- When a current-state dimension is supplied, the corresponding episode
  evidence must exist and match. Episode `state_version` must be less than or
  equal to the current version. Recency must be within `max_age_days`.
- Stale, future, missing, mismatched, malformed, or tampered applicability
  evidence is ineligible. Filtering is deterministic across repeated reads.
- Rejections are observable through bounded metadata/reason counters without
  returning rejected rows or leaking exceptions from the adapter.
- Same-task exclusion, terminal/provenance validation, deduplication, legacy
  source isolation, and `auto_replay_allowed=false` remain unchanged.
- Retrieval must not mutate the ledger or call providers, Router,
  CapabilityPlanner, Workforce, lifecycle, or runtime execution surfaces.

## Hostile witnesses

- Version boundary: lower/equal accepted, future rejected, non-integer rejected.
- Source, contract, and runtime identity: match accepted; mismatch or missing
  material evidence rejected.
- Recency: fresh accepted; stale, missing, malformed, or timezone-naive input
  rejected when `max_age_days` is supplied.
- Unknown/malformed `current_state` fails closed with no rows.
- Tampered applicability fields fail closed; repeated reads are byte-stable and
  leave the ledger unchanged.
- `current_state=None` reproduces the G1 result; legacy stores remain isolated
  and compatible; foreign-schema records still fail canonical validation.
- Tests assert returned rows as well as counters to prevent false-green
  metadata-only filtering.

## Forbidden

- G3/G4 implementation or changes under `nexus/learning/**`, `nexus/memory/**`,
  LearningEpisode contracts/writers/projection, Router, CapabilityPlanner,
  Workforce, lifecycle, prompts, verifier, or runtime execution.
- A new database, vector store, truth ledger, scorer, scheduler, replay path,
  provider call, third changed file, file deletion, or scope widening.

## Verification

```text
uv run pytest -q tests/unit/local_heal/test_memory_retrieval_adapter.py tests/unit/local_heal/test_bmf3_nexus_memory_integration.py tests/learning/test_nexus_learning_episode_contract.py
uv run ruff check nexus/services/local_heal/memory_retrieval_adapter.py tests/unit/local_heal/test_memory_retrieval_adapter.py
uv run ruff format --check nexus/services/local_heal/memory_retrieval_adapter.py tests/unit/local_heal/test_memory_retrieval_adapter.py
git diff --check
```

Audit exactly the two allowed implementation/test files and zero deletions.

## Exit

A bounded isolated Candidate diff in exactly the two allowed files with the
hostile matrix and focused checks passing. The DeepSeek worker cannot commit,
push, approve, integrate, merge, or claim runtime/release/production truth.
Publication and acceptance remain separate coordinator gates.

`AUTO_CHAIN=false`. Claim ceiling:
`canonical_episodic_memory_g2_candidate_pr_only`.

## Terminal reconciliation

G2 was independently accepted and physically merged through PR #303.

- Candidate head: `c06ba7dc160af5b0ef0a0165d39ee89a47f57af3`.
- Merge/current main: `d181a653d4a155266bf9e97fdfe35b69d3f08991`.
- Implementation-only diff SHA-256: `8a16e6595da0cd23a674305bc5a2b6502418dab4b1f27373e0128bd3769bc7d6`.
- Scope: the two declared implementation/test files, plus this card and the
  campaign INDEX; zero deletions.
- Evidence: focused `52 passed`; Ruff check and preview format check passed;
  compileall and `git diff --check` passed; required exact-head CI succeeded;
  Tier 3 was skipped by policy.
- Independent acceptance: `ACCEPT_MERGE_SLOT_ONLY` at the exact Candidate
  head before merge.

This reconciliation records only the deterministic G2 applicability source
and hostile tests. It grants no G3/G4 implementation, Router,
CapabilityPlanner, Workforce, lifecycle, provider, runtime, approval, release,
or production authority. Issue #292 remains open and `AUTO_CHAIN=false`.

Completion marker: `CANONICAL_EPISODIC_MEMORY_G2_APPLICABILITY_PROVEN`.
Claim ceiling: `canonical_episodic_memory_g2_source_and_tests_only`.
