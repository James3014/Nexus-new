# Open SWE Execution Productionization V1

- **Spec ID:** `SPEC-OPEN-SWE-EXECUTION-PRODUCTIONIZATION-V1`
- **Status:** `READY_FOR_TASK_CARDS`
- **Basis snapshot:** `James3014/Nexus-new@c00c299152599a87efd831c3e146ecadd8f8b21f`; Open SWE pilot Candidate `764333bcbed67e5b83870d5ceeb8e9d70f7e749f`; Open SWE `4bed1112362d4ce74db86e704329fda0f3412b69`; Deep Agents `0.7.6`; Repository Intelligence `v0.1.0@a8b9a00a6f3ea3e9ade0c6ef494d0fa88a2d73b2`; observed 2026-08-31.
- **Supersedes:** the proposed custom semantic/diagnosis/repair LLM graph portion of `RI Agent Automation V1`; no existing Nexus governance authority is superseded.
- **Claim ceiling:** this specification may authorize bounded productionization Candidates only; it does not prove activation, production readiness, OpenCLI retirement, merge/release authority, or portable sandbox readiness.

> **Corrective topology overlay — 2026-09-01:** A later Owner corrective handoff supersedes any interpretation in this historical specification that requires Nexus Core to host Deep Agents/Open SWE in-process or to own their dependency graph. The current binding topology is `Nexus thin typed client -> external nexus-open-swe-runtime process -> structured result/Candidate`, governed by `tasks/open-swe-execution-productionization-v1/OPEN_SWE_EXTERNAL_RUNTIME_CORRECTIVE_CONTRACT.md`. Historical Pilot/import mechanics and the one-time trusted dependency transition remain evidence/history, not production-topology authority. Open SWE remains non-default until a fresh activation decision after the corrective architecture is independently accepted.

## 1. Problem statement

Nexus already has durable External Intelligence orchestration, Task Card authority validation, queue/replay/reconciliation state, worker fanout, Candidate verification/closure, and GitHub controller boundaries. The remaining automation plan would otherwise duplicate semantic-review, diagnosis, and repair LLM graph runtime that Open SWE / Deep Agents can execute.

The replacement pilot proved a bounded real semantic -> diagnosis -> repair chain and a real GitHub canary without granting agent-side GitHub credentials or merge authority. The pilot also proved that upstream Open SWE reviewer defaults are too broad, while a Nexus-side graph factory can construct physically read-only reviewer/diagnosis graphs through public Deep Agents seams. The result is `PARTIAL_REPLACE`, not full replacement.

## 2. Desired outcome

Nexus SHALL use Open SWE / Deep Agents as an **external** optional execution runtime behind existing Nexus control-plane authority. Nexus SHALL communicate through a thin typed process/protocol client; Deep Agents/Open SWE graph/runtime internals and their provider dependencies SHALL remain outside the Nexus Core Python dependency/process domain. The initial productionized path SHALL be non-default, feature/config gated, preserve the OpenCLI control arm, and fail closed. Nexus SHALL continue to own RI, CapabilityPlanner routing, Workforce Admission, queue/replay/reconciliation, credential brokering, GitHub mutation, independent Candidate verification/acceptance, and merge/release authority.

## 3. Basis, coverage, and freshness

- GitHub `main` was freshly read on 2026-08-31 and remained `c00c299152599a87efd831c3e146ecadd8f8b21f`.
- Current-main source was read at `scripts/ops/external_intelligence_service.py::build_automation`, `nexus/services/external_intelligence.py`, and `nexus/services/external_intelligence_automation.py`.
- Current `build_automation()` constructs `ExternalIntelligenceSidecar` with `OpenCLIExternalIntelligenceTransport`; `ExternalIntelligenceAutomation` already owns durable automation state and separates semantic intelligence, fanout, closure, and publication preparation.
- Pilot Candidate `764333bcbed67e5b83870d5ceeb8e9d70f7e749f` has tree `77b10be6c19b89d3ffdcabbf46e7a6fd102a77eb` and final report SHA-256 `a5974e19995ba87aad6982e48fa9dd845a95ee842869f67e8e5d2012fd034b7b`.
- Independent re-verification on the exact Candidate, using Nexus verifier Python plus the pinned Open SWE environment site-packages, produced `45 passed, 1 skipped`, Ruff PASS, Pyright 0 errors/0 warnings, Bandit PASS, and `git diff --check` PASS.
- The first independent run proved a deployment-boundary signal: the canonical Nexus `.venv` does not contain `deepagents`; corrective architecture keeps that property and installs/pins Deep Agents/Open SWE dependencies in the dedicated external runtime dependency domain rather than in Nexus Core or via `/private/tmp`/ad-hoc `PYTHONPATH`.
- Pilot package identities: `deepagents 0.7.6`, `langchain-google-genai 4.3.2`, `langchain-core 1.5.2`, `google-genai 1.74.0`; Open SWE package `0.1.0`, MIT.
- GitHub PR #664 was independently re-read as closed, unmerged, with final head `06d4f27f8fc8b6ec2403d5c805105665698569c4`.
- Portable remote sandbox, crash recovery under Open SWE execution, and statistically meaningful reviewer-quality comparison remain unproven.

