---
artifact_authority: current
owner: James Chen
status: ACTIVE_LIVE_ACCEPTANCE
task_id: agy-card01-live-dispatch-acceptance
campaign_id: agy-account-pool-runtime
verifies:
  - agy-account-pool-real-manager-runtime-closure
  - agy-gateway-executable-authority-convergence
depends_on_evidence:
  - 7705c27e5529127a9bd4e61f041972ee0e8ca4e8
  - a5e7e5272785f405d7a4575d3d31f731558e2d25
  - b8973e2e4c39953b22ad12c1a14106139de82558
  - 45c01ba1bbf9958f3b512db81e2edfe4635b027c
commit_required: false
candidate_required: false
worker_may_commit: false
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false
---

# Task Card: AGY Card 01 Live Dispatch Acceptance

## Objective

Prove that the persistent Nexus Gateway can use the installed AGY account-pool
runtime to send one explicitly authorized bounded source-code slice to AGY in an
isolated Target, receive a schema-valid non-mutating summary, preserve credential
and account privacy, and leave the canonical repository unchanged.

This card verifies Cards 01 and 02. It does not implement or modify their
production behavior.

## Owner decision

The Owner explicitly authorizes sending:

`nexus/executors/worker_registry.py`

to AGY only for this bounded live acceptance.

The authorization does not include other files, Git history, credentials,
environment dumps, raw manager output, lifecycle archives, or unrelated context.

## Execution contract

- execution lane: `ISOLATED_TARGET`
- worker: `agy`
- resolved model: `gemini-3.6-flash-high`
- apply: `false`
- mutation intent: `none`
- maximum provider calls: `3`
- rotation: auth/quota failures only
- maximum rotations: `2`
- generic failure retry: forbidden
- timeout retry: forbidden
- commit: forbidden
- merge: forbidden
- push: forbidden
- canonical mutation: forbidden

## Allowed source input

- `nexus/executors/worker_registry.py`

No other repository file may be included in the AGY context.

## Required preflight

Before provider invocation:

1. Verify canonical HEAD and clean working tree.
2. Verify Gateway health and current tools manifest.
3. Verify AGY executable identity.
4. Verify account pool is enabled only for AGY.
5. Run a bounded secret/privacy scan over the exact allowed source file.
6. Run manager `ensure-active` through the existing production seam.
7. Record only the redacted active account alias hash and isolated HOME hash.
8. Verify the task ID has never previously existed.

Any failed preflight produces zero provider calls.

## Provider task

Ask AGY to return a structured architectural summary only.

AGY must not:

- edit the file;
- generate a patch;
- reproduce substantial verbatim source;
- request additional files;
- inspect Git history;
- expose environment or credential data;
- claim completion, integration, production readiness, or approval.

Expected logical output:

```json
{
  "summary": "bounded description",
  "key_responsibilities": ["..."],
  "safety_observations": ["..."],
  "mutation_requested": false
}
```

The current provider adapter may wrap this object in its established envelope,
but the final decoded result must validate against the required schema.

## Required live evidence

Receipt must record:

* task ID and unique attempt ID;
* Task Card path and hash;
* controller HEAD;
* Gateway instance identity;
* tools manifest revision;
* AGY executable hash/version;
* manager executable hash/version;
* redacted account alias hash;
* isolated HOME hash;
* provider attempt count;
* rotation count;
* exit code;
* stdout/stderr hashes, not raw content;
* decoded schema-validation result;
* allowed-source SHA-256;
* canonical HEAD/status before and after;
* Target cleanup result;
* credentials exposed: `false`.

## Account binding

At dispatch start, record the alias returned by the production manager
`ensure-active` path.

The provider receipt account alias must equal that preflight alias.

Where the prior Account A receipt is available, additionally prove that the
current Account B alias differs from Account A. Do not copy either raw account
identity into this card or receipt.

## Pass conditions

All must be true:

* exact Task Card identity accepted;
* exact one-file scope preserved;
* provider process started;
* provider exit code is zero;
* decoded output is schema-valid;
* `mutation_requested` is false;
* provider receipt alias equals manager preflight alias;
* no credential, raw HOME or account identity exposure;
* no canonical file, HEAD or working-tree change;
* isolated Target cleanup complete;
* no commit, merge or push.

## Block conditions

Return `RECOVERABLE_BLOCK` for:

* external provider unavailable;
* natural auth/quota exhaustion after bounded rotation;
* transient Gateway transport failure;
* schema-invalid provider output.

Return `HARD_BLOCK` for:

* contract identity collision;
* extra source file included;
* privacy/credential leakage;
* canonical mutation;
* account alias mismatch;
* route-authority change.
