# V6-A Distillation / QLoRA Feasibility Gate

## Status: V6A_NOT_READY_FOR_TRAINING

## 1. Trace Inventory

| Category | Count |
|----------|-------|
| Internal audit traces | 6 (V4-A/B tasks) |
| Verifier-backed successes | 4 (MC001, MC006, MC007, V4B_12481) |
| Canonical recovery cases | 2 (MC006, V4B_12481) |
| Env blocker cases | 2 (MC008, V4B_13579) |
| Failure/control cases | 0 |

## 2. Data Quality

| Check | Status |
|-------|--------|
| Compliance pass rate | 100% (6/6 with caveats) |
| Missing fields | Schema drift (older artifacts) |
| Source license concerns | External repos (astropy, sympy) — BSD licensed |
| Private code concerns | None in current artifacts |
| Redaction needs | None identified |

## 3. Training Eligibility Gap

Before `training_eligible=true` is possible:
1. Owner approval required
2. Legal/license review for external repos
3. Data minimization (strip local paths, tokens)
4. Trace schema must support audit/export/training mode distinction
5. Compliance checker must enforce training eligibility gate

## 4. Candidate Training Objectives

| Objective | Feasibility |
|-----------|-------------|
| Format compliance | HIGH — clear pass/fail signal |
| Lane prediction | MEDIUM — 6 examples insufficient |
| Receipt audit | MEDIUM — 6 examples insufficient |
| Patch risk scoring | LOW — needs more data |
| Strict diff generation | HIGH — format compliance subset |
| Self-correction sequence | LOW — needs retry traces |

## Recommendation

**V6A_NOT_READY_FOR_TRAINING** — insufficient trace volume, no owner approval, governance not resolved.
