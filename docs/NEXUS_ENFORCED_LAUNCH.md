# Nexus Enforced Launch

Use enforced launch scripts to guarantee agents start under Nexus preflight.

## Nexus Armor Mode (Recommended)

To run agents in Nexus Armor Mode with full protocol enforcement:

```bash
uv run scripts/engine/nexus_cli.py nexus:status --global
uv run scripts/ops/ci_gate.py --dry-run
```

## Mandatory Protocol Checks

Before any task execution, the agent must pass:
1.  **Agent Protocol Check**: `uv run scripts/ops/agent_protocol_check.py`
2.  **Wiki Governance Audit**: `uv run scripts/ops/wiki_linter.py --strict`
3.  **Acceptance Check**: `uv run scripts/ops/nexus_acceptance_check.py --output-dir .nexus/reports`

## Why
- Prevent direct raw agent startup without Nexus gate checks.
- Force startup preflight (`nexus_cli --help` + `ci_gate --dry-run`) before agent session begins.

## Required Policy
- ✅ Allowed: launch via enforced scripts only.
- ❌ Disallowed: direct `gemini ...` or direct `antigravity ...` for production task execution.

## Gemini (enforced)
```bash
bash /Users/jameschen/Workspace/nexus/scripts/ops/start_gemini_nexus_enforced.sh gemini-3-flash-preview yolo
```

## Antigravity (enforced)
```bash
bash /Users/jameschen/Workspace/nexus/scripts/ops/start_antigravity_nexus_enforced.sh
```

If antigravity is not on PATH:
```bash
ANTIGRAVITY_BIN=/absolute/path/to/antigravity \
bash /Users/jameschen/Workspace/nexus/scripts/ops/start_antigravity_nexus_enforced.sh
```

## Override behavior
By default, gate failure blocks startup.

Temporary bypass (not recommended):
```bash
ALLOW_GATE_FAIL=1 bash /Users/jameschen/Workspace/nexus/scripts/ops/start_gemini_nexus_enforced.sh
```

