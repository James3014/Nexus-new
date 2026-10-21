---
ci_hash: pend-audit
created: 2026-04-07 05:59:01+00:00
governance: Trident 3.0
id: nexus-nexus-enforced-launch
landscape: structural
owner: Nexus Core
path: /docs/NEXUS_ENFORCED_LAUNCH.md
priority: P2
soul_alignment: harmonized
status: Current
tags:
- nexus
- sync
- - - documentation|documentation
type: Guide
updated: 2026-04-07 05:59:01+00:00
version: v23.1
visibility: internal
---


Waiver: 00_Home/[System Overview](../00_Home/System Overview.md).md
[source: nexus_wiki_vault/00_Home/System Overview.md]].md]



## One-sentence summary
- TODO

## Role / responsibility
- TODO

## Upstream
- TODO

## Downstream
- TODO

## Related modules / files
- TODO

## Source notes
- TODO

## Open questions / conflicts
- TODO

---


# Nexus Enforced Launch

Use enforced launch scripts to guarantee agents start under Nexus preflight.

## Nexus Armor Mode (Recommended)

To run agents in Nexus Armor Mode with full protocol enforcement:

```bash
uv run scripts/engine/nexus_cli.py nexus status --json
uv run scripts/ops/ci_gate.py --dry-run
```

## CLI Entrypoint Unification (入口統一對照表)

| 舊入口 (DEPRECATED_BLOCKED) | 唯一新入口 (MANDATORY) |
|---|---|
| `nexus:status` | `nexus status` |
| `nexus:acceptance-check` | `nexus acceptance-check` |
| `nexus:closeout` | `nexus contract-check` |
| `nexus:hud` | `nexus status` |
| `nexus:governance-check` | `scripts/ops/ci_gate.py --dry-run` |

## Mandatory Protocol Checks

Before any [task](../Reference/task.md) execution, the agent must pass:
1.  **Agent Protocol Check**: `uv run scripts/ops/agent_protocol_check.py`
2.  **Wiki Governance Audit**: `uv run scripts/ops/wiki_linter.py --strict`
3.  **Acceptance Check**: `uv run scripts/engine/nexus_cli.py nexus acceptance-check --evidence <FILE>`

## [[why|Why]]
- Prevent direct raw agent startup without Nexus gate checks.
- Force startup preflight (`nexus_cli --help` + `ci_gate --dry-run`) before agent session begins.

## Required Policy
- ✅ Allowed: launch via enforced scripts only.
- ❌ Disallowed: direct `gemini ...` or direct `antigravity ...` for production [task](../Reference/task.md) execution.

## Gemini (enforced)
```bash
bash ./scripts/ops/start_gemini_nexus_enforced.sh gemini-3-flash-preview yolo
```

## Codex (enforced) — retired launcher
`scripts/ops/start_codex_nexus_enforced.sh`, its helper `scripts/ops/codex_run_guard.py`
and the `start_antigravity_nexus_enforced.sh` proxy were deleted on 2026-10-21
(#2584, Phase-2 batch B, `ARCHIVED_2026-10-21_phase2_batch_B.md`): no host,
schedule or code ever launched them. Governed Codex work runs through
`CodexCliExecutor`, which applies the same run boundary
(`nexus/executors/codex_run_boundary.py`: disposable HOME, env allowlist,
symlink/`.git` integrity checks, atomic auth write-back).

## Override behavior
By default, gate failure blocks startup.

Temporary bypass (not recommended):
```bash
ALLOW_GATE_FAIL=1 bash ./scripts/ops/start_gemini_nexus_enforced.sh
```

---
[System Overview](../00_Home/System Overview.md)

---
[System Overview](../00_Home/System Overview.md)

---
[[System Overview]]