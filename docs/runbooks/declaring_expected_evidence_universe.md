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

Read `core_universe_identity_matches` instead (#2451). The host sets it to
`true` only when `core_universe_identity` is present, equals
`coverage.universe_identity`, and also equals `core_response.hashes.universe_identity`
when Core reports one:

- `true`: the Core identities agree. This says nothing else: the generation,
  subject list, completeness and provenance are checked separately, so read
  `blocking` and `host_reason_codes` for those;
- `false`: the identities differ, or one side is missing (Core unavailable,
  no coverage). The verdict then also blocks with a host reason such as
  `CORE_COVERAGE_IDENTITY_MISMATCH` or `CORE_RESPONSE_UNIVERSE_IDENTITY_MISMATCH`;
- `null`: no universe is declared. A legacy task's receipt normally has no
  `core_verdict` at all (`null`), so check that first.

## Binding Issue promises to subjects (#2532)

A universe says *which* evidence a card expects. It does not say which
behavior the Issue promised. A generic subject such as `pytest tests/` can be
green while the real entry point of a promise never ran. Since #2532 an Issue
can name its promises and a card can map each one to the subjects that prove
it. Both blocks are optional; a card without them is byte-identical to before.

### 1. The Issue declares its promises

Put exactly one fenced block in the Issue **body**:

````
```nexus.issue_promise_set.v1
{"promise_set_generation": 1,
 "promises": [
  {"promise_id": "P1", "statement_sha256": "<sha256 of the promise sentence>",
   "phase": "PRE_MERGE", "risk": "STANDARD"},
  {"promise_id": "P2", "statement_sha256": "<…>", "phase": "POST_MERGE", "risk": "HIGH"}]}
```
````

- `phase`: `PRE_MERGE` promises are proven by host-run verifier subjects.
  `POST_MERGE` promises are proven only by a live witness (#2453); a test
  never satisfies them.
- `risk`: `HIGH` needs both the pre-merge evidence and the #2453 live witness.
- The Issue body is frozen by Core's existing `issue_contract_hash` and the
  trusted-author rule (Owner decision on #2532). Editing the promises means
  editing the body, so raise `promise_set_generation`; old evidence then reads
  as `STALE`.
- `parse_issue_promise_set(issue_body)` (`nexus/orchestrator/task_contract.py`)
  reads the block; `issue_promise_set_identity()` is its identity. A duplicate,
  unterminated or near-miss block fails closed.

### 2. The card maps every promise to subjects

Pass `issue_promises` to `nexus_task_card_create`, together with
`expected_evidence`:

```json
{"repository": "James3014/Nexus-new", "issue_number": 1234,
 "issue_contract_hash": "<Core issue_contract_hash of the Issue>",
 "expected_evidence_identity": "<expected_evidence_universe_identity(expected_evidence)>",
 "promise_set": {"promise_set_generation": 1, "promises": [ … copied from the Issue … ]},
 "map": [{"promise_id": "P1", "subject_ids": ["python -m pytest tests/test_x.py::test_real_entry"]},
         {"promise_id": "P2", "subject_ids": ["…"]}]}
```

It is written into the hashed card as one `nexus-issue-promises` block, and
the Owner authorization effect carries `issue_promises_identity`. Card
creation refuses, with no file written and no authority recorded, when:

- a promise of the set is not mapped, or the map names a promise that is not
  in the set;
- a mapped subject is not a `logical_subject_id` of this card's universe;
- `expected_evidence_identity` is not this card's universe identity;
- a promise has no `REQUIRED` / `APPLICABLE` subject;
- `issue_promises` is given without `expected_evidence`;
- the objective or verifier text smuggles a `nexus-issue-promises` block
  (including one so deeply nested that `json.loads` raises `RecursionError`).

All of these checks run before the Owner authority is checked or recorded,
so a refused card leaves no authority record either.

Workers cannot supply or change the map: `nexus_worker_candidate` rejects the
field, and only the hashed card carries it.

Map a promise to the **exact** test of its real entry point (a pytest node id),
not to the whole suite. Freeze those tests first: merge them in a RED-test PR
before the implementation PR (Owner decision on #2532). A worker-added test
is not in the frozen map, so it cannot cover a promise.

`nexus_task_card_create` cannot read the Issue, so it checks only that the map
covers the supplied set exactly. The reader checks that the supplied set is
the live one, through `live_issue` below.

### 3. Reading per-promise coverage

`nexus.orchestrator.issue_promise_coverage.project_issue_promise_coverage(
promise_block, core_verdict, expected_head, *, evidence_head, live_issue)` is
a pure function. It returns `nexus.issue_promise_coverage.v1` with one status
per promise and an `overall` of `COMPLETE`, `PARTIAL` or `BLOCKED`:

| Status | Meaning |
|---|---|
| `COVERED` | every mapped subject is satisfied and at least one REQUIRED / APPLICABLE subject was observed with `PASS` |
| `NOT_COVERED` | a mapped subject was not observed or had no `PASS`; or no verdict, no `core_status`, `integrity` other than `VALID`, unpinned Core provenance, missing coverage |
| `FAILED` | a mapped subject was observed with `FAIL`, in any coverage category |
| `STALE` | `evidence_head` ≠ `expected_head`, `core_universe_identity_matches` is not `true`, the verdict's `contract_universe_identity` is not the binding's `expected_evidence_identity`, or `live_issue` (`issue_contract_hash`, `promise_set_identity`) is missing or differs |
| `PENDING_EXTERNAL_WITNESS` | a `POST_MERGE` promise, or a `HIGH` promise whose pre-merge evidence holds; it waits for a #2453 live witness |

`overall` is `BLOCKED` for an invalid block, an `integrity` other than
`VALID`, or any `FAILED` / `STALE` promise. It is `COMPLETE` only when every
promise is `COVERED` **and** the verdict itself was accepted (`core_status`
`VERIFIED`, `integrity` `VALID`, `blocking` false). Every promise `COVERED`
under a verdict that Core failed or the host blocked is `BLOCKED`: something
outside the promises failed. Otherwise it is `PARTIAL`.
`coverage_complete`, `claimed_items` and similar flags in the verdict are
ignored; only Core coverage entries count.

#### What the reader (#2453's closer) must supply

The projection is only as fresh as its inputs. The reader must:

- compute `live_issue.issue_contract_hash` from the **live** Issue (Core's
  `issue_contract_hash` over the current title, body, state and author), and
  `live_issue.promise_set_identity` with
  `issue_promise_set_identity(parse_issue_promise_set(<live Issue body>))`.
  Never take either from the card or the binding: that would compare the
  card with itself;
- take `evidence_head` from the receipt that holds the `core_verdict` (the
  Candidate commit it verified), never echo `expected_head`;
- pass `expected_head` as the exact PR head it is about to act on;
- pass `promise_block` from the committed card
  (`parse_task_card_issue_promises` on the hashed card text), not from a tool
  argument.

The result grants nothing: it has no approve, merge or close field, and
`claim_ceiling` is `ISSUE_PROMISE_COVERAGE_PROJECTION_ONLY`. #2453's closer,
not this function and not `issue_closure_guard`, decides what an incomplete
result blocks.

### 4. Live witnesses and the confirmer report (#2453)

`nexus.services.promise_confirmation.build_promise_confirmation_report` (CLI:
`scripts/governance/promise_confirmation.py --issue N --pr M [--author-session NAME]`,
read-only, `--offline-input FILE.json` for no network) builds a per-promise table
(`WITNESSED`, `UNCOVERED`, `FAILED`, `STALE`) and a `recommendation`
(`NOT_APPLICABLE`, `BLOCKED`, `LIVE_FAILED`, `PROVISIONAL`, `VERIFIED`). Claim
ceiling `PROMISE_CONFIRMATION_INPUT_ONLY`: it grants nothing.

- Issue body: an optional `nexus.issue_promise_statements.v1` fence holds
  `{"statements": [{promise_id, statement, observe, entry, counterexample}]}`;
  `sha256(canonical JSON of each statement)` must equal the promise's
  `statement_sha256`. `--emit-blocks statements.json --generation G` prints both
  fences plus a witness template per promise.
- Witness comment (whoever ran the real entry): `<!-- NEXUS_PROMISE_WITNESS_V1`
  + one JSON object + `NEXUS_PROMISE_WITNESS_V1 -->` with promise_id,
  promise_set_identity, phase, pr, commit, entry (must equal the statement's
  entry), result, observed_at, by, evidence. A post-merge witness must be on a
  commit containing every listed merge commit and observed after the merge.
- A later `ACTUAL_FAILED` is only superseded by a valid PASS on a commit that
  contains a PR merged after the failure.
- Confirmation comment (independent confirmer): `NEXUS_PROMISE_CONFIRMATION_V1`
  with promise_set_identity, commit, confirmer and per-promise verdicts. The
  confirmer's verdict is ignored when its name equals a witness `by`, the Issue
  or PR author, or an `--author-session`; this is a text-level check only.

### Fail-to-pass and missing test ids

If a verifier names a pytest node id that does not exist on base, pytest
exits 4. The fail-to-pass probe treats exit 4 and 5 as
`BASE_NOT_PHYSICAL_FAIL` / `base_collected_no_tests`, not as a real base
failure (#2387; the missing-node case is pinned by
`test_repair_task_whose_base_lacks_the_named_test_node_is_not_verified`).
So a promise test must already exist, and fail, on base. Merging the
RED tests first gives exactly that.

RED tests cannot land as `xfail` or `skip`: the exact-base impact gate counts
an added test that does not pass as `IMPACT_UNKNOWN`. #2532's RED PR therefore
gates each RED class with `__test__ = _RED_<issue>` (collected only when
`NEXUS_RED_<issue>=1`) and pins the file with a source hash; the
implementation PR deletes only the gate lines. A verifier that must see the
RED tests on base sets the variable, e.g.
`NEXUS_RED_2532=1 python -m pytest tests/…::test_x`.
