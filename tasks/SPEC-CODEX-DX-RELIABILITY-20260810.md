# Codex Repository Success Product Specification

- **Spec ID:** `SPEC-CODEX-DX-RELIABILITY-20260810`
- **Status:** `READY_FOR_TASK_CARDS`
- **Basis snapshot:** `/Users/jameschen/Workspace/nexus`; canonical branch `codex/ci-0-truthful-gates`; HEAD `b6601270edd95a756c4eab8c7a623006ee1b32d1`; refresh snapshot `c676fc82c3e5ebbd6c3a5fbb77189eed09157ad70bfebd4e8ebdca1a94227c52`; concurrent linked-worktree drift present
- **Supersedes:** `none`
- **Claim ceiling:** owner-approved brownfield implementation contract; no implementation, benchmark lift, Candidate approval, integration, release, or production claim

## 1. Problem statement

New Codex sessions do not have one reliable, portable path to understand, set up, test, and modify Nexus. Recent GitHub evidence and local probes show missing dependencies and fixtures, machine-specific paths, secret assumptions, conflicting commands, an unusable benchmark entrypoint, skipped full regression, and costly context discovery. Codex app history is currently unavailable, so task-history coverage is explicitly incomplete.

## 2. Desired outcome

A fresh Codex session SHALL be able to locate authority, prepare a secrets-free core development environment, select and run the correct tests, make a bounded fixture-backed change, and verify it without human repair. A reproducible paired benchmark SHALL measure the before/after difference.

## 3. Basis, coverage, and freshness

- Owner objective and the instruction to use Luna workers are current binding decisions.
- Canonical checkout HEAD, index, and 46-entry pre-existing untracked manifest stayed unchanged during the latest refresh.
- Linked worktrees are actively changing: issue16 topology changed and issue29 advanced during observation. Repository-wide current-state claims are therefore snapshot-limited.
- Prior GitHub inventory observed 20 PRs: 18 merged and 2 open. GitHub/DNS was unavailable during the latest refresh, so those counts are historical rather than confirmed-current.
- Codex app `list_threads` returned no payload in two turns. Recent task coverage is zero/unknown.
- Live local probes reproduced the missing benchmark entrypoint and uv home-cache permission failure. A temporary uv cache allowed the CLI help probe to pass.

## 4. Source and decision ledger

