# Nexus SF Skill Finalization V20 - 2026-05-19

## Status

- SF skill pairing: FINALIZED
- Runtime default update: HOLD
- Public benchmark: HOLD

## Decisions

### registry_skills_sync

- Runtime primary skill: `sf2-registry_skills_sync-route-fit-spec`
- Verdict: `KEEP_CURRENT_RUNTIME_SKILL_HOLD_CHALLENGERS`
- Reason: `challengers_delivery_passed_but_runtime_receipt_not_confirmed`

| Challenger | Token delta | Wall delta sec | Receipt status | Missing runtime fields |
|---|---:|---:|---|---|
| `github3-openclaw-map-registry-sync` | -2919 | -5.8455 | `RETURN_RUNTIME_RECEIPT_NOT_CONFIRMED` | selected, injected, used, evidence_present, gate_passed, outcome_contributed, skill_mount_contract_status_pass |
| `github3-openai-skill-creator-safe-registry-sync` | -2836 | -11.5308 | `RETURN_RUNTIME_RECEIPT_NOT_CONFIRMED` | selected, injected, used, evidence_present, gate_passed, outcome_contributed, skill_mount_contract_status_pass |

### ultra_review

- Runtime primary skill: `acceptance-evidence-failclosed`
- Verdict: `KEEP_CURRENT_RUNTIME_SKILL_HOLD_CHALLENGERS`
- Reason: `challengers_delivery_passed_but_runtime_receipt_not_confirmed`

| Challenger | Token delta | Wall delta sec | Receipt status | Missing runtime fields |
|---|---:|---:|---|---|
| `github3-claude-security-scan-safe-ultra-review` | -947 | -17.6549 | `RETURN_RUNTIME_RECEIPT_NOT_CONFIRMED` | selected, injected, used, evidence_present, gate_passed, outcome_contributed, skill_mount_contract_status_pass |

## Boundary

Delivery/cost improvement does not replace runtime receipt causality. A challenger must be runtime eligible and must prove selected/injected/used/evidence/gate/outcome before default replacement.

## Artifacts

- `docs/reports/NEXUS_SF_CANDIDATE_RECEIPT_SMOKE_V20_2026-05-19.json`
- `docs/reports/NEXUS_SF_RUNTIME_POLICY_APPLY_GATE_V20_2026-05-19.json`
- `docs/reports/NEXUS_SF_SKILL_FINALIZATION_V20_2026-05-19.json`
