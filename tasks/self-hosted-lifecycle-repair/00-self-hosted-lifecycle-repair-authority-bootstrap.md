# Task Card 00: Self-hosted Lifecycle Repair Authority Bootstrap

## Identity
- task_id: `self-hosted-lifecycle-repair-authority-bootstrap`
- campaign_id: `self-hosted-lifecycle-repair`
- artifact_authority: current
- status: INTEGRATED
- owner: James Chen
- commit_required: true
- candidate_required: true
- worker_may_commit: true
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- AUTO_CHAIN: false

## Goal
建立 Self-hosted Lifecycle 修復的唯一 canonical Campaign authority 與完整 Task Card 規範。

## Non-goals
- 不修改任何現有 production code 或 test
- 不修改 AGENTS.md, MUSE_PROTO.md, Model Workforce 政策
- 不刪除任何檔案
- 不自動啟動 Task 01 或 Task 02
- 不自動啟動 P2
- 不執行 approve, integrate, push

## Owner decisions
1. P0 現有整合保留，不回退。
2. `1425848c7f5e720275bd635ba294f0006a901d51` 不能直接視為完整 Workflow 修復。
3. 修復範圍只限 Self-hosted Lifecycle，不涉及 GitHub Actions。
4. Agy 可以讀取、修改、測試及建立 scoped commit。
5. Agy 不得 approve、integrate、push 或直接改寫 canonical durable state。
6. 每張卡獨立執行，`AUTO_CHAIN=false`。
7. Task 00 完成後停止，由人工審查及整合後才可啟動 Task 01。

## Source and start state
- Repository: `/Users/jameschen/Workspace/nexus-worktrees/integration-main`
- Expected branch: `nexus/integration/main`
- Expected starting HEAD: `1425848c7f5e720275bd635ba294f0006a901d51`
- Isolated target worktree: `/Users/jameschen/Workspace/nexus-worktrees/runtime-targets/self-hosted-lifecycle-repair/self-hosted-lifecycle-repair-authority-bootstrap`

## Authority map
- Selection authority: Model Workforce policy / existing CapabilityPlanner constraints
- Execution authority: Agy bounded Candidate generation
- Verification authority: CandidateVerifier + exact tests
- Receipt authority: SelfHostedTaskService durable state
- Approval authority: James / independent reviewer
- Integration authority: ControlledIntegrationManager

## Allowed scope
Only allowed 4 governance Markdown files under `tasks/self-hosted-lifecycle-repair/`:
- `tasks/self-hosted-lifecycle-repair/INDEX.md`
- `tasks/self-hosted-lifecycle-repair/00-self-hosted-lifecycle-repair-authority-bootstrap.md`
- `tasks/self-hosted-lifecycle-repair/01-self-hosted-lifecycle-core-hardening.md`
- `tasks/self-hosted-lifecycle-repair/02-self-hosted-lifecycle-recovery-surfaces.md`
Maximum touched files: 4.

## Unknown scan
- Searched task card conventions in `AGENTS.md` and `nexus_wiki_vault/`.
- Confirmed task card naming standard: `tasks/<campaign-id>/<NN>-<task-id>.md`.

## Mandatory source audit
- Verified Model Workforce policy permits Agy `gemini-3.6-flash-high` for bounded candidate generation under Nexus-bounded context.
- Verified target path is outside `/private/tmp` and inside workspace MCP visible directory.

## Start-state classification
PROOF_ONLY_NO_DEFECT_CLAIM

## RED or existing-guard proof
- `git status --short` shows exact 4 new Markdown files.
- Absence of executable Task Cards prior to commit blocks invalid downstream execution.

## Implementation constraints
- Use the current Nexus-isolated Git environment (`GIT_CONFIG_NOSYSTEM=1`, `GIT_CONFIG_GLOBAL=/dev/null`) for this bootstrap Candidate.
- The persistent canonical hook-root design belongs to Task 01. Do not establish `/private/tmp` as durable authority.
- Amend candidate commit `8222ff6abd6109884ea26e2e30c4387611a0c5dc`.
- Create/update protected candidate ref `nexus/task/self-hosted-lifecycle-repair-authority-bootstrap`.

## GREEN and regression gates
- `git diff --check` must be clean.
- Tracked deletion count must be 0 (`git diff --name-status --diff-filter=D`).
- Only 4 allowed files created.

## Mandatory command manifest
Required command receipt format: `command_id`, `cwd`, `exact_command`, `exit_code`, `passed`, `failed`, `skipped`, `duration`.
```bash
git diff --check
git diff --name-status --diff-filter=D
git diff --cached --name-status --diff-filter=D
git status --short
```

## Physical evidence
- candidate_commit: 628290120d709cab6865e04c6c3d09c23c853138
- candidate_tree: 625bb6465a064e67f1901c7adbb73c161efeced9
- integration_commit: 007b536be121573622b55e2b5e65b3cf7e1506b9
- integration_branch: nexus/integration/main
- Protected candidate ref (`refs/heads/nexus/task/self-hosted-lifecycle-repair-authority-bootstrap`)
- Changed files list (exactly 4 files)
- Tracked deletion count (0)
- Historical execution evidence: `/private/tmp/nexus-empty-git-hooks` used during bootstrap creation.

## Independent review
Required human review and approval by James Chen prior to integration.

## Exit conditions
- 4 governance Markdown files created with complete contract sections.
- Relative links verified in `INDEX.md`.
- Scoped candidate commit amended cleanly.
- Protected ref created.
- Execution stopped before Task 01.

## RECOVERABLE_BLOCK / HARD_BLOCK
- RECOVERABLE_BLOCK: Git environment noise or temporary lock.
- HARD_BLOCK: Modification requested on production/test code, attempt to start Task 01 automatically, or violation of AGENTS.md boundaries.

## Maximum claim
LIFECYCLE_REPAIR_AUTHORITY_BOOTSTRAPPED
