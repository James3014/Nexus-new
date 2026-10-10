---
title: Nexus Current State
type: current-state
status: active
lifecycle: current
authority: operational
owner: nexus-core
verified_at: '2026-07-13'
content_verified_against_commit: a2ae57ab96a9ddb0243858f4f2c1776709511af5
document_updated_in_commit: fecda71e417c453a7ea2ae0229478784921c362a
source_of_truth: repository evidence and current runtime reports
confidence: mixed
---

# Nexus Current State

> **Freshness notice (2026-10-08):** The source-bound snapshot below supersedes the 2026-07-13 architecture/status narrative for present-day navigation. The retained legacy sections are historical observations, not a live-system readiness verdict. Do not promote commit, CI or documentation evidence into runtime or acceptance truth.

## Current repository evidence (2026-10-08, source-only)

The following are exact observed default-branch revision identities, **not** claims of deployment, continuous readiness, independent acceptance or production certification. Nexus spans separately governed repositories; each must be checked at its own revision.

| Repository | Observed main (2026-10-08) | Evidence boundary |
|---|---|---|
| `James3014/Nexus-new` | `55d4a49f9e1777d453c076eab09203a51477d4b6` | Governance/collaboration and compatibility host; source revision only |
| `James3014/nexus-core` | `663cd72c0879907bbf029b5d25a37abbdae36118` | Evidence Trust and Completion; source revision only |
| `James3014/nexus-learning` | `0f6ec13a9a4ec4c1093424abad1a02c806eaf84e` | Evidence-bounded learning; source revision only |
| `James3014/nexus-open-swe-runtime` | `8cc747b0bc548106e32cff9973ae87a93e4b0504` | External execution runtime repository; source revision only |
| `James3014/devspace` | `a3103fab6ca9afe3e81a13f2885e68996136825d` | Independent host/control transport; source revision only |

The Nexus-new repository's current `AGENTS.md` is the agent-operation authority. Its `docs/governance/current_operating_mode.yaml` defines the BOOTSTRAP engineering-lane default in its declared scope; it does **not** authorize routing, worker admission, acceptance, merge or release. The `CapabilityPlanner` remains sole Nexus route/capability authority. The Core and Learning repositories are separate authorities for their declared functions, not implicit proof that the legacy three-world overview below remains current.

**Evidence ceiling:** source identities and current repository contracts observed on 2026-10-08. Runtime deployment identity, heartbeat/readiness, complete cross-repository wiring and independent acceptance have **not** been reverified for this page. Any claimed live status requires separate current evidence.

## Historical architecture snapshot (verified 2026-07-13)

The following sections document the July 2026 three-world interpretation and v32.x assumptions. They remain for traceability only. Their paths, blockers, wiring conclusions and promotion gates must not be presented as current without checking present source and runtime.

## 1. Historical identity (July 2026)

Nexus is an AI Agent governance operating system built around a physical-integrity P-X-D-R-A-C lifecycle. It provides governance, tool isolation, evidence collection, and claim verification for AI swarms.

## 2. Current architecture model

Nexus operates across three independent execution worlds. They are **not** integrated into a single runtime.

## 3. Three execution worlds

### World A: Agent-Operated Nexus (governance wearing)

- **Entry**: `enforced.sh` -> Gemini CLI -> Nexus CLI
- **Purpose**: Daily development governance
- **Proven**: Governance briefing, startup gate, operational rules, agent-facing CLI tools exist and are functional
- **Not proven**: Automatic local assist injection, local model context injection into online agent path
- **Status**: Governance wearing proven. The agent remains the long-task controller.

### World B: Benchmark A/B Harness (verification instrument)

- **Entry**: `capability_ab_runner.py` -> `LocalModelExecutor`
- **Purpose**: Prove whether Nexus produces uplift compared to bare baseline
- **Proven**: Bare vs Nexus comparison harness exists and runs
- **Not proven**: As a product runtime. World B is a **verification instrument**, not the canonical product runtime.
- **Critical**: World B results must not be cited as product runtime performance.

### World C: Local Armor / LocalModelExecutor (local pipeline)

- **Entry**: `LocalModelExecutor.run()` -> topology dispatch -> candidate/verifier/receipt
- **Purpose**: Local model execution with candidate isolation and verification
- **Proven**: Full local pipeline (topology, executor, candidate provider, verifier, receipt, ledger)
- **Not proven**: Daily CLI dispatch integration. Primary callers are benchmark scripts, not日常 CLI.
- **Status**: Benchmark runtime proven.

