# 📜 Universal Agent Guidelines: READ MUSE_PROTO.md
# SCOPE: Antigravity, Gemini, OpenClaw, Codex, Claude.
# SSOT: ./MUSE_PROTO.md

## 🎯 Semantic Completion Criteria
- **Behavioral Integrity**: The requested functionality is verified through empirical testing.
- **Structural Soundness**: Changes adhere to the local codebase conventions and architectural patterns.
- **Documentation Alignment**: Update an existing authoritative document only when the task changes a durable contract, operator procedure, or public interface. Documentation alignment does not by itself authorize creating a new report.

## 📊 Evidence Reporting Format
- **Default surface**: Report evidence in the final agent response, commit message, pull-request description, or an existing structured receipt. Do not create a Markdown/JSON report file merely to satisfy evidence reporting.
- **Change Log**: List modified files and summarize the behavioral change.
- **Verification Evidence**: List the exact commands executed and their key outputs (e.g., test results, status checks).
- **Residual Debt**: State known issues and follow-up work explicitly.

## 🧾 Persistent Artifact Admission Policy
- **Default is no new persistent document**: A task does not create a file under `docs/reports/`, `docs/plans/`, `docs/arch/`, `docs/testing/`, the Wiki, or an ADR directory unless an admission condition below is met.
- **Admission conditions**: A new persistent artifact is allowed only when at least one is true:
  1. The user or task specification explicitly requires that exact artifact.
  2. Runtime, CI, release, or another machine consumer requires the artifact.
  3. The artifact defines a durable contract, ADR, runbook, operator entrypoint, or current SSOT that has no existing authoritative home.
  4. The task is a dedicated audit, inventory, indexing, migration, or closure task whose primary deliverable is the artifact.
  5. Cross-session handoff requires persistence and no existing task/receipt store can represent it.
- **Prefer updating authority**: Update the current authoritative document instead of creating `v2`, `final`, `updated`, `corrected`, `closeout`, or parallel summaries. Historical versions belong in an explicit archive only when the task authorizes archival work.
- **No self-authorizing reports**: Requirements in this file to provide evidence, retrieve lessons, align documentation, or close a task are not permission to create a report file.
- **No recursive evidence artifacts**: Do not create a report solely to document creation of another report, inventory, receipt, or closeout artifact.
- **Required metadata**: Any admitted persistent document must identify its purpose, authority (`current`, `reference`, or `historical`), owner, status, and the evidence/commit it describes. Claims such as `COMPLETE`, `SEALED`, `PRODUCTION READY`, or `PUBLIC CLAIM ALLOWED` require the corresponding physical gate evidence.
- **Task-card enforcement**: If a task requests a new artifact, its allowed path and filename must appear in the task's Allowed files. Otherwise return evidence in the final response only.
- **Legacy authority**: Persistent documents created before the admission policy, or documents lacking artifact_authority metadata, are evidence-only by default. They must not be treated as current authority unless a current manifest, ADR, runbook, code consumer, or task specification explicitly promotes them. Claims in a report do not override physical code, tests, runtime receipts, or newer authoritative contracts.

## 🗂️ Task Card Authority and Discovery
- **Canonical execution authority**: Approved, cross-session Task Cards MUST be Git-tracked under `tasks/<campaign-id>/`. Do not use chat history, `.nexus/`, `docs/plans/`, or `docs/reports/` as the executable task specification.
- **Campaign index**: Every active campaign MUST have `tasks/<campaign-id>/INDEX.md`. The index declares `artifact_authority: current`, owner, status, source specification, ordered cards, dependencies, current frontier, completed/blocked/superseded cards, and `AUTO_CHAIN`.
- **Card naming**: Use `tasks/<campaign-id>/<NN>-<task-id>.md`. The card's `task_id` MUST exactly match the Nexus lifecycle task ID.
- **Required card contract**: Each active card MUST define objective, authority and status, inputs, dependencies, allowed files, forbidden scope, verification commands, evidence required, exit criteria, residual debt handling, and block classification.
- **Discovery order**: Before implementation, agents MUST read the root `AGENTS.md`, locate the relevant campaign `INDEX.md`, read only the current-frontier card, then verify the lifecycle `task_id`, `task_card_path`, and `task_card_hash` before editing code.
- **Runtime state is not specification authority**: `.nexus/multi_agent/tasks/` and other `.nexus` lifecycle stores may record task ID, card path/hash, Target, Candidate, status, verification, integration, and receipts. They MUST NOT replace or silently rewrite the Git-tracked Task Card.
- **Design and evidence are non-executable by default**: `docs/plans/` is design input and `docs/reports/` is evidence/history. Neither authorizes execution unless an active Task Card explicitly cites and bounds it.
- **Legacy root cards**: Existing root-level files under `tasks/` are evidence-only unless an active campaign `INDEX.md` explicitly promotes them.
- **No implicit chaining**: `AUTO_CHAIN=false` is the default. A successor card may start only when the campaign index explicitly names it and its dependency/exit gates are satisfied. Completion, failure, or BLOCK of one card never self-authorizes another card.

