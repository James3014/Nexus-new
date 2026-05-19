---
name: github3-openclaw-map-registry-sync
description: 當使用者要求 Nexus 執行 registry_skills_sync work that needs OpenClaw/Codex skill map drift checks, skill inventory mapping, bundled skill baseline comparison, or registry synchronization planning; return receipt/evidence/gate/outcome-backed guidance. Do not use to execute external update scripts or mutate runtime defaults.
metadata: {"source_repo":"https://github.com/wsxqaza12/skill-openclaw-map","source_path":"main/SKILL.md","source_status":"generated_safe_candidate_from_external_repo","runtime_eligible":false,"ablation_eligible":true,"target_capability":"registry_skills_sync","safety_boundary":"prompt_only_no_external_script_execution"}
---

# Github3 Openclaw Map Registry Sync

Candidate-only safe adaptation for Nexus `registry_skills_sync` route-fit testing.

## Source Summary

- Repo: https://github.com/wsxqaza12/skill-openclaw-map
- Source path: main/SKILL.md
- Original description: OpenClaw environment map for coding agents (Claude Code, Cursor, Windsurf, etc.). Use when a coding agent needs to navigate or modify an OpenClaw installation — where config, logs, cron jobs, sessions, skills, workspaces, and docs live. Triggers on questions like "where are cron jobs stored?", "where are session logs?", "how does the workspace work?", "where is the OpenClaw config?", or any task that requires understanding the OpenClaw file system structure.

## Safety Boundary

- Do not execute upstream scripts, plugin commands, installers, scanners, MCP servers, or external tools.
- Do not mutate runtime default, permissions, global config, or skill registries.
- Use this skill only as prompt/context guidance inside ablation-only SF tests.

## Required Receipts

- selected
- injected_or_used
- evidence_present
- gate_passed
- outcome_contributed

## Adapted Workflow

> ---
> name: openclaw-map
> description: OpenClaw environment map for coding agents (Claude Code, Cursor, Windsurf, etc.). Use when a coding agent needs to navigate or modify an OpenClaw installation — where config, logs, cron j
> ---
> # OpenClaw Map
> Full reference: [references/environment.md](references/environment.md)
> Read it before navigating the file system. It covers:
> - How to locate the OpenClaw docs on any OS (`npm root -g` method)
> - `~/.openclaw/` directory layout
> - Agent workspace location and bootstrap files
> - Session transcript paths
> - Cron job format and CLI
> - Skills loading priority
> - Gateway daemon management
> - ACP bridge for IDE integrations
> - All log file locations
> - CLI quick reference
> ## Key facts
> | What | Where |
> |---|---|
> | Config | `~/.openclaw/openclaw.json` |
> | Gateway log | `/tmp/openclaw/openclaw-YYYY-MM-DD.log` |
> | Cron jobs | `~/.openclaw/cron/jobs.json` |
> | Sessions | `~/.openclaw/agents/<agentId>/sessions/<sessionId>.jsonl` |
> | Default workspace | `~/.openclaw/workspace` |
> | User skills | `~/.openclaw/skills/` |
> | Bundled docs | `$(npm root -g)/openclaw/docs/` |
> | Online docs | https://docs.openclaw.ai |
> ## Common tasks
> **Modify config** → edit `~/.openclaw/openclaw.json` (hot-reloads automatically; only `gateway.*` changes need restart)
> **Add cron job** → `openclaw cron add --name "..." --cron "..." --session main --system-event "..."`
> **Install a skill** → drop skill folder (containing `SKILL.md`) into `~/.openclaw/skills/`
> **Diagnose issues** → `openclaw doctor` or `openclaw logs --follow`

## Output Contract

Return `scope`, `checks`, `evidence_plan`, `fail_closed_boundaries`, and `recommended_catalog_verdict`.

