---
task_id: github-issue-292-canonical-episodic-memory-g1-20260815
issue: 292
repository: James3014/Nexus-new
baseline_revision: cdf2570ede5ae218f36f886b696c8da45458043a
status: ACTIVE
readiness_marker: CANONICAL_EPISODIC_MEMORY_G1_SOURCE_FROZEN
AUTO_CHAIN: false
claim_ceiling: canonical_episodic_memory_g1_candidate_pr_only
implementation_files:
  - nexus/services/local_heal/memory_retrieval_adapter.py
  - tests/unit/local_heal/test_memory_retrieval_adapter.py
governance_files:
  - tasks/github-issue-292-canonical-episodic-memory-20260815/INDEX.md
  - tasks/github-issue-292-canonical-episodic-memory-20260815/github-issue-292-canonical-episodic-memory-g1-20260815.md
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
  admission_binding_hash: c2320e887be82dbdac9c10c20bfb07ac048732f7a83d55d8123dbfd255e5cda5
  admission_aggregate_hash: fecaa4a90f5bf587b6bd2d85dd8c539ff45dde303eab0d58d776b527a1bb1524
---

# Issue #292 G1 — retrieve canonical cross-task LearningEpisodes

## Objective

Generate one bounded Candidate that adds the canonical
`.nexus/memory/learning_episodes.jsonl` ledger as a validated input to the
existing `MemoryRetrievalAdapter`. This is retrieval-only G1; it creates no new
store, writer, route, planner, scoring authority, or automatic replay.

## Frozen source finding

The repository already owns canonical LearningEpisode identity, validation,
append, and load primitives under `nexus.learning`. The local-heal memory
adapter currently reads the legacy learning-closure JSONL, FindingsMemory, and
MemoryRepository sources, but does not expose the canonical LearningEpisode
ledger as a first-class retrieval source. The smallest seam is therefore the
existing adapter plus one new focused test module.

## Required behavior

- The adapter reads canonical `nexus.learning_episode.v1` records through the
  existing canonical path/validation primitives rather than inventing a
  parallel parser or store.
- Valid cross-task episodes with terminal provenance can become
  `RetrievedLesson` values through the existing adapter and metadata surface.
- Missing, malformed, wrong-schema, identity-mismatched, provenance-free, or
  non-terminal records fail closed and are not returned.
- The same task/attempt must not be treated as cross-task prior experience when
  a caller supplies its task identity.
- Duplicate episodes remain deterministically deduplicated; repeated retrieval
  is deterministic and read-only.
- Existing legacy learning-closure, FindingsMemory, and MemoryRepository
  behavior and fail-open source isolation remain compatible.
- `auto_replay_allowed` remains false; retrieval never performs mutation.

## Forbidden

- Changes to LearningEpisode writers/contracts, Router, CapabilityPlanner,
  Workforce, lifecycle, runtime execution, prompts, verifier, or scoring
  authority.
- A new database/vector store/truth ledger, learned scheduler, or automatic
  replay path.
- G2–G4 implementation, file deletion, or scope widening.

## Verification

```text
uv run pytest -q tests/unit/local_heal/test_memory_retrieval_adapter.py tests/unit/local_heal/test_bmf3_nexus_memory_integration.py tests/learning/test_learning_closure_effectiveness.py tests/learning/test_nexus_learning_episode_contract.py
git diff --check
```

Hostile witnesses must cover valid cross-task retrieval, same-task exclusion,
wrong schema, malformed identity, missing provenance, non-terminal evidence,
deduplication, deterministic repeated reads, and legacy-store compatibility.
Audit exactly the two allowed files and zero deletions.

## Exit

A bounded isolated Candidate diff in exactly the two allowed files with all
focused tests passing. The DeepSeek worker cannot commit, push, approve,
integrate, merge, or claim runtime/release/production truth. Publication and
acceptance remain separate coordinator gates.

`AUTO_CHAIN=false`. Claim ceiling:
`canonical_episodic_memory_g1_candidate_pr_only`.
