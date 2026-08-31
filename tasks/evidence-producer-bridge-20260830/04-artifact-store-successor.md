# TASK-EPB-001-R2 — ArtifactStore CAS Containment Successor

task_id: `TASK-EPB-001-R2`

- **Campaign:** `CAMPAIGN-EVIDENCE-PRODUCER-BRIDGE-01`
- **Status:** `ACTIVE`
- **Source spec:** `none`
- **Source spec SHA-256:** `none`
- **Source groups:** Owner Boundary-E successor repair
- **Requirements:** `REQ-EPB-R2-001`
- **Acceptance:** `AC-EPB-R2-001; AC-EPB-R2-002; AC-EPB-R2-003`
- **Auto-chain:** `false`
- **Maximum claim:** ArtifactStore successor independently accepted with race-safe CAS containment; no adoption, approval, integration, merge, Task4, release, production, or public claim.
- **Depends on:** `none`
- **Dependency unlock evidence:** Explicit Owner authorization to preserve `b3343c95479f03857af7761381a1b839ac049e24` as historical `REJECTED/SUPERSEDED` evidence and create one two-file successor.
- **Task type:** `IMPLEMENTATION`
- **Slicing strategy:** `TRACER_BULLET`
- **Scope class:** `small`
- **Execution lane:** `NEXUS_LIFECYCLE_V2`
- **Minimum MCP profile:** `CANDIDATE`
- **Commit required:** `true`
- **Candidate required:** `true`
- **Parallel safe:** `false`
- **Supersedes:** `TASK-EPB-001-R1`

## Goal

Create exactly one successor on immutable `b3343c954...` that closes the
physically proven ArtifactStore root/component symlink and descriptor TOCTOU
defect without changing any other EPB behavior or authority semantics.

## Observable outcome

CAS operations remain bound to one physically opened directory; root,
ancestor, post-construction, and final-object substitution cannot redirect
`put/read`, while the existing prospective EPB witness remains trusted.

## Non-goals

No amendment/rewrite of the original Candidate. No Task4, Product, trust-root,
certification, lifecycle, Gateway, approval, integration, merge, push, release,
production, or public-claim work.

## Source lineage

| Source ID | Role in this card | Preserved constraint |
|---|---|---|
| `DEC-EPB-R2-001` | Owner Boundary-E decision | Original remains immutable historical evidence; one successor only |
| `DEF-EPB-R2-001` | Physical counterexample | Root symlink redirects current CAS writes outside |
| `REQ-EPB-R2-001` | Repair contract | Descriptor-bind root, components, and objects; fail closed on substitution |
| `AC-EPB-R2-001` | Containment witness | Root/ancestor/final/post-init substitutions cannot redirect I/O |
| `AC-EPB-R2-002` | Immutability witness | Colliding/concurrent objects remain complete and content-addressed |
| `AC-EPB-R2-003` | Regression witness | EPB producer/verifier/Product Task3 suite remains green |

## Owner decisions

- Original commit/tree/diff remain unchanged and receive no inherited acceptance.
- Exactly one successor is allowed, limited to the two paths below.
- Successor requires fresh commit/tree/diff/validation/independent acceptance.

## Source and start state

- **Workspace/root:** `/private/tmp/nexus-epb-artifact-store-successor`
- **Branch:** `codex/evidence-producer-bridge-r2`
- **Starting HEAD:** `b3343c95479f03857af7761381a1b839ac049e24`
- **Dirty baseline:** clean before RED commit
- **Required initial verification:** exact root/branch/HEAD/tree/status and `uv run` 289-test baseline
- **Freshness rule:** re-read after reconnect, commit, status, executable, or test movement

## MCP execution profile

- **App/server and action snapshot:** isolated successor worktree; no public runtime action required for implementation
- **Exact required actions:** bounded edit, exact verify, scoped commit, independent acceptance
- **Confirmation-required actions:** scoped Candidate commit only; already Owner-authorized
- **Idempotency and attempt rule:** one successor Task ID; rejected attempts remain negative evidence
- **Reconnect reconciliation:** exact two-file diff, HEAD/tree/status, processes, and test evidence
- **Transport blocker:** none

## Authority map

