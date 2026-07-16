# Local Model Nexus Armor Operator Runbook

## Scope

Engineering-ready operator guide for **Local Model Nexus Armor** production path.

Armor provides: repository understanding, localization, routing, evidence, candidate isolation, verifier, receipt, governance, local assist layer. Models are executors only. Nexus remains authority.

N30R / Local Heal benchmarks are **validation tools**, not the product surface.

## Phase Responsibilities

### P3: Provider-Assist / Synthetic Candidate Trace
- Synthetic candidate generation only (no real provider) unless explicitly approved
- Shadow/dry-run authority
- No runtime behavior change when guard flags are off

### P6: Quota-Aware Degradation Advisory
- Advisory-only recommendations
- Cannot override P3/P4/P5
- Receipt-backed evidence only

### P2: Apply/Hash/Anchor Truth Authority
- Hash chain verification required
- Anchor truth required for any candidate
- Apply proof required before claim

### P4: Verifier/Claim Gate Authority
- Final verifier authority
- Claim gate required
- No P7/P6 override allowed

### P5: Selection Metadata Boundary
- Selection metadata recorded
- No P6 override of P5 selection

## Durable artifact storage

| Artifact | Default path |
|---|---|
| Repair receipts | `.nexus/reports/local_heal/<task_id>/receipt.json` |
| Isolated apply workspaces | `.nexus/artifacts/local_armor/workspaces/` |
| Repro scripts (replay) | `.nexus/artifacts/local_armor/repro/` |
| Operator logs | `.nexus/artifacts/local_armor/operator/` |

Override root (must be durable, not `/tmp` or `/var/folders`):

```bash
export NEXUS_ARMOR_ARTIFACT_ROOT=/absolute/durable/path
```

Decision receipts **must not** default to OS ephemeral temp. All decisions must be replayable from stored receipt (+ ledger fields inside receipt).

## Operator CLI (shipped entry)

```bash
# Dry-run: validate durable roots; no model, network, or patch apply
python -m nexus.services.local_heal.armor_operator_cli dry-run

# Status: storage roots, entry points, governance boundary
python -m nexus.services.local_heal.armor_operator_cli status

# Replay decision from a stored receipt (no model re-call)
python -m nexus.services.local_heal.armor_operator_cli verify-receipt .nexus/reports/local_heal/<task>/receipt.json

# Recovery steps (+ optional receipt inspect)
python -m nexus.services.local_heal.armor_operator_cli recovery --receipt path/to/receipt.json

# Rollback checklist
python -m nexus.services.local_heal.armor_operator_cli rollback-check
```

### Related modules

| Flow | Module |
|---|---|
| Apply dry-run (no mutation) | `local_model_apply_dry_run.run_local_model_apply_dry_run` |
| Write repair receipt | `receipt.write_repair_receipt` |
| Replay decision | `receipt.replay_repair_decision` |
| Artifact roots | `armor_artifact_storage` |
| Runbook compliance (artifact dir) | `python -m nexus.services.local_heal.runbook_compliance_cli <artifact_dir>` |
| Adaptive profile | `resolve_local_armor_profile` |

## Operator flows

### 1. Dry-run (safe default)

1. `python -m nexus.services.local_heal.armor_operator_cli dry-run`
2. Expect `status=ok`, `model_invoked=false`, `artifact_root_ephemeral=false`
3. Operator log written under durable `operator/` path

### 2. Normal run (local repair path)

1. Confirm env guards for live model only if intended (`NEXUS_LOCAL_MODEL_CALL_ALLOWED=1`, provider config).
2. Execute via existing Path B pipeline / executor (not Path D probes as production evidence).
3. Confirm `receipt.json` under `.nexus/reports/local_heal/...` with `artifact_storage=nexus_workspace_durable`.
4. `verify-receipt` on the written receipt before any claim language.

### 3. Error recovery

1. Halt further runs for the affected `task_id`.
2. Locate durable receipt (never invent paths under `/var/folders`).
3. `verify-receipt` → inspect `verifier_result`, `routing`, `claim_boundary`, `model_decisions`.
4. Do **not** hand-edit receipt or ledger.
5. Fix code/config; re-run; attach new receipt path as evidence.

### 4. Rollback

Triggers (any true ⇒ stop and roll back experimental flags):

- provider_invoked=true
- network_invoked=true
- api_key_used=true
- patch_apply_invoked=true
- runtime_behavior_changed=true
- public_claim_allowed=true
- production_ready=true
- verifier_bypassed=true
- receipt_forged=true
- policy_mutated=true

Actions:

1. Unset experimental opt-ins (`NEXUS_P3_CLOUD_WITH_LOCAL_ASSIST`, `NEXUS_ENABLE_P6_QUOTA_DEGRADATION`, `NEXUS_FORCE_FULL_ARMOR`, `NEXUS_FAST_MODE` as applicable).
2. Re-run `dry-run` and `status`.
3. Discard ephemeral decision artifacts if any were written outside durable roots.
4. `python -m nexus.services.local_heal.armor_operator_cli rollback-check`

## Env Guard Rules

- `NEXUS_ENABLE_P6_QUOTA_DEGRADATION` required for any P6 behavior
- `NEXUS_P3_CLOUD_WITH_LOCAL_ASSIST` required for any P3 cloud behavior
- Both flags off = unchanged behavior
- `NEXUS_ARMOR_ARTIFACT_ROOT` optional durable override (fail-closed if set to OS temp)

## Dry-Run/Synthetic-Only Restrictions

- No real provider execution (unless separate human-approved smoke package)
- No live model execution in operator dry-run
- No patch application in operator dry-run
- No network calls in operator dry-run
- No API key usage in operator dry-run

## Human Approval Required

- Any real provider/network smoke requires explicit human approval
- P8 human-approved network smoke package required before any live test
- Production rollout requires separate release gate

## Rollback Triggers

- provider_invoked=true
- network_invoked=true
- api_key_used=true
- patch_apply_invoked=true
- runtime_behavior_changed=true
- public_claim_allowed=true
- production_ready=true

## Forbidden Claims

- No production rollout
- No live quota routing
- No solve-rate improvement as product claim
- No public claim eligibility without release gate
- No production readiness without release gate
- No production rollout without Evidence Gate
- Path D probes are not mainline evidence

## Governance boundary (models)

Models may request only: Localization, Candidate, Verification assist, Receipt fields.

Models must not: Skip Verifier, Forge Receipt, Mutate Policy, Bypass Governance.

**Final authority: NexusVerifier.**

## Promotion note (Phase 3 deferred)

Selector/Judge: `KEEP_SHADOW`. Repair: `LIMITED_ASSIST`. Promotion is evidence-gated only — not manual receipt edits.