### Core gap

World A and World C have **no runtime bridge**. The Canonical CLI does not dispatch to LocalModelExecutor. Online agent path and local armor path are completely separated.

## 4. Proven capabilities

| Capability | Evidence level | Canonical caller | Current limitation | Source |
|------------|---------------|------------------|-------------------|--------|
| Governance briefing | RUNTIME_INVOKED | World A agent startup | Only within World A | `enforced.sh`, `nexus_cli.py` |
| Startup gate | RUNTIME_INVOKED | World A agent startup | World A only | `start_gemini_nexus_enforced.sh` |
| CLI tool surface | UNIT_VERIFIED | World A agent | Not wired to LocalModelExecutor | `scripts/nexus_cli.py` |
| Local pipeline (topology/executor/verifier/receipt) | RUNTIME_INVOKED | Benchmark scripts only | Not exposed via Canonical CLI | `nexus/services/local_heal/local_model_executor.py` |
| A/B uplift measurement | BENCHMARK_VERIFIED | Benchmark harness | Verification instrument only | `scripts/bench/capability_ab_runner.py` |
| Candidate isolation | CONTRACT_VERIFIED | LocalModelExecutor | Benchmark path only | `nexus/services/local_heal/isolated_local_solve_loop.py` |
| Claim verification | CONTRACT_VERIFIED | LocalModelExecutor | Benchmark path only | `nexus/services/local_heal/claim_delivery_gate.py` |

## 5. Not proven / restricted claims

- World A and World C are **not integrated**. No runtime bridge exists.
- Local assist injection into online agent path is **not proven**.
- Nexus as an autonomous solver is **not claimed**. Nexus is a context, policy, tool, and evidence layer worn by the model.
- Product runtime performance is **not proven** by benchmark results alone.
- Public benchmark uplift numbers must be qualified by suite, model, and methodology.

## 6. Current blockers

| Blocker | Impact |
|---------|--------|
| No Canonical CLI -> LocalModelExecutor dispatch bridge | General `nexus run` does not use local model execution |
| Online Agent Path and Local Armor Path fully separated | No automatic local assist for daily agent work |
| `cloud_with_local_assist` uses Fake Cloud | Contract exists but no real provider |
| No Agent-facing output contract for local assist | Missing assist envelope |
| No shared task lineage between control modes | Cannot trace local contribution |
| `benchmark_run` semantics are ambiguous | May cause misrouting |
| Local assist token/time savings cannot be measured at entry | Cannot prove ROI |

## 7. Current development mainline

The current development mainline is the v32.x series. Key recent work:
- v32.8: Removed legacy run seams, implemented Cold-Start Acceptance Policy
- v32.7: Service Mesh refactoring, engine split into 20+ microservices
- v32.6: Full alignment of `nexus/governance/` and `nexus/events/` physical relocation

## 8. Current operational paths

- **World A**: `enforced.sh` -> agent uses Nexus CLI for governance
- **World B**: `capability_ab_runner.py` for benchmark measurement
- **World C**: `LocalModelExecutor.run()` for local model pipeline

## 9. Next promotion gates

- Wire Canonical CLI to LocalModelExecutor (bridge World A and World C)
- Prove local assist injection in online agent path
- Establish shared task lineage across control modes
- Produce product runtime evidence (separate from benchmark)
- Complete public claim eligibility review

## 10. Evidence sources

- Repository code: `nexus/`, `scripts/`, `tests/`
- Runtime reports: `.nexus/reports/`
- Benchmark results: `benchmarks/`
- Architecture blueprint: `01_System/SYSTEM_ARCHITECTURE_BLUEPRINT.md`
- Learning closure: `06_Ops/Ops - Learning Closure Matrix.md`
- Code-to-Wiki alignment: `08_Diffs/Code_to_Wiki_Alignment_Matrix.md`

## 11. Last verification metadata

| Field | Value |
|-------|-------|
| verified_at | 2026-07-13 |
| content_verified_against_commit | a2ae57ab96a9ddb0243858f4f2c1776709511af5 |
| document_updated_in_commit | fecda71e417c453a7ea2ae0229478784921c362a |
| source_of_truth | repository evidence and current runtime reports |
| confidence | high |
