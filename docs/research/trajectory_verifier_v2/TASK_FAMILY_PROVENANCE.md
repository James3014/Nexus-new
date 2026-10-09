# Track 1 task-family provenance (issuer-declared, pre-action)

Scope: Nexus #1677 / #1197, research-only trajectory-readiness projection. This
document describes **derived evidence**, not a lifecycle, routing, Workforce,
verifier, acceptance, merge or deployment authority. `AUTO_CHAIN=false`.

## Producer and freeze point

The **Task Card issuer**, acting through the already governed task-creation
authority, chooses one meaningful family for a *new* task before the first
provider/action effect. The existing Git-tracked Task Card is the single
producer. Its pre-execution Git revision and SHA-256 are already retained in
the canonical lifecycle task state; the existing collected candidate row also
binds the original contract's SHA-256.

In that Task Card, add this exact section **before** it is issued/committed or
the task starts. Omit it when the issuer cannot confidently classify a task.
The lines must occur once, inside the section, as plain Markdown:

```text
## Track 1 task-family declaration (issuer, pre-action)
track1_taxonomy: TRACK1_ENGINEERING_V1
track1_family: defect_repair
track1_family_rationale: Correct an existing behavioral defect without adding a feature
```

These optional research annotations do not alter the Task Card's lifecycle
schema, contract hash algorithm, protected-approval rules or worker inputs.
The Task Card issuer is responsible for a truthful category and specific
rationale; research consumers **must not infer a missing label** from task
IDs, filenames, branches, provider/model, post-hoc success/failure or a model
prediction.

## Frozen family vocabulary: TRACK1_ENGINEERING_V1

| Family | Issuer's decision rule |
| --- | --- |
| `defect_repair` | Restore behavior that already should work, after a demonstrated defect. |
| `feature_extension` | Introduce a previously absent product capability or behavior. |
| `test_oracle` | Correct/add tests, verifier oracles, assertion quality or test evidence without making the product feature change itself. |
| `runtime_recovery` | Repair runtime restart, deployment, transport, persistence/recovery or operational continuity. |
| `evidence_integrity` | Repair evidence identity, provenance, tamper/replay defense, and claim-boundary integrity. |
| `architecture_maintenance` | Behavior-preserving architectural maintenance, refactor or code-structure improvements. |

This taxonomy is for **research grouping**, not the Product/Planner route or
Workforce action class. Ambiguous, mixed or unidentified tasks must remain
`UNKNOWN` for research counting. New categories require an explicit reviewed
taxonomy revision, not silent additions to the current vocabulary.

## Consumer/readback contract

The existing `refresh_registered_experiment` reads only an already-persisted,
trusted canonical state entry, its immutable original contract identity, the
recorded Task Card SHA-256, and the Task Card bytes at the recorded Git revision.
It verifies all of the following before counting a family:

- exact task and attempt identity; verifier-backed eligible candidate row hash
  and contract identity;
- pre-action state submission preceding the outcome binding;
- normalized repository-relative `tasks/.../*.md` path, or an absolute
  Task Card path anchored to the original contract's `controller_repo_root`;
  exact 40-character Git source revision and exact Git-object bytes matching
  the *saved* Task Card hash;
- single issuer section with one taxonomy value, one allowed family and a
  nonempty specific rationale; no duplicate declaration.

Invalid, legacy, retrofitted, conflicted or absent declarations simply do not
count. Existing old trajectory evidence is never modified; reading an older
Task Card *at the task's original revision* prevents a later working-tree edit
from relabeling it.

The derived readiness snapshot retains a `task_family_provenance` readback
per verified task (Task Card/contract hash, source revision and selected family)
and a deterministic **structural** family-disjoint split witness with disjoint
task lists and observed PASS/FAIL counts on **both** train and dev. When no
family-disjoint partition has both labels on each side, readiness remains
`WAITING_FOR_DATA` even if five distinct family names are present. The witness
does not attest to the eventual statistically defensible split, sealed holdout
near-duplicate independence or training eligibility; fresh Wave 2 / T0-T1
scientific adjudication remains the owner of those claims.

Only a natural corpus meeting the existing five-family, strong-verifier
PASS+FAIL, dedup, leakage and holdout gates may reach
`READY_TO_REAUDIT / T0_T1_REAUDIT_ONLY`. No automatic Wave 2, Wave 3, training,
route changes, production activation or retrospective labeling.

## Operational limits

- This fix **does not automatically author** a family tag for a new Task Card:
  the authorized Task Card issuer must deliberately supply the research
  section before execution. No new classification authority is inserted into
  `SelfHostedTaskContract` or the running Nexus Gateway.
- Existing historical tasks without a valid pre-action declaration, including
  three current natural FAIL trajectories, remain unclassified.
- The canonical state and historical Git objects must remain readable to
  reproduce the provenance. Missing/archived state or an unavailable original
  Git object is a fail-closed provenance gap, never a mapping fallback.
- The rollout is research-only until current-main code, tests, independent
  checks, protected integration and the required physical runtime readback
  establish what is actually deployed.

Validation: `python3 -m pytest -q tests/research/test_trajectory_continuity.py`
with positive and adversarial pre-effect/retrofit/tamper/holdout controls.