## 4. Source and decision ledger

| ID | Class | Statement | Authority/location | Freshness/snapshot | Status | Limitation |
|---|---|---|---|---|---|---|
| DEC-001 | Owner decision | Adopt the pilot verdict `PARTIAL_REPLACE`. | Owner conversation, 2026-08-31 | current | BINDING | Does not authorize activation or retirement. |
| DEC-002 | Owner decision | Stop rebuilding a parallel semantic/diagnosis/repair LLM graph runtime; use Open SWE / Deep Agents for that execution role. | Owner continuation of pilot plan | current | BINDING | Nexus adapters/control plane remain required. |
| DEC-003 | Owner decision | Keep RI, DevSpace dispatch, CapabilityPlanner, queue/replay, credential broker, GitHub controller, independent verification/acceptance, and merge/release authority in Nexus. | Owner-approved replacement map | current | BINDING | None. |
| DEC-004 | Owner decision | Productionize behind a non-default feature/config gate, retain OpenCLI control arm, and require repeated canaries plus portable sandbox acceptance before any default switch. | Owner-approved next action | current | BINDING | Exact canary count is derived below. |
| DEC-005 | Owner decision | No automatic merge/release authority is granted to Open SWE. | Existing Nexus boundary + Owner plan | current | BINDING | None. |
| CUR-001 | Current fact | GitHub main is `c00c299152599a87efd831c3e146ecadd8f8b21f`. | GitHub branch read | 2026-08-31 | EVIDENCE | Must re-read at task start. |
| CUR-002 | Current fact | `build_automation()` wires `OpenCLIExternalIntelligenceTransport` into `ExternalIntelligenceSidecar`; automation already owns state/reconcile/fanout/closure. | current-main source | `c00c299...` | EVIDENCE | Source may drift before implementation. |
| CUR-003 | Current fact | Pilot Candidate `764333bc...` independently re-runs with 45 PASS / 1 skip when pinned Open SWE packages are available. | isolated verifier worktree | 2026-08-31 | EVIDENCE | Live-only Seatbelt test remains separately scoped. |
| CUR-004 | Current fact | PR #664 is closed and unmerged at repaired head `06d4f27...`. | GitHub PR read | 2026-08-31 | EVIDENCE | One canary only. |
| CUR-005 | Current fact | Nexus `.venv` lacks `deepagents`; the Pilot used a separate pinned environment. | fresh verifier | 2026-08-31 | EVIDENCE | Packaging must be solved before production-shaped use. |
| CUR-006 | Current fact | Pilot-qualified reviewer/diagnosis graphs physically exclude write/execute/task/HTTP; repair uses bounded Seatbelt execution. | pilot report + fresh tests | Candidate `764333bc...` | EVIDENCE | Seatbelt is macOS-specific. |
| CON-001 | Canonical contract | `CapabilityPlanner` is the sole route/capability-selection authority. | root `AGENTS.md` | current main | BINDING | Open SWE cannot become a second router. |
| CON-002 | Canonical contract | Worker implementation, verification, approval, integration, merge, release, and production claims remain separate authority stages. | `AGENTS.md`, `docs/agents/TASK_EXECUTION_CONTRACT.md` | current main | BINDING | None. |
| DER-001 | Derived | A minimum activation evidence set is three independent production-shaped canaries: semantic-only; CI diagnosis+repair; and ambiguous-outcome/recovery. | DEC-004 + risk/evidence boundary | this spec | BINDING FOR THIS SPEC | Three is a minimum engineering gate, not a quality benchmark claim. |
| UNK-001 | Evidence gap | A portable credential-isolated remote sandbox is not yet qualified. | pilot final report | current | UNRESOLVED | Blocks default switch, not the initial default-off adapter. |
| UNK-002 | Evidence gap | CI artifact-aware reconciliation is needed when a repaired new failure coexists with a pre-existing aggregate failure. | PR #664 evidence | current | UNRESOLVED | Blocks relying on coarse check-level CFI as repair-success truth. |
| REJ-001 | Rejected | Full Open SWE replacement of Nexus governance/execution control plane. | DEC-001/003 | current | REJECTED | Would duplicate/erase Nexus authority boundaries. |
| REJ-002 | Rejected | Direct activation, OpenCLI retirement, or auto-merge from one canary. | DEC-004/005 | current | REJECTED | Insufficient evidence/authority. |