- **Selection authority:** Primary Controller under explicit Owner Boundary-E authorization
- **Execution authority:** one bounded Luna worker
- **Verification authority:** physical filesystem controls and frozen Card commands
- **Receipt authority:** fresh successor validation and independent acceptance only
- **Approval/integration authority:** none

## Allowed scope

- **Read:** `AGENTS.md; tasks/evidence-producer-bridge-20260830/01-evidence-producer-bridge-r1.md; tasks/evidence-producer-bridge-20260830/04-artifact-store-successor.md; nexus/evidence/artifact_store.py; tests/nexus/evidence/test_producer_bridge.py; nexus/orchestrator/self_hosted_task_service.py`
- **Edit:** `nexus/evidence/artifact_store.py; tests/nexus/evidence/test_producer_bridge.py`
- **Create:** `none`
- **Delete:** `none`
- **Maximum touched production files:** `1`
- **Maximum touched test files:** `1`

## Unknown scan

- **Known facts:** root resolution follows symlinks; path-level checks are TOCTOU-prone; descriptor-safe patterns already exist.
- **Assumptions requiring verification:** supported POSIX environment provides `dir_fd`, `O_DIRECTORY`, and `O_NOFOLLOW`.
- **Architecture risks:** descriptor leaks, partial objects, idempotency loss, exception-contract drift.
- **Evidence risks:** leaf-only or mocked tests that miss physical outside writes.
- **Missing owner decision:** `none`

## Mandatory source audit

Inspect all ArtifactStore callers; preserve digest format, size limit, identical
put, `ValueError` failures, deterministic readback, and evidence-layer isolation.

## Start-state classification

`DEFECT_REPRODUCED`

## RED or existing-guard proof

Before production edits, physical tests must fail for root symlink and ancestor
symlink because outside writes occur. Final-leaf, collision, concurrent, and
post-construction controls must execute behavior rather than inspect symbols.

## Implementation constraints

- Walk root/components with directory descriptors and `O_NOFOLLOW`.
- Use `dir_fd` for create/open/unlink and require regular files with `fstat`.
- New objects use `O_CREAT | O_EXCL | O_NOFOLLOW`; identical existing bytes are idempotent.
- `fsync(file)` and `fsync(root directory)` precede success.
- Preserve public API, digest, size, and `ValueError` semantics.
- No string-path I/O fallback after descriptor binding.

## GREEN and regression gates

- `AC-EPB-R2-001`: outside directories remain untouched for every substitution.
- `AC-EPB-R2-002`: wrong bytes/symlinks fail; concurrent identical puts leave one complete object.
- `AC-EPB-R2-003`: the exact baseline suite plus new hostile tests passes.

## Mandatory command manifest

| ID | cwd | Exact command/argv | Purpose | Required result |
|---|---|---|---|---|
| `CMD-001` | successor root | `uv run pytest -q tests/nexus/evidence/test_producer_bridge.py tests/nexus/orchestrator/test_candidate_verifier.py tests/product/test_trusted_evidence_ingestion.py` | EPB regression/hostile verification | `289 baseline tests plus new controls PASS` |
| `CMD-002` | successor root | `uv run ruff check nexus/evidence/artifact_store.py tests/nexus/evidence/test_producer_bridge.py` | Static lint | `PASS` |
| `CMD-003` | successor root | `uv run pyright nexus/evidence/artifact_store.py` | Type verification | `PASS` |
| `CMD-004` | successor root | `git diff --check` | Patch integrity | `PASS` |

## Physical evidence

RED/GREEN node identities, outside-directory assertions, exact two-path diff,
no deletion/mode change, successor commit/tree/diff, commands, and clean status.

## Independent review

A distinct reviewer must rerun all physical substitution/concurrency controls,
inspect descriptor lifecycle and error normalization, audit the two-path diff,
and return `ACCEPT_CANDIDATE` or an exact counterexample. No downstream action.

## Exit conditions

- **PASS:** one exact two-file successor passes all commands and hostile controls and receives fresh independent `ACCEPT_CANDIDATE`.
- **BLOCK:** outside write, symlink acceptance, race/partial object, descriptor leak, API drift, extra path, or inherited acceptance.
- **Residual debt:** one-shot adoption/host reload, approval/integration, remote merge, and post-merge verification.
- **Next gate:** fresh successor validation and independent acceptance; informational only.

`AUTO_CHAIN=false`
