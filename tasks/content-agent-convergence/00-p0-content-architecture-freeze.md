# P0 — Content Architecture Freeze

**task_id:** `content-agent-convergence-p0-freeze-r4`
**artifact_authority:** current
**owner:** James Chen
**status:** CANDIDATE_READY
**read_only:** false
**audit_only:** false
**commit_forbidden:** false
**commit_required:** true
**candidate_required:** true
**worker_may_commit:** true
**worker_may_approve:** false
**worker_may_integrate:** false
**worker_may_push:** false

## Objective

Bootstrap and implement P0 Immediate Freeze for the content-agent-convergence campaign.
Create Task Authority files `tasks/content-agent-convergence/INDEX.md` and `tasks/content-agent-convergence/00-p0-content-architecture-freeze.md` with artifact_authority=current, owner=James Chen, AUTO_CHAIN=false, P0 as current frontier, Plan B/P1 recorded as already INTEGRATED with evidence commits 06e211496e05be3d42a7d079ef6f215977774f95 and 2df3357cc174aa90adda5679ccf5bcdc4cf8a619, and P2 Plan G0-G2 as next pending frontier.
Extend only the existing RepositoryContractGate so that:
1. Every newly created persistent Markdown file outside tasks/ is blocked with finding new_persistent_markdown_frozen, including newly created policy/authority Markdown such as AGENTS.md, MUSE_PROTO.md, docs or workflow Markdown;
2. Newly created Markdown under tasks/ is permitted only when its exact path is explicitly listed in contract.allowed_files;
3. Existing authorized Markdown modifications remain allowed except existing policy self-modification rules;
4. A newly created production Python module under nexus/ or scripts/ whose basename denotes agent, router, or wrapper is blocked;
5. A modified or new production Python file that introduces a new AST class whose name ends with Agent, Router, or Wrapper relative to the target base revision is blocked;
6. Existing Agent, Router, and Wrapper classes may be modified but no new component may be introduced;
7. Preserve all existing shadow findings, policy self-modification blocking, candidate lineage behavior, route authority, dirty-controller fail-closed, and Candidate verification semantics.

## Dependencies

None.

## Allowed files

- `tasks/content-agent-convergence/INDEX.md`
- `tasks/content-agent-convergence/00-p0-content-architecture-freeze.md`
- `nexus/orchestrator/repository_contract_gate.py`
- `tests/nexus/orchestrator/test_repository_contract_gate.py`

## Forbidden scope

- Any file outside the Allowed files list.
- Modifying WorktreeManager dirty-controller rejection.
- Adding a new gate, router, agent, wrapper, service, CI workflow, report, plan, ADR, inventory, classification, deletion, archive, or retrieval system.

## Verification commands

```text
/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -q tests/nexus/orchestrator/test_repository_contract_gate.py tests/nexus/orchestrator/test_candidate_verifier.py tests/nexus/orchestrator/test_worktree_manager.py::test_create_lease_rejects_dirty_controller
/usr/bin/env GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null PYTHONDONTWRITEBYTECODE=1 python3 -m compileall -q nexus/orchestrator/repository_contract_gate.py
git diff --check
git diff --name-status --diff-filter=D
```

## Evidence required

- Task Authority files `INDEX.md` and `00-p0-content-architecture-freeze.md` created.
- Extended `RepositoryContractGate` enforcing all P0 freeze rules.
- Unit tests covering P0 freeze rules in `test_repository_contract_gate.py`.
- Clean pass on all verifier commands.

## Exit criteria

All verifiers pass cleanly.

## Residual debt and block classification

- `RECOVERABLE_BLOCK`: Temporary environment failure; preserve state and resume.
- `HARD_BLOCK`: Irreversible drift or specification conflict.
