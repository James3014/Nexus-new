# Issue #117 — GB-079 CONTINUITY_REPLAY_PROBE contract

- artifact_authority: `current`
- owner: James Chen
- task_id: `github-issue-117-gb079-continuity-replay-probe`
- status: `task_card_compiled_implementation_not_authorized`
- purpose: Freeze Issue #117 GB-079 CONTINUITY_REPLAY_PROBE contract without implementing the probe.
- issue: `#117`
- finding: `GBF-004 / GB-079`
- continuity_owner: `Issue #31 / PR #245`
- continuity_owner_merge: `5853073a29cab5600187c9fa03728c8ee61ebe0a`
- baseline_main: `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`
- allowed_files:
  - `tasks/github-issue-117-golden-findings-probes-20260816/INDEX.md`
  - `tasks/github-issue-117-golden-findings-probes-20260816/00-gb079-continuity-replay-probe.md`
- max_files: `2`
- auto_chain: `false`
- claim_ceiling: `probe_contract_and_evidence_only`

## Objective

Compile the frozen contract for an executable continuity replay probe that
consumes Issue #31's physically merged evidence only. The probe proves that a
canonical task snapshot plus its tail events replays exactly to the full
projection without protected-field loss, and fails closed on stale,
substituted, cross-task, cross-attempt, or tampered inputs.

This card does not implement the probe and does not change finding status.

## Consumed owner evidence (Issue #31 / PR #245, merged)

- `nexus/core/task_continuity.py`: `ContinuityEvent`, `ContinuitySnapshot`,
  `ResumeContext`, `project()`, `resume()`, `_project_tail()`,
  `events_from_attempt_records()`, `_validate_chain()`,
  `snapshot_hash`, `validate_integrity()`.
- `nexus/events/contracts.py`: `AttemptTransitionEvent`, `REJECTED_STATES`,
  bounded collection ceiling.
- `nexus/orchestrator/self_hosted_task_service.py`: canonical attempt-event
  seam producing the records consumed by `events_from_attempt_records()`.

The merged PR #245 merge commit `5853073a29cab5600187c9fa03728c8ee61ebe0a`
is an ancestor of current main `46e21858d3a3d8ba1c0cb377fbaa61aa2ed45f3c`.

## Probe inputs and outputs

Inputs:

- a real canonical attempt-event stream (JSONL records) for one task and one
  attempt;
- a verified `ContinuitySnapshot` produced from the leading events;
- an optional tail event list;
- current source/contract revisions and the expected snapshot hash.

Outputs (fail-closed):

- `(bool, detail)` where detail names the bound task/attempt identity, chain
  root, source/contract revision, protected-field projection, and replay
  equality result.

## Frozen semantics

1. `replay == snapshot + tail`: `resume(snapshot, tail)` merged snapshot must
   equal `project(events_from_attempt_records(full stream))`, including
   `event_root`, `last_sequence`, and `snapshot_hash`; empty tail merges to the
   snapshot exactly.
2. Protected fields 0 loss: `do_not_repeat`/`rejected_strategies`,
   `evidence_refs`, `unresolved_risks`, `unknowns`, `next_action`,
   `claim_ceiling`, and `failure_reason` survive append/read/projection/resume
   with zero loss; `ATTEMPT_REJECTED` never collapses to
   `OBSERVATION_RECORDED`.
3. Stale: snapshot or tail revision mismatch with current source/contract
   fails closed.
4. Substituted: tail that does not extend the snapshot (`previous_hash` or
   sequence mismatch) or carries drifted revisions fails closed.
5. Cross-task/cross-attempt: foreign task/attempt events fail closed.
6. Tamper: altered protected fields, snapshot content, record digest, or
   record parent chain fail closed; sequence gaps and empty streams fail
   closed.
7. A passing probe is revision-bound and cannot by itself convert a corpus
   finding to covered; conversion requires separate reconciliation using new
   authority/source/test/Issue evidence.

## Future implementation scope (not authorized by this card)

Candidate files only, to be frozen at implementation time against then-current
main and open-PR overlap:

- `nexus/learning/learning_coverage_probes.py` (register the probe in the
  existing `PROBES` interface of `scripts/ops/run_golden_behavior_eval.py`);
- focused probe tests in `tests/learning/` (positive plus stale/substituted/
  cross-task/cross-attempt/tamper negatives);
- this card and `INDEX.md`; 0 deletions; max files 4.

Forbidden future scope: `tests/golden_behavior/corpus.py`,
`tests/golden_behavior/test_corpus.py`, PR #228 surface, any second evaluator
runner, any second continuity/lifecycle authority, and any change to
`nexus/core/task_continuity.py`, `nexus/events/contracts.py`, or the
self-hosted task service seam (consume only).

## Other findings

- GB-077 / GBF-002: blocked on Issue #12 runtime identity evidence.
- GB-078 / GBF-003: blocked on Issue #29 lawful live Local-to-Online evidence.
- GB-080 / GBF-005: blocked on Issue #49 post-#29 final-delivery verdict.

## Exit

This card exits only as `TASK_CARD_COMPILED_IMPLEMENTATION_NOT_AUTHORIZED`.
After the card is independently accepted and the blocked owner evidence
surfaces are settled, the primary coordinator must create a fresh
Owner-authorized implementation frontier with exact current blobs, files,
tests, overlap, and claim ceiling. This card cannot authorize that mutation.

## Block class

`RECOVERABLE_BLOCK — PENDING_INDEPENDENT_ACCEPTANCE_AND_OWNER_EVIDENCE`
