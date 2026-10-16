# P0.1 Evidence Hygiene Report

## Summary

Fixed evidence hygiene issues: abort receipt guarantee, dedupe rules, claim boundary fields, and added StraTA StrategyEnvelope S0 schema-only skeleton.

## Files Changed

| File | Purpose |
|------|---------|
| `nexus/evidence/__init__.py` | New module init |
| `nexus/evidence/abort_receipt.py` | Abort receipt guarantee |
| `nexus/evidence/dedupe.py` | Dedupe rule + canonical instance ID |
| `nexus/evidence/claim_boundary.py` | Claim boundary fields + rules |
| `nexus/strategy/__init__.py` | Strategy module init |
| `nexus/strategy/strategy_envelope.py` | StrategyEnvelope v1 schema-only |
| `tests/unit/test_abort_receipt.py` | 5 tests for abort receipt |
| `tests/unit/test_dedupe.py` | 7 tests for dedupe |
| `tests/unit/test_claim_boundary.py` | 8 tests for claim boundary |
| `tests/unit/test_strategy_envelope.py` | 10 tests for StrategyEnvelope |
| `docs/reports/dedupe_manifest_v1.json` | Dedupe manifest example |
| `docs/reports/claim_boundary_rules_v1.md` | Claim boundary rules |

## Scope A: Abort Receipt Guarantee

- Abort receipt created for workspace provisioning failures
- Contains all required fields: task_id, instance_id, receipt_present=true, solved=false, claim_eligible=false, simulated=false, failure_class, failure_subclass, workspace/repo/target paths, model_calls=0
- 6 workspace failure subclasses defined: REPO_NOT_MOUNTED, WORKSPACE_NOT_WRITABLE, TARGET_PATH_UNRESOLVED, MANIFEST_MISSING_TARGET, WRONG_REPRO_PATH, STALE_MODEL_PATH
- Workspace failure classified as workspace_provisioning, not patcher failure

## Scope B: Dedupe Rule

- `normalize_instance_id()` handles `astropy__astropy-14096` -> `astropy-14096`
- `build_dedupe_group()` creates canonical + alias mapping
- `DedupeManifest` persists to JSON with schema v1
- `find_canonical()` resolves any alias to canonical via manifest
- No modification to historical receipt originals

## Scope C: Claim Boundary

- `ClaimBoundary` dataclass with all required fields
- `evaluate()` enforces rules:
  - simulated=true -> public_claim_allowed=false
  - receipt_present=false -> public_claim_allowed=false
  - claim_eligible=false -> public_claim_allowed=false
  - model_calls=0 -> public_claim_allowed=false
- Workspace failures not counted as patcher failures

## Scope D: StraTA S0 Schema-only

- `StrategyEnvelope` v1 with 13 required fields
- strategy_id computed from content hash (SHA256[:16])
- `validate()` checks required fields
- `check_paths()` enforces allowed/forbidden paths
- Serialize/deserialize support
- NOT connected to: CampaignGeneral, SurgicalPacker, prompt_builder, model routing
- No model calls produced

## Tests

30 tests, all passing:
- 5 abort receipt tests
- 7 dedupe tests
- 8 claim boundary tests
- 10 StrategyEnvelope tests

## Patcher Logic

Patch apply logic NOT modified. Confirmed by inspection: no changes to `patch_applier.py`, `apply_engine.py`, `bounded_fuzzy_applier.py`, or any fuzzy threshold.
