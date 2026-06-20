# nexus-receipt-core — Monorepo Boundary Definition

## Location
`subprojects/nexus-receipt-core/`

## Structure
```
nexus-receipt-core/
├── rust/
│   └── receipt_verifier/          # Rust crate: deterministic receipt verification
│       ├── Cargo.toml
│       ├── src/
│       └── tests/
├── schemas/
│   ├── python/
│   │   ├── fixtures/              # Test fixtures (public: valid JSON, private: S3 traces)
│   │   ├── generate_mismatch_report.py
│   │   ├── check_parity.py
│   │   └── compare_hashes.py
│   └── RESULT_SCHEMA.md           # Public contract: v0.1 frozen
├── verification-evidence/         # CI/test transcripts, parity reports
├── README.md                      # Public: what it is, how to use
├── INSTALL.md                     # Public: build instructions
├── RELEASE_NOTES_v0.1.md          # Public: release scope, known limits
├── BOUNDARY.md                    # Internal: this file
└── RFC.md                         # Internal: design rationale
```

## Public-Facing (OK to open-source)
- `rust/receipt_verifier/` — deterministic verification engine, no Nexus dependencies
- `schemas/RESULT_SCHEMA.md` — v0.1 frozen contract
- `schemas/python/fixtures/` — **only** synthetic test fixtures (no S3 traces, no secrets)
- `README.md`, `INSTALL.md`, `RELEASE_NOTES_v0.1.md`
- `verification-evidence/` — test transcripts (sanitized)

## Internal-Only (NOT for OSS)
- `schemas/python/` scripts that reference internal S3 buckets or task descriptions
- `verification-evidence/` containing raw Nexus traces
- `RFC.md` — design rationale tied to internal governance decisions
- Any fixture referencing real S3 URLs, private identifiers, or task descriptions

## Dependency Audit
- `receipt_verifier` depends ONLY on: `serde`, `serde_json`, `sha2`, `hex` — all public crates
- No dependency on `autonomicrouter`, `capability_planner`, or any Nexus core module
- CLI runs standalone with only fixture files as input
- Parity scripts (`check_parity.py`, `compare_hashes.py`) run independently of Nexus runtime

## OSS Readiness Checklist
- [x] License decision → Apache 2.0 (established)
- [x] Minimal CONTRIBUTING.md (established)
- [x] Fixtures sanitized (no S3 URLs, no secrets, no private identifiers)
- [x] README.md self-contained (no link to internal docs)
- [ ] CI badge points to public repo, not internal nexus-ci
