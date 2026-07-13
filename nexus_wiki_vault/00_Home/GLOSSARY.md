---
title: Glossary
type: normative
status: active
lifecycle: current
authority: normative
owner: nexus-core
verified_at: '2026-07-13'
verified_against_commit: 957cd19c744d168ff050667b611adca5fb20d56f
source_of_truth: repository evidence and current runtime reports
confidence: high
---

# Glossary

Canonical definitions for key Nexus terms. Each entry states what the term means, what it is NOT the same as, where it comes from, and any legacy aliases.

---

### Nexus

**Definition**: An AI Agent governance operating system that enforces a physical-integrity P-X-D-R-A-C lifecycle for AI swarms.

**Not the same as**: An AI model, a chatbot, a standalone tool.

**Code/document source**: `nexus/`, `nexus_wiki_vault/01_System/SYSTEM_ARCHITECTURE_BLUEPRINT.md`

**Legacy aliases**: Nexus OS, Nexus Swarm, Singularity OS

---

### Battlesuit

**Definition**: The metaphor for Nexus as a wearable governance layer. Any AI model "wearing" Nexus gains governance, tool isolation, evidence collection, and claim verification.

**Not the same as**: An AI model, a standalone application.

**Code/document source**: `nexus_wiki_vault/00_Home/System Overview.md`

**Legacy aliases**: Singularity, War Suit

---

### World A

**Definition**: Agent-Operated Nexus. The daily development governance path where an AI agent uses Nexus CLI for governance briefing, startup gates, and operational rules. Entry via `enforced.sh` -> Gemini CLI -> Nexus CLI.

**Not the same as**: World B (benchmark), World C (local model), product runtime.

**Code/document source**: `nexus_wiki_vault/01_System/SYSTEM_ARCHITECTURE_BLUEPRINT.md` section 16.2

**Legacy aliases**: Online Agent Path, Governance Wearing Path

---

### World B

**Definition**: Benchmark A/B Harness. A verification instrument that compares bare model performance vs. Nexus-wearing performance. Entry via `capability_ab_runner.py` -> `LocalModelExecutor`.

**Not the same as**: Product runtime, World A, World C. World B is a measurement tool, not the product.

**Code/document source**: `nexus_wiki_vault/01_System/SYSTEM_ARCHITECTURE_BLUEPRINT.md` section 16.3

**Legacy aliases**: Benchmark Path, A/B Harness

---

### World C

**Definition**: Local Armor / Local Model Executor. The local model execution path with topology dispatch, candidate isolation, verifier, and receipt. Primary callers are benchmark scripts.

**Not the same as**: World A (agent path), World B (benchmark), Canonical CLI dispatch.

**Code/document source**: `nexus_wiki_vault/01_System/SYSTEM_ARCHITECTURE_BLUEPRINT.md` section 16.4

**Legacy aliases**: Local Armor Path, LocalModelExecutor Path

---

### Path

**Definition**: A specific execution route through Nexus (e.g., World A path, World B path, World C path). Each path has its own entry point, components, and evidence requirements.

**Not the same as**: A file system path, a route, a topology.

**Code/document source**: `nexus_wiki_vault/01_System/SYSTEM_ARCHITECTURE_BLUEPRINT.md` section 16

**Legacy aliases**: (none)

---

### Route

**Definition**: A decision-level selection within a path (e.g., which capabilities to invoke, which skills to use). Routes are selected by CapabilityPlanner and SkillsRouter.

**Not the same as**: A path (route is a decision within a path), a topology.

**Code/document source**: `nexus/engine/capability_planner.py`, `scripts/core/skills_router.py`

**Legacy aliases**: Capability Route

---

### Topology

**Definition**: The structural arrangement of components within a path (e.g., sequential, parallel, candidate-verified). Topology determines how candidates, verifiers, and receipts are composed.

**Not the same as**: A route (topology is the structure, route is the decision), a path.

