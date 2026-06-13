# Nexus Module Inventory & P3 Readiness Audit

## 📊 Module Classification

| Status | Directories | Description |
|--------|-------------|-------------|
| **Active** | `engine/`, `core/`, `app/`, `state/`, `telemetry/` | Core P-X-D-R-A-C infrastructure. |
| **Experimental** | `experimental/`, `market/`, `federation/` | Future features, currently non-critical. |
| **Legacy** | `pilot_cli/`, `abstention/`, `calibration/` | Older v16-v22 components, candidate for deprecation. |
| **Benchmark** | `benchmarks/`, `evals/`, `evaluation/` | Test suites and SWE-bench integration. |

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
