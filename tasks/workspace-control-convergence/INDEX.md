# Campaign Index: Workspace Control Convergence

artifact_authority: current
owner: James Chen
status: active_p6_owner_approved
source_specification: owner-authorized conversation on 2026-07-31
AUTO_CHAIN: false

## Campaign Overview
Converge Nexus workspace authority onto the clean integration controller and add one reusable, fail-closed execution slot without deleting evidence, rewriting history, or granting workers integration authority. P1-P5 and P7 implementation evidence is on `nexus/integration/main`; terminal lifecycle receipts are now archived through the formal archive API. On 2026-08-01 the owner explicitly approved worktree reconciliation, required valuable changes to be integrated, required redundant worktrees to be removed, and required `/Users/jameschen/Workspace/nexus` to become the sole daily entrypoint.

## Live Authority Reconciliation (2026-07-31)

- Controller: `/Users/jameschen/Workspace/nexus-worktrees/integration-main`, branch `nexus/integration/main`, HEAD `ba1fe9b6d59d9e47600d9a06babdd2f5a06a9fad`.
- Canonical root: `/Users/jameschen/Workspace/nexus`, branch `feature/full-capability-closure-20260718`, HEAD `a2185edb0e67e3fc9d6ed7169593d9d80bb1c03a`; it remains protected and is not a mutation Target.
- Current workspace inventory hash: `795ad3bd4832e4592e899888ef316419106879882f3ccf35765756b16259ec48`.
- Current convergence plan hash: `a285fd2045b352162d903ab1d73f4e2a7d2c3783a5cc9c546b811425bcf2e646`; `deletion_count: 0`; `AUTO_CHAIN: false`.
- Controller versus canonical divergence is 266 controller-only commits and 4 canonical-only commits; P6 remains a separate owner gate.
- `workspace-convergence-core-primitives` is formally `SUPERSEDED`; its salvage ref remains evidence-only and it is no longer an actionable retained receipt.
- `exact-authorized-deletion-contract-bootstrap` remains the only actionable owner decision: `RETAINED_FOR_REVIEW` / `FINAL_BLOCK`, with cleanup `REMOVED`; no candidate, close, or disposal is authorized by this index.

## Final Physical Cutover Verification (2026-08-01)