## 5. Current verified state

At `CUR-001`, External Intelligence is already a control-plane workflow. `ExternalIntelligenceSidecar` accepts a transport abstraction and persists request/attempt/receipt state. `ExternalIntelligenceAutomation` controls dispatch sequencing, source/task-card validation, fanout, closure, and reconciliation. The operator service currently hard-wires OpenCLI at construction time (`CUR-002`).

The Open SWE pilot is not production code. It is evidence that a Nexus-side adapter can use public Deep Agents seams for physically narrowed semantic/diagnosis graphs and bounded repair execution (`CUR-003`, `CUR-006`). The pilot must not be merged wholesale as a new controller.

## 6. Owner decisions

- `DEC-001`: use `PARTIAL_REPLACE`.
- `DEC-002`: Open SWE / Deep Agents owns the reusable LLM/tool graph execution role.
- `DEC-003`: Nexus retains deterministic intelligence, routing/admission, durable orchestration, credential/GitHub authority, verification, and merge/release boundaries.
- `DEC-004`: initial productionization is default-off and keeps OpenCLI as control arm.
- `DEC-005`: no automatic merge/release.

## 7. Canonical terminology

- **Open SWE execution adapter:** Nexus-owned **thin external-runtime client** that speaks a versioned request/result protocol to the Open SWE / Deep Agents runtime; it does not host Deep Agents graphs in the Nexus process, import upstream runtime internals into Core, or act as a fork/controller.
- **Control arm:** existing OpenCLI semantic path kept operational during adoption.
- **Activation:** changing production default routing/config to prefer Open SWE. Activation is outside the first implementation card.
- **Portable sandbox:** credential-isolated execution environment not dependent on macOS Seatbelt.
- **Candidate:** bounded code change subject to independent verification/acceptance; never self-approved by the execution model.

## 8. Change delta

Mode: `BROWNFIELD`.

Baseline: `James3014/Nexus-new@c00c299152599a87efd831c3e146ecadd8f8b21f`, especially `scripts/ops/external_intelligence_service.py`, `nexus/services/external_intelligence.py`, and External Intelligence tests.

### ADDED

- `REQ-001` optional Open SWE semantic execution adapter.
- `REQ-004` physical tool-surface qualification on dependency/runtime drift.
- `REQ-005` reproducible dependency and credential-isolation requirements.
- `REQ-007` staged activation evidence gates.

### MODIFIED

- Semantic transport construction changes from OpenCLI-only to a configuration-selected transport with OpenCLI as the unchanged default.
- Diagnosis/repair execution will later be adaptable to Open SWE while preserving Nexus queue/replay/verification authority; this is not part of the first card.

### REMOVED

- No existing production path is removed in the first productionization phase.
- Planned custom semantic-review LLM graph implementation is removed from future design scope, not deleted from current production source because no equivalent production implementation exists.

### RENAMED

None.

## 9. Scope

Included:

- optional Open SWE semantic external-runtime transport/client;
- explicit default-off configuration with OpenCLI default preserved;
- dedicated `runtimes/open_swe` dependency domain with pinned/reproducible runtime dependencies;
- physically read-only semantic tool surface;
- existing request/attempt/reconcile semantics preserved;
- later bounded diagnosis/repair adapter integration;
- portable sandbox qualification and production-shaped canaries before activation.

## 10. Non-goals

