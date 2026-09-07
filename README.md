# Nexus-new — Legacy Integration Lab & Compatibility Host

> [!IMPORTANT]
> **Repository Boundary & Ownership Transition Note**
> `James3014/Nexus-new` is no longer the canonical implementation repository for Nexus Core, Nexus Learning, or Open SWE runtime.
> - **Nexus Core**: Canonical repository is [`James3014/nexus-core`](https://github.com/James3014/nexus-core).
> - **Nexus Learning**: Canonical repository is [`James3014/nexus-learning`](https://github.com/James3014/nexus-learning).
> - **Open SWE Runtime**: Canonical repository is [`James3014/nexus-open-swe-runtime`](https://github.com/James3014/nexus-open-swe-runtime).
>
> `James3014/Nexus-new` now serves as the **Legacy Integration Lab & Compatibility Host**. Existing historical paths may remain as compatibility snapshots or source history, but new canonical Core/Learning/Open SWE implementation work belongs in their standalone repositories.

# Canonical Nexus Core — Continuous Pull Request Certification

Nexus Core is a hardened local-first certification runtime for pull requests. It evaluates code changes against explicit Acceptance Contracts, verifies execution in hermetic environments, generates cryptographically verifiable receipts, and maintains an append-only ledger.

## 🚀 Quick Start (Certification-First)

Nexus Core provides a lightweight CLI `nexus-certify` for submitting, querying, and verifying PR certification receipts against the local Core HTTP runtime.

### 1. Install Nexus Core from its canonical repository

The supported development/install surface documented here is the standalone `James3014/nexus-core` repository. Do not assume that an unqualified public package-index project named `nexus-core` is this repository.

```bash
git clone https://github.com/James3014/nexus-core.git
cd nexus-core
uv sync
uv run nexus-certify --help
```

`nexus-core` owns the canonical `product` package and `nexus-certify` console script.

### 2. Submit a Certification Request

```bash
# Submit a canonical certification request to the local HTTP runtime
uv run nexus-certify submit --request request.json --url http://127.0.0.1:8767
```

### 3. Query Status and Retrieve Receipts

```bash
# Query status of a running or completed request
uv run nexus-certify status <REQUEST_ID>

# Retrieve the tamper-evident certification receipt
uv run nexus-certify receipt <REQUEST_ID>
```

### 4. Verify a Receipt

```bash
# Verify receipt integrity and cryptographic provenance
uv run nexus-certify verify --receipt receipt.json
```

## 🔌 Client Interfaces

- **CLI (`nexus-certify`)**: Scriptable command-line interface for local operators and shell pipelines.
- **MCP Adapter (`product.clients.mcp`)**: Host-projected Model Context Protocol library adapter (`nexus_certify`).
- **GitHub Action (`.github/actions/nexus-certify`)**: Thin action wrapper designed for self-hosted GitHub runners.

### Canonical Core Action binding

The Action requires `core-python`, an absolute executable path to a
pre-provisioned isolated `nexus-core` virtual environment. Provision the exact
Core wheel before invocation and record its SHA-256. The Action shell guard
rejects empty, relative, missing, directory, or non-executable paths, then
validates the installed `nexus-core` distribution, exact Action module path and
`RECORD` hash before reading the token. It also rejects `nexus-legacy`
co-installation in that Action interpreter. Existing self-hosted-runner,
loopback, request, token, and receipt-output semantics remain unchanged. This
binds the Action to canonical Core; it does not make the MCP library a native
MCP server or change the legacy integration-lab CLI.

## 🧪 Legacy Orchestration & Lab Surfaces

The legacy integration host is this repository and has separate package ownership from canonical Core:

- distribution: `nexus-legacy`;
- packaged namespaces: `nexus` and `scripts`;
- legacy console script: `nexus`;
- optional dependency group for historical orchestration/lab dependencies: `legacy`.

This README does **not** claim that `nexus-legacy` is published under a public package-index name. Install it from a checked-out `Nexus-new` source tree. Use a separate virtual environment for legacy/lab work so its larger optional dependency set stays isolated from the canonical Core development environment.

```bash
git clone https://github.com/James3014/Nexus-new.git
cd Nexus-new
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[legacy]"
nexus --help
```

Current package/console ownership is intentionally distinct: canonical `nexus-core` owns `product` and `nexus-certify`; `nexus-legacy` owns `nexus`/`scripts` and the `nexus` CLI. The GitHub Action remains stricter and must use its isolated Core interpreter as described above.

## 🗺️ Navigation

- **[Project Index (docs/INDEX.md)](docs/INDEX.md)**: Architecture and specification roadmap.
- **[Testing Runbook (docs/testing/test_runbook.md)](docs/testing/test_runbook.md)**: CI gates and local verification.
- **[Module Inventory (docs/arch/module-inventory.md)](docs/arch/module-inventory.md)**: Generated audit of 85+ packages.