| ID | Class | Statement | Authority/location | Freshness/snapshot | Status | Limitation |
|---|---|---|---|---|---|---|
| DEC-001 | DEC | Treat Codex success in this repository as a product and improve instructions, skills, scripts, fixtures, setup, tests, documentation, and before/after benchmarking. | Owner objective | current turn | BINDING | none |
| DEC-002 | DEC | Use Luna workers extensively for bounded parallel evidence work. | Owner message | current goal | BINDING | primary agent retains authority |
| DEC-003 | DEC | Approve the proposed specification and continue without stopping while unavailable task history remains explicitly unclaimed. | Owner message `都同意，不要停` | current turn | BINDING | missing history remains required before final completion |
| DEC-004 | DEC | Use a clean isolated governed Target rather than waiting for unrelated linked worktrees to stop. | Owner approval plus root governance | current turn | BINDING | canonical dirty state remains untouched |
| CON-001 | CON | Cross-subsystem or delegated mutation requires governed Task Cards; direct work may not widen into this scope. | root AGENTS.md | HEAD b6601270e | BINDING | execution remains separate |
| CUR-001 | CUR | `scripts/ci/run_swebench_subset.py` discovers five smoke cases but all error because `nexus_benchmark.sh` is absent. | local 0/5 probe | HEAD b6601270e | EVIDENCE | fixture/simulation only |
| CUR-002 | CUR | `scripts/ops/ci_smoke_test.py` resolves the wrong root and hardcodes a user-specific uv executable. | current source | HEAD b6601270e | EVIDENCE | static evidence |
| CUR-003 | CUR | README preflight requires Node, Gemini, uv, and user-specific macOS paths before an ordinary core CLI smoke. | README and `_nexus_preflight.sh` | HEAD b6601270e | EVIDENCE | static evidence |
| CUR-004 | CUR | Local Python is 3.14.6; CI uses 3.11 and 3.12; no repository interpreter pin exists. | local/version/workflow inspection | refresh snapshot | EVIDENCE | one machine plus current source |
| CUR-005 | CUR | CONTRIBUTING, README, OpenWiki, test scripts, and testing runbook expose conflicting or stale verification commands. | current source | HEAD b6601270e | EVIDENCE | targeted files only |
| CUR-006 | CUR | The relevant broad discovery surface is about 6.9 MB and contains 156 skill files without a single machine-readable Codex task-to-context index. | bounded inventory | HEAD b6601270e | EVIDENCE | size is not quality proof |
| HIS-001 | HIS | PR 1 failed pytest collection on missing `jsonschema`, recorded missing artifacts/secrets debt, and exposed 10,141 Ruff baseline errors. | GitHub PR 1 artifact audit | 2026-08-10 prior snapshot | CONTEXT_ONLY | GitHub currently unavailable |
| HIS-002 | HIS | PR 41 showed an environment-sensitive executable path and repeated repair/merge cycles; most observed PRs skipped Tier 3 full regression. | GitHub PR audit | 2026-08-10 prior snapshot | CONTEXT_ONLY | status may have changed |
| CUR-007 | CUR | Recent Codex app task inventory, task-level failures, and human-intervention counts are unavailable because the task-history transport hangs. | Codex app transport | three consecutive goal turns | EVIDENCE | zero task coverage; cannot support final completion |
| CUR-008 | CUR | Linked issue worktrees continue moving while the canonical checkout itself remains stable. | repo snapshot comparison | current refresh | EVIDENCE | execution must use a clean isolated Target |
| DER-001 | DER | A small canonical machine-readable developer surface is preferable to adding another broad narrative document. | DEC-001, CUR-005, CUR-006 | current derivation | EVIDENCE | owner review required |

## 5. Current verified state

- Core onboarding and test guidance is physically present but internally inconsistent (`CUR-003`, `CUR-005`).
- The scheduled benchmark path is not runnable at its first subprocess seam (`CUR-001`).
- One legacy smoke script is non-portable (`CUR-002`).
- Environment and context selection are underspecified (`CUR-004`, `CUR-006`).
- GitHub and Codex app history cannot currently support a complete recent-task inventory (`HIS-001`, `HIS-002`, `CUR-007`).

## 6. Owner decisions

- `DEC-001`: improve Codex success as an end-to-end repository product, not a docs-only exercise.
- `DEC-002`: use Luna workers for bounded evidence and execution packets while preserving primary-agent acceptance authority.

## 7. Canonical terminology

- **Core setup:** environment sufficient for repository orientation, static checks, fixture-backed tests, and bounded changes without provider credentials.
- **Provider setup:** optional Gemini/OpenAI/local-model runtime requiring explicit dependencies or credentials.
- **First-pass success:** task-specific verifier passes without human correction, command substitution, undocumented secret, or environment repair.
- **Human intervention:** any user message needed to supply a command, path, fixture, secret, convention, or recovery step absent from the task and canonical developer surface.
- **Context cost:** bytes/items read before the first correct test command and before a verified patch.

## 8. Change delta

Mode: BROWNFIELD

Baseline: current onboarding, scripts, workflows, fixtures, skills, and governance at canonical HEAD `b6601270e`, plus the bound historical GitHub audit.

### ADDED

- Add a canonical Codex developer contract, portable doctor/setup surface, task-to-test/context index, failure-history inventory contract, and paired fresh-session benchmark.

### MODIFIED

- Modify setup from provider-first and host-specific to core-first and portable.
- Modify test guidance from multiple conflicting commands to one canonical command matrix.
- Modify benchmark execution from a missing shell dependency to a checked-in, fixture-backed, fail-closed entrypoint.
- Modify Codex instructions and skills so retrieval is task-bounded and benchmarked.

### REMOVED

- Remove or redirect obsolete CLI/test commands, personal executable paths, implicit core secret requirements, and unsupported readiness claims from current developer guidance.

### RENAMED

- No behavior-preserving renames are required. Any renamed command must retain an explicit compatibility/deprecation path or be recorded as a modification.