- Canonical daily entrypoint: `/Users/jameschen/Workspace/nexus`.
- Canonical branch: `nexus/integration/main`; current verified HEAD: `HEAD` on the canonical branch (re-query with `git rev-parse HEAD` after each index update).
- Registered worktrees: `1`; exact path is the canonical root; `git worktree prune --dry-run` reports no stale metadata.
- Canonical dirty state: clean (`git status --short --branch` reports only `## nexus/integration/main`).
- Unregistered worktree root: `/Users/jameschen/Workspace/nexus-worktrees` is absent.
- Process/launcher state: no `devspace`, `nexus-worktrees`, or `nexus-8a1be3f4` process; `com.waishnav.devspace` is disabled in `gui/501`, and its plist is preserved at `/Users/jameschen/Workspace/nexus-salvage/20260801-root-convergence/com.waishnav.devspace.plist.disabled_20260801`.
- Retained refs: `70` `refs/nexus-salvage/*`, `33` `refs/heads/codex/*`, and `12` `refs/codex/turn-diffs/*`; salvage and branch deletion remain forbidden by this card.
- External preservation: root dirty archive, staged/unstaged patches, ignored residue archives, SymPy archive, and unregistered-worktree residue remain under `/Users/jameschen/Workspace/nexus-salvage/20260801-root-convergence/`.
- Archive SHA-256: `root-dirty-files.tar.gz`=`55f49a0561cac7445f6f76c44d97a3e1dbae7b110e86ed19dfa480cfe5cf060b`; `root-staged.patch`=`d9070be36347150b27acd9349793e7f3331f11734ed2a0e1b1d33f16b56d343e`; `root-unstaged.patch`=`c78849f28302461e7e0f9f6dcdca86438029c776557b5759a7b88b0105ac7916`; `root-scratch-ignored-residue.tar.gz`=`1cac6a0453ae4f4cbf48b47197b15696dd9c305991cf34928ff33e48b4d8c2a8`; `self-hosted-lifecycle-closure-controller-ignored-residue.tar.gz`=`8a0e179744044937dc85df6ff558acc849e7ea36dd03d4b6f615a33671eee5a9`; `sympy-13852-untracked.tar.gz`=`0b1b02c7bc4baeacc7ad9ee251605493aa8bd9987ffa009c5322c428ddf4e4d8`.
- Gate evidence: bounded lifecycle suite `217 passed in 120.68s`; CI dry-run passed; startup contract has passed on the final checkout (a prior run-scoped token `4a7749103061ce2d` is retained as evidence; tokens are timestamp-scoped).
- Gate hardening commits `c6a6ffc6b` and `89379333f` make Ultra Review and route smoke use the active interpreter, ignore dangling runtime links, and avoid the restricted uv cache; focused suites are `18 passed` and `36 passed`, and CI strict reached a passing Ultra Review lane.
- Gate hardening commit `2eb73514e` makes research-flow child verification use the active interpreter; the nightshift/research-flow focused app suite reached `107 passed`, with two pre-existing public-claim telemetry assertions still failing.
- Reconciled valuable unique source commit `eac5cedbf` (source commit `d3d38e1ba`) into the canonical branch: local-model alias resolution is now provider-owned and covered by `28 passed` across the resolver/provider integration tests; the packet touched 7 files.
- Contract compatibility commit `c9c05e5e1` restores numeric semantic-label decoding and dict-compatible DTO access; the bounded contract run is `231 passed / 1 failed`. The remaining failure is the stale expectation that fail-closed `INTAKE -> ESCALATE` is a legal transition; the authoritative transition matrix intentionally rejects that edge.
- The card's named `scripts/ops/acceptance_suite.py` and `scripts/ops/contract_test.py` entrypoints are absent. Authoritative replacements used for this live checkout are `scripts/ops/nexus_acceptance_check.py`, `scripts/ops/nexus_p30_acceptance_gate.py`, and `tests/contracts tests/contract` (232 tests collected).
- Gate residuals: full pytest now collects cleanly (`11484 collected` after adding `jsonschema` to the local `.venv`); the latest bounded run reached `4787 passed / 145 failed / 6 skipped` in `358.47s` before keyboard interruption at 42%, with repeated LanceDB background-event-loop timeouts. Acceptance is `UNVERIFIED_COLD_START` with zero samples. P30 remains `passed:false`: route smoke public-safe capability set is empty versus required nine, and route evidence-to-outcome rate is `0.206349`; CI strict reaches Wiki Governance and reports `226 passed / 55 failed` legacy documentation contracts. These remain evidence blockers, not workspace residue.

## Exact Live Inventory (2026-08-01 rechecked)

- Worktree/dirty/process census: one registered worktree only (`/Users/jameschen/Workspace/nexus`, `refs/heads/nexus/integration/main`); `git status --short --branch` is clean; `git worktree prune --dry-run -v` is empty; `/Users/jameschen/Workspace/nexus-worktrees` is absent; read-only `ps` found no `devspace`, `nexus-worktrees`, `nexus-8a1be3f4`, or route-smoke process.
- Ref census: `70` `refs/nexus-salvage/*`, `33` `refs/heads/codex/*`, and `12` `refs/codex/turn-diffs/*`. Salvage refs are owner-preserved evidence and are not disposable metadata under card 05.
- Non-ancestor Codex branches were rechecked after reconciliation with `git cherry nexus/integration/main <ref>`; all remain preserved: `codex/fix-code16-rootcause` (`+6`), `codex/governance-p0-hardening-v2` (`+3`), `codex/lifecycle-authority-reconciliation` (`+0/-1`, patch-equivalent), `codex/lifecycle-p6-stack` (`+0/-2`, patch-equivalent), `codex/local-armor-baseline-integration` (`+43/-1`, integrated alias-resolution patch plus 43 residual experimental commits), `codex/n30r-gate2-gate3-repair` (`+4/-4`, mixed patch-equivalent), `codex/n30r-v32-p8-integration-review` (`+19/-1`), `codex/n30r-v32-value-closure` (`+16/-1`), `codex/salvage-nexus-8a1be3f4-20260801` (`+7`), `codex/unified-production-closure-20260724` (`+7`), and `codex/wiki-final-audit-readonly-20260715` (`+3`). Remaining unique state is historical/generated, superseded, or requires a separate bounded owner-authorized packet; no unprotected unique state remains.