## ⛔ Task Block Semantics
- **RECOVERABLE_BLOCK**: A temporary external or environmental condition prevents progress without invalidating the Task Card. Preserve state and evidence, name the exact unblock condition, and resume the same card after recovery. Do not create or start a replacement card automatically.
- **HARD_BLOCK**: Authority, safety, architecture, evidence integrity, irreversible-risk, or specification conflict prevents valid continuation. Stop mutation, preserve evidence, state the decision required, and require explicit owner/spec-authority resolution before resuming or superseding.
- **Blocked means no promotion**: Neither block class permits Candidate promotion, integration, cleanup, production-readiness claims, public claims, or downstream task activation.
- **Supersession is explicit**: Replacing a blocked card requires an explicit `superseded_by` link in the campaign index and lifecycle state. The replacement card must have its own path, task ID, hash, authority, scope, and gates.

## 📦 Commit and Candidate Policy
- **Implementation tasks require a scoped commit**: Unless the active Task Card explicitly declares `read_only: true`, `audit_only: true`, or `commit_forbidden: true`, a valid implementation task MUST end with a Git commit containing only that card's authorized changes.
- **Task Card authority fields**: Implementation cards MUST declare `commit_required`, `candidate_required`, `worker_may_commit`, `worker_may_approve`, `worker_may_integrate`, and `worker_may_push`. Defaults are `commit_required: true`, `candidate_required: true`, `worker_may_commit: true`, and all three downstream authorities `false`.
- **No commit from mixed dirty source checkout**: When unrelated tracked or untracked changes are present, implementation MUST occur in a clean isolated Target. Never stage, commit, reset, stash, clean, overwrite, or absorb unrelated source-checkout changes.
- **Required pre-commit gates**: Before committing, verify allowed-file scope, run the Task Card's exact verification commands, run `git diff --check`, inspect tracked deletions, run GitNexus detect-changes, and review the complete staged diff.
- **Worker responsibility**: The implementing Worker creates the scoped implementation commit and reports its exact SHA. Leaving verified implementation changes uncommitted and claiming completion is invalid.
- **Candidate formation**: Under governed lifecycle execution, the scoped commit becomes a Candidate only after the card's required verification succeeds and the Candidate record is bound to the exact commit and task-card hash.
- **Separation of authority**: A Worker MUST NOT approve, integrate, merge, push, or clean up its own Candidate unless the active Task Card explicitly grants that exact authority. Commit authority does not imply approval, integration, push, cleanup, or production-claim authority.
- **Commit failure is a block**: If a required scoped commit cannot be formed safely, the task is not complete. Return `RECOVERABLE_BLOCK` or `HARD_BLOCK` with the exact physical reason and preservation state.

## 🛡️ Agent Capability Boundaries
- **allowed_paths**: Project root, scripts/ops/, nexus_wiki_vault/, docs/
- **forbidden_paths**: .obsidian/, benchmarks/, logs/, nexus_swarm/, packages/
- **max_files_touched**: 10 (Strict Limit for single task)

## 🔄 Failure-to-Lesson Writeback
- Analyze failures during the task, but persist a lesson only when the failure is novel, repeatable, and has a concrete prevention rule or verification contract that will benefit future tasks.
- Do not persist routine command typos, shell quoting mistakes, transient tool failures, one-off environment noise, user-corrected misunderstandings, or failures already covered by an existing lesson.
- Prefer appending one concise entry to the existing Learning Closure Matrix or structured learning ledger. Do not create a new report for a lesson.
- Create or update an ADR only for a durable cross-module architectural decision with alternatives and consequences; an implementation failure alone is not an ADR.
- When no persistent writeback qualifies, state `no durable lesson writeback required` in the final response.

## 🔎 Pre-Task Lesson Retrieval
- Before non-trivial tasks, agents MUST perform targeted retrieval, not full-corpus reading.
- Agents MUST derive 3-8 stable search handles from the task: filenames, modules, commands, error strings, gate names, route names, benchmark names.
- Search only relevant lesson sources: `nexus_wiki_vault/06_Ops/Ops - Learning Closure Matrix.md`, `nexus_wiki_vault/01_System/ADR/`, `docs/reports/`, `docs/arch/`, `docs/testing/`.
- Read only the top relevant files or sections.
- Report retrieved lessons with: source path, applicability, and how they change the current plan.
- If no relevant lesson is found, state `no relevant prior lesson found`.