## 9. Scope

- Root and nearest relevant `AGENTS.md` instruction surfaces.
- Existing Nexus/Codex skills needed for setup, test selection, diagnosis, and completion verification.
- Portable setup/doctor/test/benchmark scripts.
- Deterministic core fixtures and fixture validation.
- README, CONTRIBUTING, testing runbook, and derived navigation redirects.
- CI parity, secret classification, failure inventory, and paired benchmark artifacts.

## 10. Non-goals

- Changing CapabilityPlanner, route authority, lifecycle semantics, workforce admission, production release, or model-provider policy.
- Making provider credentials mandatory for core development.
- Cleaning or absorbing unrelated untracked benchmark work.
- Claiming all historical Codex tasks were analyzed while the `CUR-007` coverage limitation remains.
- Self-approving, integrating, pushing, or releasing the eventual Candidate.

## 11. User and operator stories

1. A fresh Codex session identifies its authority and relevant subsystem without scanning the full docs/skills corpus.
2. It prepares and diagnoses a core environment without requiring Gemini, Node, API keys, or access to a user's home uv cache.
3. It selects the cheapest correct test for a bounded change and can discover the escalation to full verification.
4. It completes a deterministic fixture-backed modification and reports exact evidence without touching unrelated state.
5. An owner can compare immutable before and after arms and see failures, interventions, context cost, and verifier truth.

## 12. Architecture and authority boundaries

Root `AGENTS.md` remains repository authority. The new developer contract and index are subordinate navigation and executable verification surfaces, not a second router or verifier. Existing test/CI commands remain behavior witnesses. GitHub and Codex history ingestion is read-only. Implementation must use one approved campaign with one frontier and `AUTO_CHAIN=false`; Candidate, approval, integration, push, and release remain separate.

## 13. Requirements

### REQ-001 — Evidence-complete failure inventory

- **Status:** `SETTLED`
- **Source:** `DEC-001, DEC-003, DEC-004, HIS-001, HIS-002, CUR-007, CUR-008`
- **Behavior:** The audit system SHALL inventory all discoverable recent Codex tasks and GitHub PR/check failures with source identity, cutoff, denominator, category, recurrence, human-intervention count, and coverage ceiling.
- **Failure behavior:** It SHALL report incomplete transport or snapshot drift and SHALL NOT convert unavailable history into zero failures.
- **Rationale:** Prevents anecdotal prioritization and false completeness.
- **Authority/interface:** read-only audit input
- **Non-goal linkage:** section 10

### REQ-002 — Canonical bounded context entry

- **Status:** `DERIVED`
- **Source:** `DEC-001, CUR-005, CUR-006, DER-001`
- **Behavior:** The repository SHALL expose one compact machine-readable task-to-authority, task-to-context, and task-to-test index consumed by Codex-facing instructions and skills.
- **Failure behavior:** Missing or stale mappings SHALL fail validation and SHALL NOT trigger broad corpus scanning as a silent fallback.
- **Rationale:** Reduces retrieval cost and undocumented convention failures.
- **Authority/interface:** AGENTS, skills, developer index
- **Non-goal linkage:** section 10

### REQ-003 — Portable core developer setup

- **Status:** `SETTLED`
- **Source:** `DEC-001, CUR-002, CUR-003, CUR-004`
- **Behavior:** Core setup SHALL pin or constrain a tested Python version, isolate uv cache state, discover executables through PATH, install locked core/dev dependencies, and run without provider credentials or personal absolute paths.
- **Failure behavior:** The setup doctor SHALL identify the exact missing binary, dependency, cache permission, unsupported interpreter, or optional provider requirement and SHALL exit non-zero on core blockers.
- **Rationale:** Removes recurring environment repair.
- **Authority/interface:** setup and doctor scripts
- **Non-goal linkage:** provider setup definition

### REQ-004 — Explicit secret boundary

