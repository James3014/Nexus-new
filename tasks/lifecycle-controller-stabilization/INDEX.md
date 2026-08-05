# Lifecycle Controller Stabilization

artifact_authority: current
owner: James Chen
status: active
campaign_id: lifecycle-controller-stabilization
source_authority: Owner continuous execution approval for B0 then C1
source_anchor: e93dc3e4b101c4019436f3db5a6082f916ffae8d
ordered_cards:
  - 00-controller-action-identity-stabilization.md
  - 01-independent-controller-acceptance.md
dependencies: []
current_frontier: 00-controller-action-identity-stabilization.md
completed_cards: []
blocked_cards:
  - 01-independent-controller-acceptance.md (requires a fresh Owner instruction after the C1 Candidate)
AUTO_CHAIN: false

## Authority

This campaign bootstraps a clean, immutable, Git-bound lifecycle Controller and
then creates exactly one governed C1 Candidate. The one-time B0 governance
commit is Owner-authorized directly on `nexus/integration/main`; C1 must execute
from a new clean detached Controller through the formal self-hosted lifecycle
into a physically separate clean Target.

The canonical dirty checkout at `/Users/jameschen/Workspace/nexus` is retained
as source evidence. Its unrelated tracked and untracked changes must not be
staged, modified, copied into the Controller or Target, or absorbed into either
commit. Commit `51b89674132eb0b3deff452b797fe016d1c7f814` is forensic evidence
only and must not be cherry-picked, merged, rebased, or used as a base.

## Round boundary

The Owner-approved sequence is B0 followed by C1 without an intermediate
approval pause. It is not general automatic chaining. Execution stops after
the C1 Candidate reaches `PENDING_HUMAN_APPROVAL` or a named fail-closed block.
This round does not authorize C2, approval, integration, merge, push, Gateway
reload, Phase6 curation, legacy-test work, cleanup, or production claims.

## Controller invariants

- The Controller is a clean detached worktree at the B0 governance commit.
- Controller HEAD, tree, task-card path, and task-card hash are frozen before C1.
- The Controller must be clean before and after its baseline suite and before
  and after C1 lifecycle actions.
- Dirty-controller authorization and dirty-content hashes are forbidden.
- No stale Gateway or MCP lifecycle surface may submit or mutate this campaign.
- Lifecycle state is created only through the formal service or CLI.

## Gate

C1 is eligible only when B0 starts from the exact source anchor, stages and
commits only the three campaign files, preserves the pre-existing dirty source,
creates the clean detached Controller, proves its fixed HEAD/tree and clean
status, passes the controller baseline suite, and finds no existing durable C1
task. Any failed B0 condition stops before C1.
