# 📜 Universal Agent Guidelines: READ MUSE_PROTO.md
# SCOPE: Antigravity, Gemini, OpenClaw, Codex, Claude.
# SSOT: ./MUSE_PROTO.md

## 🎯 Semantic Completion Criteria
- **Behavioral Integrity**: The requested functionality is verified through empirical testing.
- **Structural Soundness**: Changes adhere to the local codebase conventions and architectural patterns.
- **Documentation Alignment**: Supporting documentation and tests are updated to reflect the new state.

## 📊 Evidence Reporting Format
- **Change Log**: List of modified files and high-level summary of changes.
- **Verification Evidence**: Specific commands executed and their key outputs (e.g., test results, status checks).
- **Residual Debt**: Any known issues or follow-up tasks explicitly stated.

## 🛡️ Agent Capability Boundaries
- **allowed_paths**: Project root, scripts/ops/, nexus_wiki_vault/, docs/
- **forbidden_paths**: .obsidian/, benchmarks/, logs/, nexus_swarm/, packages/
- **max_files_touched**: 10 (Strict Limit for single task)

## 🔄 Failure-to-Lesson Writeback
- Every failure encountered during the task MUST be analyzed for a "lesson".
- These lessons MUST be written back to the corresponding "Learning Closure Matrix" or ADR before task finalization.

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

This project is indexed by GitNexus as **Nexus** (65758 symbols, 97593 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/Nexus/context` | Codebase overview, check index freshness |
| `gitnexus://repo/Nexus/clusters` | All functional areas |
| `gitnexus://repo/Nexus/processes` | All execution flows |
| `gitnexus://repo/Nexus/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |
| Work in the Ops area (984 symbols) | `.claude/skills/generated/ops/SKILL.md` |
| Work in the Engine area (453 symbols) | `.claude/skills/generated/engine/SKILL.md` |
| Work in the Bench area (449 symbols) | `.claude/skills/generated/bench/SKILL.md` |
| Work in the Learning area (372 symbols) | `.claude/skills/generated/learning/SKILL.md` |
| Work in the Contracts area (210 symbols) | `.claude/skills/generated/contracts/SKILL.md` |
| Work in the Research area (207 symbols) | `.claude/skills/generated/research/SKILL.md` |
| Work in the Services area (200 symbols) | `.claude/skills/generated/services/SKILL.md` |
| Work in the Benchmark area (151 symbols) | `.claude/skills/generated/benchmark/SKILL.md` |
| Work in the Commands area (137 symbols) | `.claude/skills/generated/commands/SKILL.md` |
| Work in the Tests area (132 symbols) | `.claude/skills/generated/tests/SKILL.md` |
| Work in the Mempalace area (118 symbols) | `.claude/skills/generated/mempalace/SKILL.md` |
| Work in the Scripts area (99 symbols) | `.claude/skills/generated/scripts/SKILL.md` |
| Work in the Flipt area (89 symbols) | `.claude/skills/generated/flipt/SKILL.md` |
| Work in the Health area (87 symbols) | `.claude/skills/generated/health/SKILL.md` |
| Work in the Governance area (69 symbols) | `.claude/skills/generated/governance/SKILL.md` |
| Work in the Scratch area (61 symbols) | `.claude/skills/generated/scratch/SKILL.md` |
| Work in the Orchestrator area (56 symbols) | `.claude/skills/generated/orchestrator/SKILL.md` |
| Work in the App area (50 symbols) | `.claude/skills/generated/app/SKILL.md` |
| Work in the Pilot_cli area (45 symbols) | `.claude/skills/generated/pilot-cli/SKILL.md` |
| Work in the Sql area (44 symbols) | `.claude/skills/generated/sql/SKILL.md` |

<!-- gitnexus:end -->
