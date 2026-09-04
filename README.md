# Nexus Core v28.3.0 — Continuous Pull Request Certification

Nexus Core is a hardened local-first certification runtime for pull requests. It evaluates code changes against explicit Acceptance Contracts, verifies execution in hermetic environments, generates cryptographically verifiable receipts, and maintains an append-only ledger.

## 🚀 Quick Start (Certification-First)

Nexus Core provides a lightweight CLI `nexus-certify` for submitting, querying, and verifying PR certification receipts against the local Core HTTP runtime.

### 1. Install Nexus Core

```bash
# Minimal Core installation (pure runtime & thin clients, zero heavy ML/orchestration dependencies)
pip install nexus-core
```

### 2. Submit a Certification Request

```bash
# Submit a canonical certification request to the local HTTP runtime
nexus-certify submit --request request.json --url http://127.0.0.1:8767
```

### 3. Query Status and Retrieve Receipts

```bash
# Query status of a running or completed request
nexus-certify status <REQUEST_ID>

# Retrieve the tamper-evident certification receipt
nexus-certify receipt <REQUEST_ID>
```

### 4. Verify a Receipt

```bash
# Verify receipt integrity and cryptographic provenance
nexus-certify verify --receipt receipt.json
```

## 🔌 Client Interfaces

- **CLI (`nexus-certify`)**: Scriptable command-line interface for local operators and shell pipelines.
- **MCP Adapter (`product.clients.mcp`)**: Host-projected Model Context Protocol library adapter (`nexus_certify`).
- **GitHub Action (`.github/actions/nexus-certify`)**: Thin action wrapper designed for self-hosted GitHub runners.

## 🧪 Legacy Orchestration & Lab Surfaces

The historical agent orchestration and sensory swarm capabilities of Nexus Singularity have been sequestered under the `legacy` optional extra to ensure a clean, dependency-light Core installation:

```bash
# Install with legacy orchestration extras
pip install "nexus-core[legacy]"

# Invoke legacy CLI (marked as legacy/experimental lab)
nexus --help
```

Legacy commands executed without the `legacy` extra will return `LEGACY_EXTRA_REQUIRED` (exit code 78).

## 🗺️ Navigation

- **[Project Index (docs/INDEX.md)](docs/INDEX.md)**: Architecture and specification roadmap.
- **[Testing Runbook (docs/testing/test_runbook.md)](docs/testing/test_runbook.md)**: CI gates and local verification.
- **[Module Inventory (docs/arch/module-inventory.md)](docs/arch/module-inventory.md)**: Generated audit of 85+ packages.