**Code/document source**: `nexus/services/local_heal/local_model_executor.py`

**Legacy aliases**: LocalModelExecutor, Local Armor Executor

---

### Committee

**Definition**: A multi-agent governance body that reviews and votes on proposals. Committees provide collective decision-making for high-impact changes.

**Not the same as**: The Verifier (committee decides, Verifier checks), the Claim Gate (committee governs, Claim Gate validates evidence).

**Code/document source**: `nexus/services/local_heal/committee_orchestrator.py`

**Legacy aliases**: Consensus Guard, Governance Committee

---

### Candidate isolation

**Definition**: The mechanism that ensures different solution candidates are evaluated independently without cross-contamination. Enforced by the Candidate Isolation Gate.

**Not the same as**: Verifier (isolation prevents contamination, Verifier checks outcome), sandbox (isolation is about candidate independence, sandbox is about execution safety).

**Code/document source**: `nexus/services/local_heal/isolated_local_solve_loop.py`

**Legacy aliases**: (none)

---

### Verifier

**Definition**: The component that validates artifacts against contracts and evidence requirements. Part of the Audit phase.

**Not the same as**: Claim Gate (Verifier checks artifacts, Claim Gate evaluates claims), LocalHeal (Verifier validates, LocalHeal repairs).

**Code/document source**: `nexus/services/local_heal/isolated_verifier.py` (World C) / `nexus/verifiers/` (domain verifiers)

**Legacy aliases**: ReceiptVerifier, ArtifactVerifier

---

### Receipt

**Definition**: A structured record of what was executed, what evidence was produced, and what outcome was achieved. Receipts are the physical evidence trail.

**Not the same as**: A claim (receipt is evidence, claim is the assertion), a report (receipt is machine-readable, report is human-readable).

**Code/document source**: `nexus/core/receipt_causality_contract.py` / `nexus/evidence/abort_receipt.py`

**Legacy aliases**: Evidence Receipt, Execution Receipt

---

### Claim gate

**Definition**: The mechanism that validates whether a claim meets the required evidence threshold before it can be made at a given level. See CLAIM_TAXONOMY.

**Not the same as**: Verifier (claim gate evaluates claim level, Verifier checks artifact correctness), Claim Taxonomy (taxonomy defines levels, gate enforces them).

**Code/document source**: `nexus/services/local_heal/claim_delivery_gate.py`

**Legacy aliases**: Claim Verifier, Evidence Gate

---

### Benchmark

**Definition**: A reproducible measurement of Nexus performance, typically comparing bare model vs. Nexus-wearing model on a defined task suite.

**Not the same as**: Product runtime performance, production capability, public claim.

**Code/document source**: `scripts/bench/`, `nexus/benchmark/`

**Legacy aliases**: A/B Benchmark, Capability Benchmark

---

### Product runtime

**Definition**: The actual execution environment where Nexus serves end users. Distinct from benchmark harness and development/test environments.

**Not the same as**: Benchmark runtime, test runtime, development runtime.

**Code/document source**: `nexus_wiki_vault/00_Home/CURRENT_STATE.md`

**Legacy aliases**: (none)

---

### Production ready

**Definition**: Meets all reliability, security, and operational requirements for production deployment. Requires evidence beyond product runtime verification.

**Not the same as**: Product runtime verified (production ready includes security, load testing, monitoring), public claim allowed (production ready is technical, public claim is communication).

**Code/document source**: `nexus_wiki_vault/01_System/CLAIM_TAXONOMY.md`

**Legacy aliases**: Deploy ready, Release ready

---

### Public claim allowed

**Definition**: The claim has been reviewed and approved for external public communication. Requires explicit governance approval.

**Not the same as**: Production ready (public claim is communication approval, production ready is technical readiness), benchmark verified (benchmark is measurement, public claim is communication).

**Code/document source**: `nexus_wiki_vault/01_System/CLAIM_TAXONOMY.md`

**Legacy aliases**: (none)
