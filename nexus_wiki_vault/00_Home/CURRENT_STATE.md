---
title: Nexus Current State
type: current-state
status: active
lifecycle: current
authority: operational
owner: nexus-core
verified_at: '2026-07-13'
verified_against_commit: 957cd19c744d168ff050667b611adca5fb20d56f
source_of_truth: repository evidence and current runtime reports
confidence: high
---

# Nexus Current State

## 1. Current identity

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
| Local pipeline (topology/executor/verifier/receipt) | RUNTIME_INVOKED | Benchmark scripts only | Not exposed via Canonical CLI | `nexus/engine/` |
| A/B uplift measurement | BENCHMARK_VERIFIED | Benchmark harness | Verification instrument only | `capability_ab_runner.py` |
| Candidate isolation | CONTRACT_VERIFIED | LocalModelExecutor | Benchmark path only | `nexus/core/` |
| Claim verification | CONTRACT_VERIFIED | LocalModelExecutor | Benchmark path only | `nexus/core/` |

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
| verified_against_commit | 957cd19c744d168ff050667b611adca5fb20d56f |
| source_of_truth | repository evidence and current runtime reports |
| confidence | high |