## 🤖 Model Workforce Authority
- Before any planning, routing, delegation, model-selection, Local Assist, Cloud Assist, committee, or external-agent task, agents MUST read `docs/arch/MODEL_WORKFORCE_POLICY.md` and `nexus/config/model_workforce.yaml`.
- Installed binaries, cached model lists, historical reports, and model self-descriptions are discovery evidence only. They do not grant assignment authority or a higher autonomy level.
- CapabilityPlanner and HybridRouteDecision remain the route authority. The workforce policy constrains eligible workers and escalation; it must not create a parallel router or topology selector.
- Fresh runtime discovery and physical receipts override stale roster details. Update the fixed authority files above instead of creating parallel `v2`, `final`, or dated model-policy reports.
- Local model output is always a candidate. It cannot independently establish correctness, promotion, `production_ready`, `public_claim_allowed`, merge authority, or cleanup authority.

## 🚫 No Full Corpus Read
- Agents MUST NOT read all reports, ADRs, or lesson files before normal tasks.
- Full-corpus scans are allowed only for dedicated audit/indexing tasks.
- Normal tasks MUST use bounded targeted retrieval and avoid loading unrelated historical reports.

## 🤐 輸出壓縮協議 (bu-ketao)
- **禁用開場**: 禁止「好的」、「收到」、「我將...」。
- **禁用敘事**: 禁止解釋 Tool Call 過程。
- **禁用客套**: 禁止「希望能幫助你」、「隨時回報」。
- **數據優先**: 僅輸出 [任務] -> [數據] -> [證據]。

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **actionlint** (65342 symbols, 94771 relationships, 300 execution flows). Use GitNexus as a best-effort code intelligence aid to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, try `npx gitnexus analyze` once when it is practical. If GitNexus is unavailable, stale, missing symbols, or the refresh stalls, do not block the task; report the limitation and fall back to targeted `rg`, tests, and local code inspection.

## Always Do

- **Best effort: run impact analysis before editing important symbols.** Before modifying a function, class, or method, prefer `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **Best effort: run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- If impact analysis cannot run, returns `UNKNOWN`, or cannot find the symbol, state that GitNexus impact evidence is unavailable and proceed with a narrower manual blast-radius check.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.
- **Always run deletion checks before committing:** Run the four commands below to audit modified and deleted paths. If deletions are present, explain the rationale for each file.
  ```bash
  git diff --name-status --diff-filter=D
  git diff --cached --name-status --diff-filter=D
  git diff --stat
  git diff --cached --stat
  ```

## Never Do

- Do not treat GitNexus failures as task blockers when the user request is otherwise clear and local verification is available.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- Before committing, prefer `gitnexus_detect_changes()`; if unavailable, use `git diff --stat`, targeted diff review, and focused tests instead.
- **NEVER automatically delete tracked files that match `.gitignore` patterns** (such as historical metrics, learning logs, or tracked cache files) during feature implementation tasks. Git ignore rules only apply to untracked files.
- **NEVER combine out-of-scope repository cleanup or file deletion with implementation commits.** Keep implementation scopes clean and isolated.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/actionlint/context` | Codebase overview, check index freshness |
| `gitnexus://repo/actionlint/clusters` | All functional areas |
| `gitnexus://repo/actionlint/processes` | All execution flows |
| `gitnexus://repo/actionlint/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->

# 🛡️ Generation Degeneration Guard

懷疑輸出退化或失控重複時，停止後續工具與檔案修改，保留最後已確認動作，回傳 `retry_required=true`，並從新的 bounded context 重啟。AGENTS.md 規則不等於 runtime detector。

## Tool Execution Rules
* **No Pre-ambles**: Do not describe or explain which tool is about to be used.
* **Direct Invocation**: Issue the tool call directly without transition phrases or prose.


## 🛡️ Telemetry, Gate Verification & Deletion Safety

### 1. Telemetry Verification & Claimability
- **Structural vs. Model Separation**: For structural capabilities (e.g., `claim_gate`, `artifact_gate`), `token_usage=0` is valid. `token_usage > 0` is only enforced when `model_calls > 0`.
- **Telemetry Availability**: When executing capabilities in production or simulation executors (e.g., `ExecutorControls`), always measure real execution metrics (e.g., `wall_time_ms`, `overhead_ms`) and populate the receipt's telemetry dict. Simulated receipts with missing telemetry block `is_claimable` checks.

### 2. Strict Proof-Backed Gates (Anti-Hallucination)
- **Adapter Validation**: Receipt adapters must not blindly trust `claim_verified=True`. They must validate `verifier_artifact` (or `verifier_status`) and `source_hash`. If proof attributes are missing, the gate must fail closed (`gate_passed=False`) and record the failure reason.

