# 🛑 MANDATORY: READ MUSE_PROTO.md FIRST (located in project root).
# ADVISE: Use `nexus-sync` to poll the latest session summary.

## Agent skills

### Issue tracker

GitHub Issues (via `gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Standard triage roles (needs-triage, wontfix, etc.). See `docs/agents/triage-labels.md`.

### Domain docs

Multi-context layout defined in `CONTEXT-MAP.md`. See `docs/agents/domain.md`.

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
