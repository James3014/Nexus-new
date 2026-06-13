# Nexus v28.3.0 Autonomic Governance

Nexus is a high-performance orchestration layer for autonomous AI development. It wraps Large Language Models in a verifiable audit trail and self-healing execution pipelines to ensure engineering reliability.

## 🏟️ Overview

Nexus manages the full **P-X-D-R-A-C** lifecycle (Plan, Execute, Diagnose, Research, Audit, Crystallize) to transform raw model outputs into auditable software artifacts.

### 🛡️ Current Verified Gates
- **Pytest Collect (P0)**: Automated discovery of 4246 test items.
- **Enterprise Audit (P1)**: Machine-verifiable isolation and hallucination checks (`nexus status`).
- **PR-Safe Lint (P1)**: Quality enforcement on changed files via Ruff.

## 🏆 Core Capabilities (Beta)

- **Verifiable Audit Trails**: Decisions and tool calls are recorded in structured JSONL receipts.
- **Self-Healing Pipelines**: Automated diagnosis of execution failures with policy-based retry.
- **Governance Gates**: Multiple layers of validation to prevent regressions (governance gates; some are conceptual or beta).

## 🚀 Quick Start

```bash
# 1. Align environment
bash scripts/ops/_nexus_preflight.sh

# 2. Verify system status and run baseline audit
uv run nexus status

# 3. Execute an autonomous task
uv run nexus run --task "your task description"
```

## 🗺️ Navigation

- **[Project Index (docs/INDEX.md)](docs/INDEX.md)**: Architecture and roadmap.
- **[Testing Runbook (docs/testing/test_runbook.md)](docs/testing/test_runbook.md)**: CI gates and local verification.
- **[Module Inventory (docs/arch/module-inventory.md)](docs/arch/module-inventory.md)**: Generated audit of 85+ packages.

Current Maturity: **Beta**. Suitable for verification-oriented R&D teams.