- **Status:** `SETTLED`
- **Source:** `DEC-001, CUR-003, HIS-001`
- **Behavior:** Core tests and benchmarks SHALL run without API secrets; provider-only commands SHALL declare every required secret, permitted data use, local fallback, and skip/fail semantics.
- **Failure behavior:** Missing optional secrets SHALL produce an explicit skip or provider-disabled result; missing required provider secrets SHALL fail before work begins without exposing secret values.
- **Rationale:** Prevents hidden credential assumptions and accidental leakage.
- **Authority/interface:** environment template, doctor, workflows, docs
- **Non-goal linkage:** section 10

### REQ-005 — Canonical test command matrix

- **Status:** `SETTLED`
- **Source:** `DEC-001, CUR-001, CUR-002, CUR-005`
- **Behavior:** The repository SHALL provide documented, executable commands for environment check, fast core tests, changed-file impact tests, full regression, lint, and fixture validation, with the same entrypoints used by CI where practical.
- **Failure behavior:** Empty selections, missing test paths, missing fixtures, malformed commands, or skipped required tiers SHALL fail closed with an actionable message.
- **Rationale:** Makes correct verification discoverable and reproducible.
- **Authority/interface:** scripts, test runbook, CI
- **Non-goal linkage:** none

### REQ-006 — Deterministic fixture-backed smoke benchmark

- **Status:** `SETTLED`
- **Source:** `DEC-001, CUR-001, HIS-001`
- **Behavior:** The five-case smoke benchmark SHALL use checked-in or deterministically materialized fixtures and a real checked-in execution entrypoint, and SHALL produce per-case verifier-bound results.
- **Failure behavior:** Missing runner, fixture, verifier, or source binding SHALL fail the suite before or at the affected case and SHALL NOT report synthetic health from process exit alone.
- **Rationale:** Repairs the current 0/5 first seam and prevents false green.
- **Authority/interface:** fixtures and benchmark scripts
- **Non-goal linkage:** production capability claims

### REQ-007 — Converged developer documentation

- **Status:** `SETTLED`
- **Source:** `DEC-001, CUR-003, CUR-005`
- **Behavior:** README, CONTRIBUTING, testing runbook, OpenWiki navigation, and relevant skills SHALL point to the canonical setup/test/index surfaces and distinguish authoritative from derived documentation.
- **Failure behavior:** A documentation command checker SHALL reject nonexistent paths, obsolete commands, personal absolute paths, and contradictory current instructions.
- **Rationale:** Eliminates instruction ambiguity.
- **Authority/interface:** developer documentation
- **Non-goal linkage:** historical archives

### REQ-008 — Paired fresh-session benchmark

- **Status:** `DERIVED`
- **Source:** `DEC-001, DEC-002, CUR-006, DER-001`
- **Behavior:** Before and after arms SHALL each run three independent fresh Codex sessions across orientation, setup, focused-test, bounded-change, and verification tasks against immutable source snapshots, for 15 trials per arm.
- **Failure behavior:** Reused context, mutable source, human repair, unavailable metrics, verifier mismatch, or arm-specific fixtures SHALL invalidate the affected trial rather than count it as pass.
- **Rationale:** Measures product effect rather than prose quality.
- **Authority/interface:** benchmark harness and receipts
- **Non-goal linkage:** public benchmark claims

### REQ-009 — Benchmark success and regression gate

- **Status:** `DERIVED`
- **Source:** `DEC-001, CUR-001, CUR-006`
- **Behavior:** The after arm SHALL achieve 15 of 15 verifier-confirmed task passes, zero human interventions, zero secret reads, zero unauthorized/destructive actions, and no increase in median context bytes when compared with the immutable before arm.
- **Failure behavior:** Any missing receipt, false-green verifier result, safety violation, or metric regression SHALL block the success claim and preserve the failing trial evidence.
- **Rationale:** Operationalizes reliable work with minimum assistance.
- **Authority/interface:** benchmark acceptance gate
- **Non-goal linkage:** production/public claims

### REQ-010 — Durable failure regression feedback

- **Status:** `SETTLED`
- **Source:** `DEC-001, CON-001, HIS-001, HIS-002`
- **Behavior:** Each admitted recurring failure class SHALL map to a stable automated check, fixture, command contract, or bounded instruction rule with owner, evidence, and removal condition.
- **Failure behavior:** Novel failures without a validated recurrence or prevention seam SHALL remain evidence entries and SHALL NOT cause uncontrolled AGENTS, skill, or report growth.
- **Rationale:** Prevents repeated mistakes without accumulating instructions indefinitely.
- **Authority/interface:** CI, skills, learning write-back
- **Non-goal linkage:** routine report creation

