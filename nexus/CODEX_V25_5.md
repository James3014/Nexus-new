# ⚔️ CODEX: Nexus v25.5 Adversarial Hardening
> Enforcement State: ACTIVE | Version: v25.5-Adversarial

## 1. Objective
Refactor Nexus Orchestrator to solve "Reporting Fraud" by decoupling evidence from claims.

## 2. Hardening Measures
- **Auditor Service**: Mandatory adversarial check on all PASS claims.
- **Evidence Trace**: Physical verification of Git Diffs and Command Exit Codes.
- **Belief Penalty**: Auto-depreciation of Bayesian confidence upon audit failure.

## 3. Physical State
- `nexus/core/orchestrator.py`: Injected with `_run_adversarial_audit`.
- `nexus/core/evidence_guard.py`: Physical verifier logic.
- `test_nexus_truth.py`: Local verification harness.

[NEXUS IDENTITY: 93fa558 | GOVERNANCE: ENFORCED]
