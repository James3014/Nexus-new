# Nexus Module Inventory & P3 Readiness Audit

## 📊 Module Classification (Field Audit: 2026-06-14)

Total Packages: 85+

### 🟢 Active & Tested (High Integrity)
*Evidence: Packages with established `__init__.py` and matching `test_*.py` in the test suite.*

`ci/`, `classification/`, `contracts/`, `core/`, `delivery/`, `engine/`, `env/`, `evaluation/`, `evidence/`, `gate/`, `health/`, `memory/`, `orchestrator/`, `policy/`, `problem/`, `release/`, `replay/`, `research/`, `search/`, `state/`, `telemetry/`

### 🟡 Active but Untested (Stability Risk)
*Evidence: Packages found in `nexus/` with logic but no direct unit test coverage detected.*

`abstention/`, `benchmarks/`, `calibration/`, `evals/`, `events/`, `experimental/`, `federation/`, `feedback/`, `guardrails/`, `lanes/`, `lifecycle/`, `market/`, `ops/`, `problem_ingress/`, `receipts/`, `retry_policy/`, `rollout/`, `selection/`, `services/`, `tracing/`, `utils/`, `verifiers/`

### ⚪ Inert or Placeholder (Architecture Debt)
*Evidence: Directories appearing as empty placeholders or legacy scripts without core library integration.*

`api/`, `app/`, `autopilot/`, `benchmark/`, `bridge/`, `cli/`, `config/`, `connectors/`, `demo/`, `domain/`, `drills/`, `experiments/`, `governance/`, `infrastructure/`, `ingress/`, `knowledge/`, `models/`, `optimize/`, `oracle/`, `override/`, `plugins/`, `reactions/`, `reports/`, `resilience/`, `schemas/`, `scripts/`, `skills/`

## 🦀 Rust Crate Boundary Audit

### Current Split
1. **Root Crate (`/Cargo.toml`)**: PyO3 extensions for Python (High performance path).
2. **`nexus-core-rs` (`/nexus-core-rs/`)**: Independent binary/library.

### Redundancy Detected
- **Receipt Verifier**: Implemented in both `nexus-core-rs` and `nexus/engine/capability_receipt_adapters.py`.
- **Flow Machine**: Implemented in Rust (`flow_machine.rs`) and Python (`pipeline.py`).

### P3 Recommendations
- **Option A (Consolidation)**: Merge `nexus-core-rs` into the root crate. Move shared logic to a `nexus-common` workspace.
- **Option B (Auth Separation)**: Keep Python as the source of truth for logic, using Rust strictly for compute-intensive AST scanning and matching.

**Next Step**: Perform impact analysis on `tests/bridge/` before moving any Rust files.