## 14. Behavioral and interface decisions

- One `core` lane is secrets-free; provider lanes are explicit opt-ins.
- One doctor command returns structured category/status/remediation data plus human-readable output.
- One test command matrix maps task/path classes to stable commands and escalation tiers.
- One context index contains authority, nearest nested authority, setup, tests, fixtures, and forbidden scope; prose links consume it rather than duplicate it.
- Benchmark receipts bind arm, source snapshot, fresh session, task fixture, commands, context bytes/items, tool calls, wall time, human interventions, secret access, diff scope, verifier, and outcome.

## 15. Verification seam

Highest seam is an isolated clean-checkout paired Codex-session benchmark with task-specific deterministic verifiers. Static schema checks, shell syntax, focused pytest, workflow validation, secret scans, and fixture checks are necessary lower seams. No report or process return code alone proves success.

## 16. Acceptance criteria

### AC-001 — History coverage receipt

- **Requirement:** `REQ-001`
- **Evidence level:** `BENCHMARK`
- **Verification seam:** bounded Codex app and GitHub inventory collector
- **Pass:** every returned item is classified and denominators, cutoff, source identity, and missing coverage are recorded.
- **Negative control:** disable one transport and verify the result becomes incomplete rather than zero-failure complete.
- **Fail:** unavailable items are omitted without a coverage warning or task counts are inferred.
- **Receipt binding:** transport identities, cutoff, item IDs, and snapshot hash

### AC-002 — Context index correctness

- **Requirement:** `REQ-002`
- **Evidence level:** `STATIC`
- **Verification seam:** index validator plus representative task lookups
- **Pass:** every benchmark task resolves one authority path, bounded context set, test command, fixture policy, and forbidden scope.
- **Negative control:** remove a mapped test path and verify validation fails without broad fallback.
- **Fail:** a task requires full docs/skills scanning or resolves a nonexistent path.
- **Receipt binding:** index digest and source HEAD

### AC-003 — Clean core bootstrap

- **Requirement:** `REQ-003`
- **Evidence level:** `CANARY`
- **Verification seam:** clean isolated checkout with empty temporary uv cache and no provider environment variables
- **Pass:** documented setup and doctor complete on the pinned/tested interpreter and execute the core CLI/test smoke.
- **Negative control:** run with an unwritable cache and unsupported interpreter and verify precise non-zero diagnoses.
- **Fail:** a personal path, home-cache access, Gemini, Node, or API key is needed for core success.
- **Receipt binding:** source HEAD, interpreter, uv version, cache root, command log

### AC-004 — Secret classification

- **Requirement:** `REQ-004`
- **Evidence level:** `SIMULATION`
- **Verification seam:** environment-scrubbed core and provider command matrix
- **Pass:** core passes without secrets; provider cases explicitly skip or fail before execution according to declared policy.
- **Negative control:** inject sentinel secrets and verify logs/receipts redact values and core never reads them.
- **Fail:** core requests a secret or a provider command silently falls back.
- **Receipt binding:** environment-name manifest and redaction scan

### AC-005 — Test command truth

- **Requirement:** `REQ-005`
- **Evidence level:** `CANARY`
- **Verification seam:** execute every documented command in an isolated checkout and compare with CI entrypoints
- **Pass:** environment, fast, changed, full, lint, and fixture commands resolve and return truthful status.
- **Negative control:** supply a deleted test path, empty changed selection, and failing fixture; each must fail or select the documented fallback.
- **Fail:** any current command is nonexistent, silently empty, host-specific, or weaker than documented.
- **Receipt binding:** command matrix digest, source HEAD, exit codes, selected targets

### AC-006 — Five-case smoke truth

