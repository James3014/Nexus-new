# Campaign Index: lsp-code-intelligence-pilot

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Run a repository-specific A/B benchmark comparing plain-text code discovery with Pyright LSP semantic queries on the Nexus codebase. Execute only in an isolated target. Create and run one temporary harness at scripts/benchmarks/lsp_ab_probe.py, measure six representative Python symbol queries, and report cold/warm latency, returned bytes, query count, and correctness. Do not modify production source, tests, configuration, lockfiles, or canonical checkout; do not apply, commit, approve, integrate, or push the harness.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `LSP-AB-20260803-02` | `00-LSP-AB-20260803-02.md` | ACTIVE | Owner confirmation |
