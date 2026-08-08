# Campaign Index: worktree-disposition-hardening-20260809

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Replace brittle registered-worktree-count gates with evidence-based disposition.
Classify every non-canonical worktree by lifecycle ownership, process/lock state,
dirty state, reachability, protected refs, unique commits, and review/evidence
retention. Never remove ambiguous or externally owned state.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `WORKTREE-DISPOSITION-HARDENING-01` | `00-WORKTREE-DISPOSITION-HARDENING-01.md` | ACTIVE | P1 source integration; non-overlap with active worker-readiness Candidate |

## Governance

- CapabilityPlanner and existing lifecycle authority remain unchanged.
- This campaign adds classification and completion gates, not a new manager.
- Worker may commit one scoped Candidate only; approval, integration, cleanup,
  ref deletion, and push remain primary/Owner actions.
- `AUTO_CHAIN=false`.