- **Requirement:** `REQ-006`
- **Evidence level:** `FIXTURE`
- **Verification seam:** `run_swebench_subset.py --mode smoke` against deterministic fixtures
- **Pass:** five of five cases execute through the checked-in runner and pass their case-specific verifier.
- **Negative control:** remove one fixture/runner/verifier in an isolated copy and verify a non-zero, correctly classified failure.
- **Fail:** any case errors, times out, uses undeclared network/secrets, or derives health solely from exit code.
- **Receipt binding:** case IDs, fixture hashes, runner hash, verifier outputs

### AC-007 — Documentation command audit

- **Requirement:** `REQ-007`
- **Evidence level:** `STATIC`
- **Verification seam:** documentation command/path checker
- **Pass:** all current developer commands and linked paths resolve to canonical surfaces; derived pages identify their authority ceiling.
- **Negative control:** reintroduce `scripts/nexus_cli.py` or a personal absolute path and verify failure.
- **Fail:** contradictory setup/test commands remain in current guidance.
- **Receipt binding:** checked-file manifest and source HEAD

### AC-008 — Paired benchmark integrity

- **Requirement:** `REQ-008`
- **Evidence level:** `BENCHMARK`
- **Verification seam:** 30 isolated fresh-session trials across immutable before/after snapshots
- **Pass:** all trials have complete arm/session/task/fixture/verifier/metric bindings and identical task semantics.
- **Negative control:** reuse a session or mutate one arm fixture and verify the trial is invalidated.
- **Fail:** arm identity, freshness, or metrics are missing or incomparable.
- **Receipt binding:** benchmark manifest, source SHAs, session IDs, fixture/verifier hashes

### AC-009 — Product success gate

- **Requirement:** `REQ-009`
- **Evidence level:** `BENCHMARK`
- **Verification seam:** paired benchmark aggregator with independent task verifiers
- **Pass:** after arm is 15/15, needs zero human interventions, reads no secrets, performs no unauthorized/destructive action, and median context bytes do not exceed before.
- **Negative control:** mark one failing verifier result as pass and verify aggregation rejects the arm.
- **Fail:** any threshold is missed or required metric is absent.
- **Receipt binding:** per-trial receipts and aggregate digest

### AC-010 — Recurrence prevention mapping

- **Requirement:** `REQ-010`
- **Evidence level:** `STATIC`
- **Verification seam:** failure-class-to-prevention registry validator
- **Pass:** every admitted recurring class maps to exactly one current prevention seam with owner and retirement condition.
- **Negative control:** add a duplicate narrative-only rule and verify validation rejects it.
- **Fail:** recurring failures lack a prevention seam or instructions grow without bounded evidence.
- **Receipt binding:** registry digest, linked test/fixture/command IDs

## 17. Traceability matrix

| Requirement | Sources | Delta | Acceptance | Evidence level | Claim ceiling | Task-card handoff group |
|---|---|---|---|---|---|---|
| REQ-001 | DEC-001, DEC-003, DEC-004, HIS-001, HIS-002, CUR-007, CUR-008 | ADDED | AC-001 | BENCHMARK | complete bounded inventory only | evidence-inventory |
| REQ-002 | DEC-001, CUR-005, CUR-006, DER-001 | ADDED | AC-002 | STATIC | index correctness | context-contract |
| REQ-003 | DEC-001, CUR-002, CUR-003, CUR-004 | MODIFIED | AC-003 | CANARY | portable core setup | core-bootstrap |
| REQ-004 | DEC-001, CUR-003, HIS-001 | MODIFIED | AC-004 | SIMULATION | secret boundary | core-bootstrap |
| REQ-005 | DEC-001, CUR-001, CUR-002, CUR-005 | MODIFIED | AC-005 | CANARY | command truth | test-contract |
| REQ-006 | DEC-001, CUR-001, HIS-001 | MODIFIED | AC-006 | FIXTURE | deterministic smoke | fixture-benchmark |
| REQ-007 | DEC-001, CUR-003, CUR-005 | MODIFIED | AC-007 | STATIC | current docs converge | docs-convergence |
| REQ-008 | DEC-001, DEC-002, CUR-006, DER-001 | ADDED | AC-008 | BENCHMARK | paired trial integrity | paired-benchmark |
| REQ-009 | DEC-001, CUR-001, CUR-006 | ADDED | AC-009 | BENCHMARK | bounded Codex DX lift | paired-benchmark |
| REQ-010 | DEC-001, CON-001, HIS-001, HIS-002 | ADDED | AC-010 | STATIC | mapped prevention seams | durable-feedback |