- replacing RI or CapabilityPlanner;
- replacing Nexus queue/replay/reconciliation;
- deleting or disabling OpenCLI/LaunchAgent in initial productionization;
- granting Open SWE GitHub credentials or direct GitHub write tools;
- automatic merge/release/deploy;
- introducing Open SWE as a second worker selector/router;
- claiming Seatbelt is a portable production sandbox;
- merging the experimental Pilot harness wholesale.

## 11. User and operator stories

1. An operator running the current configuration sees identical OpenCLI behavior after the adapter ships.
2. An operator may explicitly select the Open SWE semantic backend in a controlled environment; if dependencies/backend qualification are unavailable, startup/dispatch fails closed rather than silently falling back.
3. Nexus can attribute every Open SWE semantic attempt to the same request identity/replay state used by the current sidecar.
4. An Open SWE model cannot mutate code, execute arbitrary commands, use HTTP, or delegate a mutating subagent while acting as semantic reviewer.
5. A future diagnosis/repair adapter can reuse the same durable controller while Candidate acceptance remains outside the worker.

## 12. Architecture and authority boundaries

```text
GitHub / Issue / PR evidence
          |
          v
Repository Intelligence / Nexus evidence
          |
          v
CapabilityPlanner + Workforce Admission
          |
          v
ExternalIntelligenceAutomation
  durable state / replay / reconciliation
          |
          +---- semantic_backend=opencli  (DEFAULT / control)
          |
          `---- semantic_backend=open_swe (DEFAULT-OFF)
                    |
                    v
          thin typed process client
                    |
                    v
       external nexus-open-swe-runtime
          Deep Agents bounded graphs

Later phase:
ExternalIntelligenceAutomation
          |
          v
Open SWE diagnosis/repair execution
          |
          v
Candidate
          |
          v
Independent Nexus verification / acceptance
          |
          v
