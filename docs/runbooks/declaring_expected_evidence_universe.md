# Declaring an expected evidence universe on a Task Card

Status: current (2026-10-15, #2218). Applies to `nexus_task_card_create` on the
unified MCP Gateway.

## What it does

An expected evidence universe lists the evidence a task must produce before its
candidate may be committed. Nexus reads it only from one fenced
`nexus-expected-evidence` block inside the hashed Task Card (#2181). A task
whose card declares a universe is checked by the pinned Core: if coverage is
incomplete or a covered verifier fails, the candidate commit is blocked. A card
without a universe behaves as before and claims no coverage.

Complete coverage grants nothing beyond that check. It is not an approval,
merge or release decision.

## How to declare one

Pass the optional `expected_evidence` argument to `nexus_task_card_create`:

```json
{
  "owner_confirmation": true,
  "campaign_id": "readme-fix",
  "task_id": "readme-fix",
  "objective": "Fix the typo in README.md.",
  "allowed_files": ["README.md"],
  "verifier_commands": ["git diff --check"],
  "authority_goal_id": "<goal>",
  "authority_coordination_scope_id": "<scope>",
  "expected_evidence": {
    "universe_generation": 1,
    "subjects": [
      {
        "logical_subject_id": "git diff --check",
        "evidence_kind": "verifier-run",
        "requirement_mode": "REQUIRED",
        "applicability": "APPLICABLE"
      }
    ]
  }
}
```

The Gateway validates the argument with the same `ExpectedEvidenceUniverse`
model that reads the card (`nexus/orchestrator/task_contract.py`). It rejects:

- a duplicated `logical_subject_id`;
- an unknown field, at the top level or in a subject;
- an unknown `requirement_mode` or `applicability`, or a blank `evidence_kind`;
- `REQUIRED` without `APPLICABLE`, or `NOT_APPLICABLE` without `NOT_APPLICABLE`;
- a `universe_generation` that is not an integer of 0 or more, or an empty
  subject list;
- an objective or verifier command that itself contains a
  `nexus-expected-evidence` fence.

A rejected call writes nothing. A valid universe is written as one compact,
sorted JSON block under `## Expected evidence`, so `card_hash` covers it, and
the card reads back as the identical universe and Core universe identity.
Without the argument the card is byte-identical to a card created before #2218.

Only `nexus_task_card_create` (the Owner-confirmed card creator) accepts a
universe. Worker-facing tools such as `nexus_worker_candidate` reject
`expected_evidence` and `core_envelope_required` as unknown fields.

## Rules that make a universe pass today

These follow from the current matching rules on the self-hosted path:

1. **A subject id must equal a verifier command.** A verifier's result counts
   for a subject only when `logical_subject_id` is the exact verifier command
   string listed in `verifier_commands` (for example `git diff --check`). The
   `evidence_kind` you declare is copied onto that observation.
2. **List exact file paths in `allowed_files`.** Use full relative file paths,
   not directories or globs, for a task with a universe.
3. **Do not declare a namespaced subject as `REQUIRED`.** A subject such as
   `review:security` or `lint:ruff` has no producer on the self-hosted path,
   so as `REQUIRED` it always ends `NOT_COVERED` and blocks the task. Declare
   such subjects `CONDITIONALLY_REQUIRED` with `NOT_APPLICABLE`, or leave them
   out, until a producer exists.

## Checking the result

After the task runs, the durable receipt
(`<state dir>/<task_id>.json`, `verified_receipt.core_verdict`) holds the
coverage entries, `blocking`, `coverage_complete` and `core_provenance`. A
`core_provenance.status` of `CORE_REVISION_PINNED` means the verdict came from
the pinned Core revision.

### Which universe identity to compare

The verdict (`verified_receipt.core_verdict`, and
`terminal_core_record.core_verdict` for a declared task that ended without a
Candidate, #2355) carries two identities with similar names. They use
different formulas:

| Field | Formula | Compare with |
| --- | --- | --- |
| `core_universe_identity` | the card universe under Core's `expected_universe_identity()` | `coverage.universe_identity` (must be equal) |
| `contract_universe_identity` | the Nexus contract hash of the same declaration (`SelfHostedTaskContract.universe_identity`, also called `expected_evidence_identity`) | nothing from Core |

`contract_universe_identity` always differs from `coverage.universe_identity`
**by design**. That difference is not a mismatch. Never block or keep an Issue
open because of it.

Read `core_universe_identity_matches` instead (#2451). The host computes it as
`core_universe_identity == coverage.universe_identity`:

- `true`: Core's coverage is bound to exactly the declared universe;
- `false`: the identities differ, or one side is missing (Core unavailable,
  no coverage). The verdict then also blocks with a host reason such as
  `CORE_COVERAGE_IDENTITY_MISMATCH`;
- `null`: a legacy task with no declared universe.
