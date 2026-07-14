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


