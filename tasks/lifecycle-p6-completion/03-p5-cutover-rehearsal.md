# Task Card 03: P5 Cutover Rehearsal Link

## Identity

- task_id: `lifecycle-p5-cutover-rehearsal`
- campaign_id: `lifecycle-p6-completion`
- artifact_authority: reference
- status: COMPLETED_REHEARSAL_ONLY
- owner: James Chen
- read_only: true
- audit_only: true
- commit_required: false
- candidate_required: false

## Gate

P5 rehearsal is evidence only. It does not approve or integrate the isolated stack and does not authorize canonical-root mutation.

## Evidence

Temporary detached controller rehearsal returned `Nexus Startup Contract PASSED`, rollback returned to the original controller HEAD, and the temporary worktree was removed. The canonical root remained untouched.