## Ordered Cards
1. [00-lifecycle-control-plane-workspace-convergence.md](00-lifecycle-control-plane-workspace-convergence.md) - `lifecycle-control-plane-workspace-convergence`
2. [01-lifecycle-control-plane-workspace-convergence-recovery.md](01-lifecycle-control-plane-workspace-convergence-recovery.md) - `lifecycle-control-plane-workspace-convergence-recovery`
3. [02-workspace-convergence-core-primitives.md](02-workspace-convergence-core-primitives.md) - `workspace-convergence-core-primitives`
4. [03-workspace-convergence-service-orchestration.md](03-workspace-convergence-service-orchestration.md) - `workspace-convergence-service-orchestration`
5. [04-workspace-convergence-cli-surface.md](04-workspace-convergence-cli-surface.md) - `workspace-convergence-cli-surface`
6. [05-live-worktree-convergence-and-canonical-cutover.md](05-live-worktree-convergence-and-canonical-cutover.md) - `live-worktree-convergence-and-canonical-cutover`

## Current Frontier
`live-worktree-convergence-and-canonical-cutover`

## Ready Cards
- `live-worktree-convergence-and-canonical-cutover`: owner approved on 2026-08-01.

## Completed Cards
- `workspace-convergence-core-primitives`: historical owner-integrated evidence at `74808adb6`; the corresponding lifecycle receipt is now formally `SUPERSEDED`, with salvage preserved and no Candidate promotion.
- `workspace-convergence-service-orchestration`: owner-integrated at `eece9edd9`; service/workflow suite 109 passed; compact list and exact-bound dry-run/apply surfaces added.
- `workspace-convergence-cli-surface`: owner-integrated at `72dee3d5d`; CLI suite 28 passed; inventory/plan/slot/converge commands are dry-run-first.
- `commit-aware-candidate-capture`: `9afd8f0a2`; commit/verifier/worktree suites 120 passed; scoped Worker commits are now reusable without wrapper commits.
- `workspace-cleanup-and-soak`: evidence commit `0bf523260`; cleanup removed 13 clean redundant worktrees without deleting branches/refs; registered worktrees reduced from 29 to 16; P7 combined lifecycle suite 230 passed; ten sequential slot cycles passed.
- `terminal-receipt-archive-and-ghost-task-disposal`: evidence commit `61b571189`; formal archive API preserved 68 terminal receipts with 68/68 hash checks; `python-verification-isolation-guard` and `self-hosted-verification-entrypoint-final-amendment` were formally superseded by their documented successors; actionable tasks reduced from 10 to 2. Two retained records remain for evidence review.
- `read-only-status-lock-free-hardening`: `b975957dc` switched actionable/inventory state reads to atomic snapshots without creating or acquiring `.state.lock`; service/workflow and full P7 regression remained green at 109 and 230 passed.

## Blocked Cards
- Retained evidence requiring explicit owner decision: `exact-authorized-deletion-contract-bootstrap`. `workspace-convergence-core-primitives` is superseded and closed; its salvage ref remains evidence-only. No lifecycle JSON was edited manually.

## Superseded Cards
- `lifecycle-control-plane-workspace-convergence`: SUPERSEDED_BY `lifecycle-control-plane-workspace-convergence-recovery`; three Agy account-pool subprocesses exited 1 after orphaned `/usr/bin/security -i` credential pipes. Salvage ref `refs/nexus-salvage/worktree/lifecycle-control-plane-workspace-convergence-2e73a792d9144335999fea648e038479` preserves the unverified implementation.
- `lifecycle-control-plane-workspace-convergence-recovery`: SUPERSEDED_BY the bounded 02/03/04 card sequence; Codex `gpt-5.6-luna` was provider-blocked by usage quota before mutation, and OpenCode L1 may not receive the original unbounded eight-file task.

## Task Dependencies
- `lifecycle-control-plane-workspace-convergence`: historical original attempt; no Candidate.
- `lifecycle-control-plane-workspace-convergence-recovery`: historical Codex recovery attempt; no Candidate.
- `workspace-convergence-core-primitives`: historical owner-integrated commit `74808adb6`; formal lifecycle receipt `SUPERSEDED`, no Candidate record, salvage-only evidence retained.
- `workspace-convergence-service-orchestration`: owner-integrated commit `eece9edd9`; no auto-chain.
- `workspace-convergence-cli-surface`: owner-integrated commit `72dee3d5d`; no auto-chain.

## Downstream Gate
The 2026-08-01 owner approval authorizes the exact worktree cleanup and canonical-root cutover in card 05. It does not authorize push, remote mutation, protected-history rewrite, deletion of salvage refs, or disposal of `exact-authorized-deletion-contract-bootstrap`.