STOP before merge authority
```

Open SWE describes/executes bounded model work. It never selects the Nexus route, grants admission, owns durable replay truth, directly mutates GitHub, accepts its own Candidate, merges, releases, or deploys.

## 13. Requirements

### REQ-001 — Optional Open SWE semantic execution adapter

- **Status:** `SETTLED`
- **Source:** `DEC-001, DEC-002, CUR-002, CUR-006`
- **Behavior:** Nexus SHALL provide an Open SWE / Deep Agents semantic execution adapter compatible with the existing External Intelligence semantic result boundary without creating a second automation controller.
- **Failure behavior:** If the adapter cannot construct its qualified graph or parse/bind a result, the current attempt SHALL fail closed through existing durable attempt/reconciliation semantics.
- **Rationale:** Reuse proven Open SWE execution rather than rebuild a parallel LLM graph runtime.
- **Authority/interface:** External Intelligence semantic transport/execution seam.
- **Non-goal linkage:** Sections 10 and 12.

### REQ-002 — OpenCLI remains default control arm

- **Status:** `SETTLED`
- **Source:** `DEC-004, CUR-002`
- **Behavior:** Existing configurations SHALL continue to select OpenCLI unless an explicit non-default Open SWE backend setting is present.
- **Failure behavior:** Invalid/unknown backend values SHALL fail configuration validation; no silent fallback from an explicitly selected Open SWE attempt to OpenCLI or another provider is permitted.
- **Rationale:** Adoption must be reversible and measurable.
- **Authority/interface:** operator service configuration.
- **Non-goal linkage:** no OpenCLI retirement.

### REQ-003 — Nexus authority remains canonical

- **Status:** `SETTLED`
- **Source:** `DEC-003, DEC-005, CON-001, CON-002`
- **Behavior:** The Open SWE adapter SHALL NOT select routes, grant Workforce Admission, own replay/queue authority, approve/merge/release/deploy, or receive direct GitHub mutation authority.
- **Failure behavior:** Any attempted capability beyond the adapter contract SHALL be absent or denied and SHALL NOT be converted into an advisory success.
- **Rationale:** Partial replacement is execution reuse, not governance replacement.
- **Authority/interface:** Nexus control plane.
- **Non-goal linkage:** Sections 10 and 12.

### REQ-004 — Physical reviewer/diagnosis capability isolation

- **Status:** `SETTLED`
- **Source:** `DEC-002, CUR-006`
- **Behavior:** Semantic and diagnosis graphs SHALL physically omit code mutation, arbitrary execution, `task`/subagent escape, generic network/HTTP, Git mutation, GitHub mutation, merge, release, and deploy tools.
- **Failure behavior:** Dependency or upstream drift that changes the executable ToolNode SHALL block Open SWE admission until the tool-surface qualification is rerun and passes.
- **Rationale:** Model-visible filtering is insufficient.
- **Authority/interface:** external runtime graph factory + Nexus tool-surface qualification contract.
- **Non-goal linkage:** none.

### REQ-005 — Reproducible dependency and credential isolation

- **Status:** `SETTLED`
- **Source:** `CUR-003, CUR-005, CUR-006, DEC-003`
- **Behavior:** Open SWE / Deep Agents runtime dependencies SHALL be installed through a dedicated external runtime dependency contract under `runtimes/open_swe`; Nexus Core SHALL NOT require those packages merely to import/start. Production code SHALL NOT depend on `/private/tmp`, ad-hoc `PYTHONPATH`, or agent-readable reusable GitHub credentials. The thin Nexus client may pass only the explicitly allowed provider credential needed by the external runtime process.
- **Failure behavior:** Missing external-runtime dependencies/executable, protocol mismatch, or a backend that cannot preserve credential isolation SHALL block the Open SWE path and SHALL NOT weaken isolation, fall back silently, or copy reusable controller/GitHub credentials into the agent workspace.
- **Rationale:** The Pilot environment split demonstrates that execution dependencies can be isolated; deployment topology must preserve that separation rather than making Nexus Core own the model runtime graph.
- **Authority/interface:** external runtime packaging/process boundary and Nexus thin client.
- **Non-goal linkage:** portable sandbox activation remains later.

### REQ-006 — Existing replay/reconciliation semantics are preserved

- **Status:** `SETTLED`
- **Source:** `DEC-003, CUR-002, CON-002`
- **Behavior:** Open SWE semantic attempts SHALL use the existing External Intelligence request identity, attempt fencing, receipt persistence, and reconcile-before-retry semantics; an ambiguous model outcome SHALL NOT cause blind redispatch.
- **Failure behavior:** If the adapter cannot reconcile an ambiguous outcome, the attempt SHALL remain blocked/reconciliation-required under existing semantics.
- **Rationale:** Open SWE execution does not replace Nexus durable orchestration.
- **Authority/interface:** `ExternalIntelligenceSidecar` / store / transport boundary.
- **Non-goal linkage:** none.

### REQ-007 — Activation remains gated

- **Status:** `SETTLED`
- **Source:** `DEC-004, DER-001, UNK-001`
- **Behavior:** Open SWE SHALL remain non-default until a portable credential-isolated sandbox passes and at least three production-shaped canaries pass: semantic-only; CI diagnosis+repair; and ambiguous-outcome/recovery.
- **Failure behavior:** Missing or failed activation evidence SHALL keep OpenCLI as default and SHALL NOT be interpreted as authorization to retire the control arm.
- **Rationale:** One successful canary is insufficient for default switching.
- **Authority/interface:** future activation decision.
- **Non-goal linkage:** initial adapter may ship before activation.

### REQ-008 — Repair success must not depend on coarse aggregate CI alone

- **Status:** `DERIVED`
- **Source:** `UNK-002, CUR-004`
- **Behavior:** Before diagnosis/repair automation can be default-enabled, the controller SHALL distinguish a repaired PR-specific new failure from unrelated pre-existing aggregate failures using artifact/identity-bound evidence.
- **Failure behavior:** `IMPACT_UNKNOWN` or an aggregate red check with unresolved new-vs-baseline attribution SHALL block automated repair-success promotion.
- **Rationale:** PR #664 removed its new failure while the aggregate impact job remained red for a baseline architecture failure.
- **Authority/interface:** RI/CI reconciliation consumer boundary.
- **Non-goal linkage:** no change to RI Core is required by the first semantic-adapter card.

## 14. Behavioral and interface decisions

- Initial backend enum/selection SHALL have two values: `opencli` and `open_swe`; `opencli` is the default.
- Explicit `open_swe` selection SHALL never silently fall back to OpenCLI.
- The Open SWE adapter SHALL return/bind the same semantic result contract consumed by `ExternalIntelligenceSidecar`, or introduce a versioned adapter result that is converted at one boundary with deterministic validation.
- Open SWE graph construction SHALL live inside the dedicated external runtime and use pinned public Deep Agents seams; Nexus owns the capability/protocol contract and physical qualification tests, not the in-process graph runtime. Upstream default reviewer graphs SHALL not be imported as trusted capability policy.
- Model/provider selection remains downstream of Nexus authority; the adapter SHALL not hard-code a new global routing authority.
- `task`/subagents remain disabled for semantic/diagnosis until separately qualified.

## 15. Verification seam

Highest initial seam: current-main `ExternalIntelligenceSidecar` + service construction under a feature-selected Open SWE transport, using a real model only in controlled canary tests; normal regression uses deterministic capture/fake model plus exact executable ToolNode assertions.

Negative controls:

- default config still constructs OpenCLI path;
- unknown backend fails closed;
- selected Open SWE with missing external runtime executable/dependency fails closed without fallback;
- hidden `write_file`, `execute`, `task`, HTTP, GitHub-write tools are absent/invalid;
- ambiguous transport outcome is reconciled, not redispatched;
- no provider/GitHub credential is copied into sandbox/workspace state;
- dependency/upstream version drift invalidates previous tool-surface qualification.

## 16. Acceptance criteria

### AC-001 — Default compatibility

- **Requirement:** `REQ-002`
- **Evidence level:** `FIXTURE`
- **Verification seam:** `ServiceConfig` + `build_automation()` tests.
- **Pass:** unchanged/default configuration constructs the existing OpenCLI path and existing OpenCLI regression tests pass.
- **Negative control:** unknown backend value is rejected.
- **Fail:** default behavior changes or implicit fallback occurs.
- **Receipt binding:** exact Candidate SHA + test result.

### AC-002 — Qualified Open SWE semantic graph

- **Requirement:** `REQ-001, REQ-004`
- **Evidence level:** `FIXTURE`
- **Verification seam:** compiled Deep Agents graph inside the dedicated external runtime, exercised through its pinned runtime environment and audited against the Nexus client contract.
- **Pass:** executable semantic ToolNode contains only the bounded read/evidence surface required by the adapter.
- **Negative control:** hidden mutation/execute/task/network invocation returns invalid/absent and produces no side effect.
- **Fail:** any forbidden capability is executable.
- **Receipt binding:** Deep Agents/Open SWE version + graph/tool inventory + Candidate SHA.

### AC-003 — Packaging is explicit

- **Requirement:** `REQ-005`
- **Evidence level:** `STATIC`
- **Verification seam:** dedicated `runtimes/open_swe/pyproject.toml` + nested lock, root `pyproject.toml`/lock audit, and clean-environment thin-client import test.
- **Pass:** the external runtime is reproducibly installable from its own dependency domain; Nexus root imports/runs the control plane without Deep Agents/LangChain runtime packages.
- **Negative control:** base Nexus environment without the external runtime dependencies continues to import/run the default OpenCLI path.
- **Fail:** default Nexus requires Deep Agents/LangChain runtime packages, the external runtime depends on an experimental checkout, or runtime upgrades require root dependency churn without a protocol change.
- **Receipt binding:** Candidate SHA + dependency lock/version evidence.

### AC-004 — Credential boundary

- **Requirement:** `REQ-003, REQ-005`
- **Evidence level:** `FIXTURE`
- **Verification seam:** adapter/backend construction with sentinel credential-name inputs and capability inspection, never secret-value logging.
- **Pass:** reusable controller/provider/GitHub credential material is not propagated into model-visible workspace/sandbox execution state.
- **Negative control:** a sentinel sensitive environment name supplied to controller scope is absent from agent execution scope.
- **Fail:** controller credential material becomes agent-readable.
- **Receipt binding:** Candidate SHA + sanitized isolation test result.

### AC-005 — Replay/reconcile parity

- **Requirement:** `REQ-006`
- **Evidence level:** `FIXTURE`
- **Verification seam:** `ExternalIntelligenceSidecar` attempt-state tests using Open SWE adapter.
- **Pass:** ambiguous outcome uses reconcile on the same request/attempt and never performs a second invocation blindly.
- **Negative control:** injected timeout/unknown outcome followed by second poll does not increment dispatch count.
- **Fail:** duplicate dispatch or receipt identity drift.
- **Receipt binding:** request SHA, attempt ID, Candidate SHA.

### AC-006 — Authority conservation

- **Requirement:** `REQ-003`
- **Evidence level:** `STATIC`
- **Verification seam:** source/diff audit + forbidden API/tool tests.
- **Pass:** adapter has no route selection, Workforce Admission mutation, direct GitHub mutation, approval, merge, release, or deploy surface.
- **Negative control:** search/assertions reject new direct calls to protected authority surfaces from the adapter.
- **Fail:** adapter becomes a second controller or authority source.
- **Receipt binding:** Candidate diff/tree.

### AC-007 — Portable sandbox qualification

- **Requirement:** `REQ-005, REQ-007`
- **Evidence level:** `LIVE_RUNTIME`
- **Verification seam:** supported non-Seatbelt isolated backend with real model execution and credential-boundary probes.
- **Pass:** portable sandbox executes bounded review/repair while reusable credentials remain controller-side and inaccessible to the agent.
- **Negative control:** untrusted prompt/source requests cannot expand capabilities or expose reusable credentials.
- **Fail:** macOS Seatbelt is the only qualifying backend or credential isolation is unproven.
- **Receipt binding:** backend identity/version, model identity, run ID, Candidate/base identities.

### AC-008 — Diagnosis/repair adapter preserves Candidate boundary

- **Requirement:** `REQ-001, REQ-003, REQ-004, REQ-006`
- **Evidence level:** `CANARY`
- **Verification seam:** real bounded CI diagnosis -> repair Candidate under Nexus durable queue/replay authority.
- **Pass:** Open SWE performs diagnosis/repair in isolated execution, produces a Candidate, and stops before acceptance/merge; no blind replay occurs.
- **Negative control:** stale identity, inconclusive diagnosis, or repair-cycle exhaustion blocks/escalates without mutation/merge.
- **Fail:** worker self-accepts, bypasses queue/replay, or directly mutates protected GitHub authority.
- **Receipt binding:** exact PR/head/RI hash, run/attempt IDs, Candidate SHA/tree.

### AC-009 — Minimum canary portfolio

- **Requirement:** `REQ-007`
- **Evidence level:** `CANARY`
- **Verification seam:** three distinct production-shaped canaries.
- **Pass:** semantic-only, CI diagnosis+repair, and ambiguous-outcome/recovery canaries independently pass on exact identities.
- **Negative control:** at least one canary must exercise a denied/stale/recovery path, not only happy paths.
- **Fail:** fewer than three qualifying canaries or unresolved material failure.
- **Receipt binding:** per-canary immutable report/run identity.

### AC-010 — Artifact-aware repair-success evidence

- **Requirement:** `REQ-008`
- **Evidence level:** `CANARY`
- **Verification seam:** PR whose target new failure is repaired while an unrelated baseline failure remains.
- **Pass:** controller records the target failure as resolved without claiming the unrelated aggregate check is green.
- **Negative control:** coarse red aggregate alone cannot mark repair failed or successful without artifact attribution.
- **Fail:** new-vs-baseline attribution remains ambiguous.
- **Receipt binding:** base/head, check run/artifact identities, RI evidence hashes.

## 17. Traceability matrix

| Requirement | Sources | Delta | Acceptance | Evidence level | Claim ceiling | Task-card handoff group |
|---|---|---|---|---|---|---|
| REQ-001 | DEC-001, DEC-002, CUR-002, CUR-006 | ADDED | AC-002, AC-008 | FIXTURE/CANARY | optional execution adapter proven | G1; G3 |
| REQ-002 | DEC-004, CUR-002 | MODIFIED | AC-001 | FIXTURE | default behavior preserved | G1 |
| REQ-003 | DEC-003, DEC-005, CON-001, CON-002 | ADDED guard | AC-004, AC-006, AC-008 | STATIC/CANARY | authority conserved | G1; G3 |
| REQ-004 | CUR-006, DEC-002 | ADDED | AC-002, AC-008 | FIXTURE/CANARY | physical tool isolation proven | G1; G3 |
| REQ-005 | CUR-003, CUR-005, CUR-006 | ADDED | AC-003, AC-004, AC-007 | STATIC/FIXTURE/LIVE_RUNTIME | dependency/isolation qualified to tested backend | G1; G2 |
| REQ-006 | DEC-003, CUR-002 | MODIFIED compatible path | AC-005, AC-008 | FIXTURE/CANARY | replay/reconcile parity proven | G1; G3 |
| REQ-007 | DEC-004, DER-001, UNK-001 | ADDED | AC-007, AC-009 | LIVE_RUNTIME/CANARY | activation evidence complete, not activated | G2; G4 |
| REQ-008 | UNK-002, CUR-004 | ADDED derived guard | AC-010 | CANARY | repair attribution supported | G4 |

## 18. Evidence and claim ceiling

- Pilot/focused tests support implementation feasibility, not production activation.
- PR #664 supports one real canary and authority separation, not statistical reviewer superiority.
- Initial Task Card completion may claim only that a default-off semantic adapter is Candidate-ready and regression-safe.
- Portable sandbox, diagnosis/repair automation, minimum canary portfolio, and activation require later cards/evidence.
- No card may claim OpenCLI retirement, default switch, production readiness, auto-merge, or release unless a later explicit authority/spec changes this ceiling.

## 19. Rollback and failure handling

- Default remains OpenCLI; rollback for the initial adapter is config-level non-selection plus code revert if needed.
- Explicit Open SWE selection with missing dependency/backend fails closed; no fallback after an attempt begins.
- Ambiguous model outcome remains reconciliation-required; no blind retry.
- Dependency/tool-surface drift blocks Open SWE until requalification.
- Canary failure never disables the control arm.

## 20. Documentation and learning write-back

- Record exact package/runtime/tool-surface identities with each qualification.
- Preserve pilot reports as historical evidence; do not promote experimental Seatbelt assumptions to portable production policy.
- Reusable failure/recovery lessons may be written through existing Nexus learning governance only after independent verification.

## 21. Risks and unknowns

- `UNK-001`: portable remote sandbox not qualified.
- `UNK-002`: aggregate CI/RI granularity can obscure successful repair of one new failure.
- Open SWE/Deep Agents upstream drift may reintroduce tool capabilities; requalification is mandatory.
- Provider/model availability and pricing remain external operational dependencies.
- Reviewer quality comparison is not statistically established.

## 22. Unresolved owner decisions

None. Remaining items are evidence/engineering gates, not owner product decisions. The first card does not activate or retire anything.

## 23. Task-card handoff boundary

| Task group | Requirements | Acceptance | Observable outcome | Dependency seam | Verification seam | Maximum claim | Scope class | Minimum MCP profile | Known blocker |
|---|---|---|---|---|---|---|---|---|---|
| G1 Feature-flagged semantic adapter | REQ-001; REQ-002; REQ-003; REQ-004; REQ-005; REQ-006 | AC-001; AC-002; AC-003; AC-004; AC-005; AC-006 | current EIA can explicitly use Open SWE semantic execution while OpenCLI remains default | current main source + pinned optional dependency contract | focused service/sidecar/tool-surface/replay tests | Candidate-ready default-off adapter only | medium | CANDIDATE | none |
| G2 Portable sandbox qualification | REQ-005; REQ-007 | AC-007 | supported non-Seatbelt backend proves credential-isolated real execution | G1 accepted adapter contract | live backend qualification | portable sandbox qualified; no activation | small | VERIFY | backend availability |
| G3 Diagnosis/repair adapter | REQ-001; REQ-003; REQ-004; REQ-006 | AC-008 | Nexus queue/replay admits Open SWE diagnosis/repair and receives Candidate only | G1 accepted adapter + bounded repair interface | real canary + independent Candidate verification | diagnosis/repair Candidate path qualified | medium | CANDIDATE | G1 acceptance |
| G4 Activation evidence portfolio | REQ-007; REQ-008 | AC-009; AC-010 | three production-shaped canaries plus artifact-aware repair attribution are complete | G2 portable sandbox + G3 repair path | canary portfolio and independent audit | evidence sufficient for a separate activation decision | medium | VERIFY | G2/G3 completion |

## 24. Out of scope

- default activation;
- OpenCLI/LaunchAgent retirement;
- automatic merge/release/deploy;
- portable sandbox implementation inside the first card;
- RI Core redesign;
- changing CapabilityPlanner or Workforce Admission authority;
- subagent/task enablement;
- broad Open SWE fork/vendor import.

## 25. Supersession and change history

- 2026-08-31: replaces the planned custom semantic/diagnosis/repair LLM graph direction with `PARTIAL_REPLACE` execution reuse.
- Existing Nexus governance/runtime authority remains unchanged.
- The Open SWE pilot Candidates/reports remain historical evidence and are not production source.