## 18. Evidence and claim ceiling

Static validation may prove structure and command/path consistency. Fixture and canary evidence may prove portable setup and deterministic smoke behavior. Only the paired fresh-session benchmark may prove bounded Codex DX improvement. No result authorizes Candidate approval, integration, release, production readiness, or a claim about unobserved historical tasks.

## 19. Rollback and failure handling

Each implementation card must be independently reversible. Preserve legacy command compatibility only where a current consumer exists; otherwise fail with a migration pointer. Benchmark failures preserve receipts. Setup changes must retain an explicit provider lane. Missing history or drifting snapshots remain recoverable blocks and never become zero counts. Unrelated dirty state is never cleaned, staged, or absorbed.

## 20. Documentation and learning write-back

Canonical developer instructions belong in one developer contract/index plus existing README, CONTRIBUTING, and testing runbook links. New repeated failures enter a bounded prevention registry only after recurrence and a machine-verifiable prevention seam are established. Historical evidence stays historical; do not create recursive reports.

## 21. Risks and unknowns

- `CUR-007`: Codex task-history transport prevents current task-level denominator and intervention analysis; this remains a final-completion requirement.
- `CUR-008`: concurrent linked-worktree changes require a clean isolated governed Target.
- The owner approved the derived 15/15 and context thresholds through `DEC-003`.
- Existing untracked benchmark files overlap the broad product area and require isolated governed targets rather than canonical mutation.
- A repaired benchmark must not accidentally become a production capability claim.

## 22. Unresolved owner decisions

None

`DEC-003` authorizes continued implementation with explicit incomplete-history labeling, and `DEC-004` selects a clean isolated governed Target. Missing task-history evidence remains a completion blocker, not an unresolved design decision.

## 23. Task-card handoff boundary

| Task group | Requirements | Acceptance | Observable outcome | Dependency seam | Verification seam | Maximum claim | Scope class | Minimum MCP profile | Known blocker |
|---|---|---|---|---|---|---|---|---|---|
| evidence-inventory | REQ-001 | AC-001 | complete bounded history receipt | working app/GitHub transports and stable cutoff | inventory negative control | coverage-bounded taxonomy | small | not applicable | none |
| context-contract | REQ-002 | AC-002 | one validated context/test index | approved index schema | static validator | bounded retrieval correctness | medium | not applicable | none |
| core-bootstrap | REQ-003, REQ-004 | AC-003, AC-004 | secrets-free portable setup/doctor | clean isolated Target | clean-cache canary | core setup canary pass | medium | not applicable | none |
| test-contract | REQ-005 | AC-005 | truthful command matrix | core bootstrap contract | isolated command canary | command truth | medium | not applicable | none |
| fixture-benchmark | REQ-006 | AC-006 | five deterministic smoke cases | test and fixture contracts | fixture negative control | fixture smoke 5/5 | medium | not applicable | none |
| docs-convergence | REQ-007 | AC-007 | current docs point to canonical surfaces | context/setup/test contracts | docs command audit | static convergence | wide-mechanical | not applicable | none |
| paired-benchmark | REQ-008, REQ-009 | AC-008, AC-009 | immutable before/after receipts | all product surfaces complete | 30 fresh-session trials | paired benchmark evidence only | medium | not applicable | none |
| durable-feedback | REQ-010 | AC-010 | recurring failures map to one prevention seam | failure inventory and after benchmark | registry validation | prevention mapping | small | not applicable | none |

## 24. Out of scope

No route/lifecycle/workforce authority change, no provider onboarding, no canonical dirty-tree cleanup, no direct main mutation, no PR merge, no Candidate approval, no release, and no broad claim that Nexus or Codex is generally production-ready.

## 25. Supersession and change history

Initial proposed specification derived from the owner objective, root governance, current source probes, prior GitHub evidence, and explicitly incomplete Codex task-history transport. It supersedes no approved specification. Future revisions must preserve these IDs or record explicit modifications and evidence freshness.
