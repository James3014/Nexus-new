# Installation — `nexus-receipt-core`

> **Version**: v0.1  
> **Last Updated**: 2026-06-16

## Prerequisites

- **Rust toolchain** (stable, tested on 1.94.1)
  ```bash
  # Install via rustup if you haven't:
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
  ```
- **Cargo** (bundled with rustup)
- **Python 3.8+** (optional — only needed for the canonicalization parity tool)

## Quick Start

```bash
# Clone or copy this project
cd nexus-receipt-core

# Build
cargo build

# Run tests
cargo test

# Verify a receipt
cargo run -- verify ./schemas/python/fixtures/clean_receipt.json

# Skip hash check (schema + evidence only)
cargo run -- verify ./schemas/python/fixtures/clean_receipt.json --skip-hash
```

## Build Output

The compiled binary is located at:

```
target/debug/receipt-verifier
```

You can also install it globally:

```bash
cargo install --path rust/receipt_verifier
receipt-verifier verify ./receipt.json
```

## Python Parity Tool (Optional)

To verify Rust ↔ Python canonicalization alignment:

```bash
cd schemas/python
python3 canonicalizer.py ../rust/target/debug/receipt-verifier
cd ..
python3 generate_mismatch_report.py python_output.json rust_output.json mismatch_report.json
```

Expected output: `Mismatches: 0`

## Troubleshooting

### `rustc: command not found`

Make sure `~/.cargo/bin` is in your `$PATH`:

```bash
source "$HOME/.cargo/env"
```

### `cargo test` fails with compilation errors

Ensure you're using a stable Rust version ≥ 1.70:

```bash
rustc --version
```

### Unicode fixtures show `hash_mismatch`

This is expected. Unicode fixtures use a placeholder `claimed_hash` that doesn't match the computed hash. The important thing is that:
- They parse successfully
- Schema validation passes
- The canonicalization handles Unicode correctly

## Directory Structure

```
nexus-receipt-core/
├── Cargo.toml              # Workspace root
├── LICENSE
├── README.md               # Main documentation
├── RESULT_SCHEMA.md        # Result field contract
├── SCHEMA_VERSIONING.md    # Schema version policy
├── RFC.md                  # Design rationale
├── INSTALL.md              # This file
├── rust/
│   └── receipt_verifier/   # Core crate
│       ├── Cargo.toml
│       └── src/
│           ├── lib.rs      # Core logic
│           └── main.rs     # CLI entry point
└── schemas/
    ├── python/
    │   ├── canonicalizer.py
    │   └── fixtures/       # Test fixtures
    └── generate_mismatch_report.py
```
