# Task Card 02: Bootstrap Path Convergence

## Identity

- task_id: `bootstrap-path-convergence`
- campaign_id: `bootstrap-authority-convergence`
- artifact_authority: current
- status: INTEGRATED_WITH_OWNER_REVIEW
- owner: James Chen
- depends_on: `task-authority-freshness` integrated
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Objective

Remove stale cross-agent bootstrap assumptions that bypass the current worktree authority. Every platform bootstrap must resolve repository rules from the current worktree, the Git-tracked Task Card, and formal lifecycle receipts; no bootstrap may require `nexus-sync`, `STATE.yaml`, a fixed Nexus version identity, an absolute checkout path, or the legacy `AGENT_MANDATORY_PROTOCOL.md`.

## Allowed files

- `AGENTS.md`
- `MUSE_PROTO.md`
- `GEMINI.md`
- `.gemini/GEMINI.md`
- `CLAUDE.md`
- `MEMORY.md`
- `SOUL.md`
- `.cursorrules`
- `tests/ops/test_bootstrap_authority_files.py`

## Forbidden scope

No dirty canonical-root mutation; no runtime router/workforce/startup checker changes; no deletion of historical reports or receipts; no provider/model changes; no P6 cutover; no new parallel protocol file.

## Required behavior

1. `AGENTS.md` is repository governance authority; Task Cards are execution authority; `MUSE_PROTO.md` is response/domain overlay only.
2. `MUSE_PROTO.md` contains no nonexistent CLI flag such as `--filter "domain=tech"`.
3. Root `GEMINI.md` is canonical; `.gemini/GEMINI.md` is a relative redirect only.
4. `CLAUDE.md`, `MEMORY.md`, and `SOUL.md` contain no `nexus-sync` or `STATE.yaml` dependency.
5. `.cursorrules` contains no absolute `/Users/jameschen/Workspace/nexus/` path and no `AGENT_MANDATORY_PROTOCOL.md` dependency.
6. No bootstrap file embeds fixed `Nexus-Singularity-V17`/V26 identity as authority.
7. Tests scan only the allowed bootstrap files and fail if any forbidden token or absolute checkout path returns.

## Verification commands

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/ops/test_bootstrap_authority_files.py
git diff --check
git diff --name-status --diff-filter=D
git diff --cached --name-status --diff-filter=D
git diff --stat
git diff --cached --stat
```

## Evidence required

- Test proves canonical/redirect relationship and forbidden-token absence.
- No changes outside the nine allowed files.
- Current worktree remains separate from `/Users/jameschen/Workspace/nexus`.

## Exit criteria

All bootstrap files resolve to current-worktree authority, focused tests pass, and a scoped commit is created.

## Integrated evidence

- commit: `70945794c`
- verification: `PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/ops/test_bootstrap_authority_files.py` (`2 passed`)
- scope: 8 changed files, all within the allowed file list; canonical root remained untouched
- follow-up: P0-C machine policy contract and P0-D startup freshness integration remain separate cards

## Residual debt

Machine policy contract and startup freshness integration are not covered by this card. Workforce/briefing work remains gated on P0-D.

## Block classification

- `RECOVERABLE_BLOCK`: test or local tooling failure with files preserved.
- `HARD_BLOCK`: required bootstrap authority would point outside the current worktree or require deletion of historical evidence.
