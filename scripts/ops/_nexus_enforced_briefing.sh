#!/bin/bash
set -euo pipefail

# Emit the smallest useful startup briefing by default.  The historical
# protocol remains available only as an explicit, non-normative reference.
OUT_FILE="${1:-.nexus/reports/enforced_agent_briefing.md}"
MODE="${NEXUS_BRIEFING_MODE:-compact}"
mkdir -p "$(dirname "$OUT_FILE")"

if [[ "$MODE" == "legacy" ]]; then
  LEGACY_FILE="${NEXUS_LEGACY_PROTOCOL_PATH:-docs/AGENT_MANDATORY_PROTOCOL.md}"
  if [[ ! -f "$LEGACY_FILE" ]]; then
    echo "legacy briefing reference missing: $LEGACY_FILE" >&2
    exit 1
  fi
  {
    echo "[NEXUS LEGACY BRIEFING REFERENCE]"
    echo "authority: non_normative; mode: explicit legacy opt-in"
    cat "$LEGACY_FILE"
  } > "$OUT_FILE"
  echo "$OUT_FILE"
  exit 0
fi

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
BRANCH="$(git symbolic-ref --short -q HEAD 2>/dev/null || echo DETACHED)"
HEAD="$(git rev-parse --short HEAD 2>/dev/null || echo UNKNOWN)"
if [[ -n "$(git status --porcelain=v1 2>/dev/null || true)" ]]; then
  DIRTY_STATE="dirty"
else
  DIRTY_STATE="clean"
fi

INDEX_PATH="${NEXUS_TASK_INDEX:-tasks/bootstrap-authority-convergence/INDEX.md}"
TASK_ID="${NEXUS_TASK_ID:-unknown}"
if [[ "$TASK_ID" == "unknown" && -f "$INDEX_PATH" ]]; then
  TASK_ID="$(awk '/^## Current Frontier/{found=1; next} found && /`/{gsub(/`/, ""); print; exit}' "$INDEX_PATH" || true)"
  TASK_ID="${TASK_ID:-unknown}"
fi
POLICY_PATH="${NEXUS_WORKFORCE_POLICY:-nexus/config/model_workforce.yaml}"
if [[ -f "$POLICY_PATH" ]]; then
  POLICY_HASH="$(shasum -a 256 "$POLICY_PATH" | awk '{print $1}')"
else
  POLICY_HASH="MISSING"
fi

cat > "$OUT_FILE" <<EOF
[NEXUS BOOTSTRAP-CANDIDATE]

# Compact current-worktree briefing

## Identity and freshness
- worktree_root: $ROOT
- branch: $BRANCH
- head: $HEAD
- dirty: $DIRTY_STATE
- task_index: $INDEX_PATH
- task_id: $TASK_ID
- workforce_policy_sha256: $POLICY_HASH
- startup_gate: python3 scripts/ops/nexus_startup_contract_check.py
- workforce_query: python3 scripts/engine/nexus_cli.py workforce status

## Authority
- AGENTS.md is repository governance authority.
- The active Git-tracked Task Card is execution authority.
- MUSE_PROTO.md is response/domain overlay only; it cannot override AGENTS.md or the Task Card.
- Workforce route authority remains CapabilityPlanner; this briefing never selects a worker.
- Missing or stale authority is NEXUS_BOOTSTRAP_INCOMPLETE and must block claims of active execution.

## Required evidence
- Verify worktree, branch, HEAD, dirty state, INDEX/card freshness, and policy hash before mutation.
- FAIL_CLOSED != SUCCESS; distinguish INFRA_INVALID from model or Nexus failure.
- Capability claims require selected, invoked, evidence, gate, and contribution proof; selected-only is not a claim.
- deterministic local rescue profile claims require their own evidence.
- Closeout must preserve receipt paths, command exit codes, and recovery classification.

## Workspace safety
- Do not kill/stash/restore/clean ambiguous targets.
- Root artifacts such as task patches are ROOT_ARTIFACT_LEAK unless explicitly scoped.
- Do not mutate protected directories or another worktree without explicit task authority.
- One task maps to one target worktree; retry the same task/card instead of opening a duplicate.

## Local Assist contract
- Read-only: nexus local-assist advisor
- Candidate: nexus local-assist candidate
- Bounded verifier: nexus local-assist verified-subtask
- Closeout: nexus local-assist closeout
- User relay validation: nexus local-assist user-relay-validate
- Required fields include local_assist_output_consumed, output_consumption_evidence, and every receipt path or task identity.
- Local Assist is advisory/candidate support, never verifier, approval, integration, push, or cleanup authority.

## Active marker
Only after the startup gate and evidence are true may the agent report:
[NEXUS ACTIVE]

Legacy protocol text is non-normative and requires explicit NEXUS_BRIEFING_MODE=legacy.
EOF

echo "$OUT_FILE"
