#!/bin/bash
set -euo pipefail

# Generate a single source-of-truth startup briefing that forces
# Nexus bootstrap proof before any agent may claim ACTIVE wearing.

OUT_FILE="${1:-.nexus/reports/enforced_agent_briefing.md}"
mkdir -p "$(dirname "$OUT_FILE")"

cat > "$OUT_FILE" <<'EOF'
[NEXUS v26 BOOTSTRAP-CANDIDATE]

# AGENT 強制執行規約 v2.9
(Fail-Closed, Runtime-Aligned, Report-Trust Hardened, Capability-Receipt Gated)

## 0) Identity Rule
Nexus is the governance/runtime armor, not a second agent. A model may claim `[NEXUS v26 ACTIVE]` only after it proves all bootstrap evidence below:
1. `commit_sha` from `git rev-parse --short HEAD`.
2. `_nexus_preflight.sh` completed or failed with explicit reason.
3. `uv run scripts/engine/nexus_cli.py --help` and `uv run scripts/engine/nexus_cli.py nexus --help` prove the command surface.
4. Nexus context/briefing was delivered to the model.
5. CapabilityReceipt or equivalent runtime evidence exists for selected/invoked/gated capabilities.

If any item is missing, report `NEXUS_BOOTSTRAP_INCOMPLETE`; do not claim ACTIVE.

## 1) Required Files
Read these if present; report `MISSING:<path>` without blocking when optional fallback is documented:
1. `AGENTS.md`
2. `MUSE_PROTO.md` or `nexus_wiki_vault/01_System/MUSE_PROTO.md`
3. `scripts/ops/_nexus_preflight.sh`
4. `scripts/engine/nexus_cli.py`
5. `nexus/engine/capability_planner.py`
6. `nexus/engine/capability_receipt_adapters.py`
7. `nexus/engine/autonomic_routing_service.py`
8. `nexus/core/hallucination_guard.py`
9. `.agents/skills/nexus-root-cause-probe/SKILL.md`
10. `.agents/skills/nexus-benchmark-public-report/SKILL.md`
11. `.nexus/reports/enforced_agent_briefing.md`

## 2) Startup Entrypoints
Use enforced scripts for external agents:
- Gemini: `bash scripts/ops/start_gemini_nexus_enforced.sh [prompt-file] [report-file] [timeout-sec]`
- Antigravity compatibility: `bash scripts/ops/start_antigravity_nexus_enforced.sh [model] [approval_mode] [prompt-file]`
- Codex: `bash scripts/ops/start_codex_nexus_enforced.sh [prompt-file]`

Bare `gemini`, `antigravity`, or model CLI output is not Nexus wearing evidence. If an enforced script is missing or fails, report `NEXUS_BOOTSTRAP_FAILED`.

## 3) CLI Alignment
Run help before using commands:
1. `uv run scripts/engine/nexus_cli.py --help`
2. `uv run scripts/engine/nexus_cli.py nexus --help`

Use only commands shown by help. Prefer `nexus <command>`; legacy `nexus:*` may be used only when help proves it still exists.

## 4) Capability Routing
Nexus must produce a capability plan before execution. The route input must include task type, risk, impact scope, cost budget, evidence needs, hidden verifier need, and public-claim need.

Capability claim requires all of:
- `selected=true`
- `invoked=true`
- `evidence_present=true`
- `gate_passed=true`
- `outcome_contributed=true`
- `public_claim_safe=true` for public claims

`selected-only`, recommendation-only, disabled flags, pending executors, and inferred report labels are not valid capability claims.

## 5) Report Trust Hard Rules
- `FAIL_CLOSED != SUCCESS`; fail-closed protects integrity but does not prove delivery.
- `ENV_INVALID` / `INFRA_INVALID` / dependency missing / Docker missing must be separated from model or Nexus capability failure.
- RLM/self-heal claims require `rlm_trace_present=true` or `capability_self_heal_used=true`.
- DDTree savings require pruning evidence.
- Swarm/Drone/Nightshift claims require concrete report/evidence paths.
- Deterministic local rescue profile claims must say `deterministic local rescue profile` or equivalent Nexus-system rescue wording; do not claim the same external model became cheaper unless same-model token evidence proves it.

## 6) Workspace Safety
- Do not kill/stash/restore/clean ambiguous targets.
- For `kill`, `pkill`, `git stash`, `git restore`, `git clean`, or unrelated untracked deletion, list exact candidates and wait for explicit user confirmation unless the user already named the exact PID, command, or path.
- Root artifacts such as `task_*.patch`, `*_test.patch`, and `element_task_*` are `ROOT_ARTIFACT_LEAK` unless the task explicitly asks to keep them.
- Do not mutate `.obsidian/`, `benchmarks/`, `logs/`, `nexus_swarm/`, or `packages/` unless explicitly authorized.

## 7) Gates
General closeout should report actual status for:
1. `delivery_gate`
2. `acceptance_check`
3. `contract_check`
4. `ci_gate`
5. `public_claim_gate` or `NOT_APPLICABLE`

Missing evidence is `UNVERIFIED`; do not declare Done.

## 8) Public Claim Gate
Public improvement claims require same model, same task/trial multiset, hidden verifier, complete run eligibility, separated infra-invalid rows, trust mismatch 0, Nexus wearing valid rate 100%, context delivered 100%, claim verified 100%, evidence bundle hash, raw JSONL preserved, and per-capability public gate PASS.

## 9) Required Report Shape
Every closeout must include:
```json
{
  "commit_sha": "<sha>",
  "semantic_audit": {"state": "VERIFIED/PARTIAL/REJECTED/UNVERIFIED", "failures": []},
  "nexus_wearing": {
    "model_calls": 0,
    "model_uses_nexus": false,
    "nexus_context_delivered": false,
    "nexus_usage_valid": false
  },
  "capability_receipts": {"public_safe": [], "selected_only": [], "failures": []},
  "gate_summary": {
    "delivery_gate": "PASS/FAIL/NOT_RUN",
    "acceptance_check": "PASS/FAIL/NOT_RUN",
    "contract_check": "PASS/FAIL/NOT_RUN",
    "ci_gate": "PASS/FAIL/NOT_RUN",
    "public_claim_gate": "PASS/FAIL/NOT_APPLICABLE"
  },
  "report_file": "<absolute-path>",
  "commands": [{"cmd": "<command>", "exit_code": 0, "evidence": "<key output or report path>"}],
  "recovery_directive": "none/stateless_pivot/report_trust_probe/route_replan"
}
```

## 10) Active Marker
Only after the bootstrap and wearing evidence are true may the agent switch to:
`[NEXUS v26 ACTIVE]`

Close with:
`[NEXUS IDENTITY: <SHA> + v2.9 RUNTIME-ALIGNED]`
EOF

echo "$OUT_FILE"
