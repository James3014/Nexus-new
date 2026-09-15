# Learning Consumer Cutover

## Canonical authority

Canonical Learning implementation authority is `James3014/nexus-learning`.
The G8 consumer identity pinned by this repository is:

`3b8ece75fac4d2554245c29590748a84c5c671d5`

Nexus-new remains a legacy integration host. The migrated canonical Learning modules under `nexus/` are compatibility facades only and must not contain a separately evolving fallback implementation.

## Package boundary

`nexus-learning` requires Python >=3.11. Nexus-new retains historical Python 3.10 compatibility for legacy-only profiles; G8 does not lower the canonical package requirement or claim that Python 3.10 can import it.

The exact canonical package source is recorded in `requirements/canonical-learning.txt`. CI and supported canonical-Learning consumer profiles install that manifest in addition to the frozen legacy environment.

The root `pyproject.toml` and `uv.lock` remain unchanged because the trusted dependency contract protects them from unrelated dependency drift. This external package boundary is therefore deliberate, not an untracked install.

If the canonical package is unavailable, migrated legacy facades fail closed. They do not fall back to the old implementation.

## Forwarding facades

The following legacy paths forward to canonical modules:

- `nexus.contracts.learning_experience` -> `nexus_learning.contracts`
- `nexus.learning.outcome_memory` -> `nexus_learning.outcome_memory`
- `nexus.learning.learning_episode_projection` -> `nexus_learning.episode_projection`
- `nexus.learning.learning_closure_effectiveness` -> `nexus_learning.closure_effectiveness`

LAB_ONLY modules not represented in the canonical package remain in Nexus-new and are not promoted to canonical authority by this cutover.

## State ownership

For a given project `.nexus` state tree, canonical `nexus_learning` is the single writer for migrated Learning capabilities. Active Nexus-new write consumers must pass an explicit project/workspace root. Process cwd is not state authority.

The cutover acceptance test executes from a cwd different from the project root, performs a canonical write twice with the same idempotency key, and requires exactly one outcome record under the explicit project root and no `.nexus` tree under cwd.

## Authority boundary

Learning outputs remain advisory/evidence-bounded. This cutover grants no route selection, worker/model selection, Workforce admission, Candidate acceptance, merge, release, deploy, or production authority.

## G8 claim ceiling

When package provenance, forwarding identity, state-root/idempotency tests, affected regression tests, and main CI all pass, this sub-gate may claim:

`LEARNING_DOWNSTREAM_CONSUMER_CUTOVER_VERIFIED`

It does not authorize legacy file deletion; G9 is separate.
