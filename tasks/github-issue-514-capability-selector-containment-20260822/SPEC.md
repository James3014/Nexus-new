# Legacy CapabilitySelector authority containment

- **Spec ID:** `SPEC-ISSUE-514-CAPABILITY-SELECTOR-CONTAINMENT`
- **Status:** `READY_FOR_TASK_CARDS`
- **Basis snapshot:** `James3014/Nexus-new@d6b4bd77e8b559710ca103eeaa30f57b2e54fcdf`; Issue #514; Owner request 2026-08-22 to complete both identified repairs
- **Supersedes:** none
- **Claim ceiling:** `LEGACY_CAPABILITY_SELECTOR_AUTHORITY_CONTAINED_AT_SOURCE`

## 1. Problem statement

Production-reachable legacy `CapabilitySelector` and `SkillsRouter` paths still independently choose lite/full behavior, capability sets, phases, and `NEXUS_SKIP_*` removals. This conflicts with the repository invariant that `CapabilityPlanner` is the sole route and capability-selection authority.

## 2. Desired outcome

Affected legacy callers remain compatible but consume/project Planner-owned decisions. They cannot independently add/remove selected capabilities or downgrade Planner-owned route/depth safety.

## 3. Basis, coverage, and freshness

Current source was read in the isolated DevSpace worktree at `d6b4bd77e8b559710ca103eeaa30f57b2e54fcdf`, including `AGENTS.md`, `docs/agents/TASK_EXECUTION_CONTRACT.md`, `nexus/core/capability_selector.py`, `nexus/core/router.py`, `nexus/engine/capability_planner.py`, `nexus/engine/capability_contracts.py`, and focused tests. GitHub Issue #514 is the durable repair contract. Nexus Gateway mutation is not used because its canonical checkout is stale at `aedc5f2607c0a6f7ecc7f7c0174854af3e6c38d3` while GitHub main is `d6b4bd77...`.

## 4. Source and decision ledger

| ID | Class | Statement | Authority/location | Freshness/snapshot | Status | Limitation |
|---|---|---|---|---|---|---|
| DEC-001 | OWNER_DECISION | Complete the two identified repairs and report after completion. | Current Owner request | 2026-08-22 | BINDING | This spec covers only repair 1. |
| CON-001 | CANONICAL_CONTRACT | `CapabilityPlanner` is sole route/capability-selection authority. | root `AGENTS.md` | d6b4bd77 | BINDING | none |
| CON-002 | CANONICAL_CONTRACT | Route-authority changes require governed work. | `docs/agents/TASK_EXECUTION_CONTRACT.md` | d6b4bd77 | BINDING | none |
| CUR-001 | CURRENT_STATE | Legacy selector calls lite oracle, assembles capabilities/phases, honors `NEXUS_SKIP_*`, and returns its own execution plan. | `nexus/core/capability_selector.py` | d6b4bd77 | EVIDENCE | source-level only |
| CUR-002 | CURRENT_STATE | `SkillsRouter.route_candidates()` invokes legacy selector and executes its plan. | `nexus/core/router.py` | d6b4bd77 | EVIDENCE | source-level only |
| CUR-003 | CURRENT_STATE | CLI learn flows invoke router and separately invoke legacy selector for lite/full behavior. | `scripts/engine/nexus_cli.py` | d6b4bd77 | EVIDENCE | source-level only |
| HIS-001 | HISTORICAL | #291 removed dynamic-learning add/remove authority; #465 fixed force-lite safety only. | GitHub history | before d6b4bd77 | CONTEXT_ONLY | does not close current gap |

## 5. Current verified state

`CapabilitySelector` currently behaves as a second selection engine and is production-reachable through `SkillsRouter` and the learning CLI. Existing focused tests still preserve `NEXUS_SKIP_*` post-selection removal behavior, so at least one test encodes the obsolete authority model.

## 6. Owner decisions

- DEC-001: perform this bounded repair now; do not wait for another approval merely to proceed through the already-authorized implementation workflow.

## 7. Canonical terminology

- **Planner truth:** the route/depth/capability decision produced by `CapabilityPlanner`.
- **Legacy projection:** a compatibility representation derived from Planner truth that cannot add/remove capabilities or alter route/depth.
- **Second selector:** any component with independent decision effect over route/capability set after/beside Planner.

## 8. Change delta

Mode: BROWNFIELD.

### MODIFIED

- **Baseline:** legacy `CapabilitySelector` independently creates execution plans.
- **Future requirement:** legacy compatibility SHALL project Planner-owned selection/route truth and SHALL NOT independently alter the selected set or lite/full decision.
- **From:** independent legacy selector plus `NEXUS_SKIP_*` capability removal.
- **To:** Planner-owned decision with compatibility-only projection/consumption.
- **Reason:** enforce CON-001.
- **Impact:** `BREAKING` only for unsupported callers that relied on legacy authority; compatibility API should remain where practical.

## 9. Scope

- `nexus/core/capability_selector.py`
- `nexus/core/router.py`
- `scripts/engine/nexus_cli.py`
- focused tests named by Issue #514.

## 10. Non-goals

No new Router/Planner/registry; no provider/model policy changes; no #472 context-consumption changes; no receipt-coverage repair; no runtime-wide C9 claim.

## 11. Architecture and authority boundaries

`CapabilityPlanner` remains the only selector. Legacy components may translate, serialize, or consume Planner decisions. Constraint blocking remains fail-closed but may not establish a parallel route/capability selection authority. Approval, integration, merge, runtime activation, and production claims remain separate.

## 12. Requirements

### REQ-001 — Sole selection authority
- **Status:** `SETTLED`
- **Source:** DEC-001, CON-001, CUR-001, CUR-002, CUR-003
- **Behavior:** The affected legacy paths SHALL derive route/depth/capability truth from `CapabilityPlanner` and SHALL NOT independently add or remove selected capabilities.
- **Failure behavior:** Missing/invalid Planner truth SHALL fail closed rather than fall back to legacy selection.
- **Authority/interface:** route/capability selection.

### REQ-002 — Legacy compatibility projection
- **Status:** `SETTLED`
- **Source:** DEC-001, CON-001
- **Behavior:** Existing legacy APIs MAY remain, but their output SHALL be a deterministic compatibility projection of Planner truth sufficient for current callers.
- **Failure behavior:** Projection mismatch SHALL be observable/test-failing; no silent legacy recomputation.
- **Authority/interface:** compatibility layer.

### REQ-003 — Safety preservation
- **Status:** `SETTLED`
- **Source:** DEC-001, CON-001, HIS-001
- **Behavior:** Legacy environment controls such as `NEXUS_SKIP_*` or force-lite controls SHALL NOT override Planner-required capabilities or Planner safety floors.
- **Failure behavior:** Unsafe downgrade/removal SHALL be rejected or ignored in favor of Planner truth.
- **Authority/interface:** safety/route policy.

## 13. Verification seam

Focused unit/integration tests exercise `CapabilitySelector`, `SkillsRouter`, and CLI learning flows. A negative control must demonstrate that post-Planner `NEXUS_SKIP_*` cannot remove a Planner-required capability and that high-risk force-lite cannot downgrade Planner-owned depth/phases.

## 14. Acceptance criteria

### AC-001 — Planner-selected set is conserved
- **Requirement:** REQ-001
- **Evidence level:** FIXTURE
- **Verification seam:** focused capability-selector/router tests
- **Pass:** legacy projection contains exactly the in-scope Planner-selected capabilities represented by the compatibility mapping and does not independently add/remove them.
- **Negative control:** inject legacy skip/add influence and prove it cannot alter Planner truth.
- **Fail:** any independent legacy selection changes the canonical decision.

### AC-002 — Learning CLI consumes Planner route truth
- **Requirement:** REQ-001, REQ-002
- **Evidence level:** FIXTURE
- **Verification seam:** `tests/test_cli_learn_mode.py`
- **Pass:** `learn_ingest` and `learn_converge` determine lite/full behavior from Planner-derived decision state, not a separately computed legacy plan.
- **Negative control:** legacy selector output disagreement cannot change the CLI route decision.
- **Fail:** CLI still treats independent legacy plan as route truth.

### AC-003 — Safety knobs cannot override Planner
- **Requirement:** REQ-003
- **Evidence level:** FIXTURE
- **Verification seam:** focused route-authority tests
- **Pass:** `NEXUS_SKIP_*` cannot remove Planner-required capability; high-risk force-lite does not bypass Planner safety floor.
- **Negative control:** set the legacy env flags while Planner requires the protected behavior.
- **Fail:** selected set/depth changes contrary to Planner truth.

### AC-004 — Regression and scope
- **Requirement:** REQ-001, REQ-002, REQ-003
- **Evidence level:** FIXTURE
- **Verification seam:** focused test suite plus `git diff --check`
- **Pass:** all declared focused tests pass and no unauthorized file changes exist.
- **Negative control:** inspect complete diff and changed-path set.
- **Fail:** focused regression, out-of-scope path, or whitespace error.

## 15. Traceability matrix

| Requirement | Sources | Delta | Acceptance | Evidence level | Claim ceiling | Task-card handoff group |
|---|---|---|---|---|---|---|
| REQ-001 | DEC-001;CON-001;CUR-001;CUR-002;CUR-003 | MODIFIED | AC-001;AC-002;AC-004 | FIXTURE | `LEGACY_CAPABILITY_SELECTOR_AUTHORITY_CONTAINED_AT_SOURCE` | selector-containment |
| REQ-002 | DEC-001;CON-001 | MODIFIED | AC-002;AC-004 | FIXTURE | same | selector-containment |
| REQ-003 | DEC-001;CON-001;HIS-001 | MODIFIED | AC-003;AC-004 | FIXTURE | same | selector-containment |

## 16. Evidence and claim ceiling

Passing source/focused tests can support only source-level authority containment. It does not prove current loaded Nexus runtime or all C9 paths.

## 17. Rollback and failure handling

The repair is isolated on an Issue branch/Candidate. Any inability to project Planner truth without semantic ambiguity blocks the change rather than restoring independent legacy selection.

## 18. Risks and unknowns

The canonical Planner node namespace and legacy CapabilityRegistry namespace are not identical. Implementation must not invent a semantic one-to-one mapping. Prefer moving production callers to canonical Planner/Runtime seams or an explicit bounded compatibility mapping backed by tests.

## 19. Unresolved owner decisions

none

## 20. Task-card handoff boundary

| Task group | Requirements | Acceptance | Observable outcome | Dependency seam | Verification seam | Maximum claim | Scope class | Minimum MCP profile | Known blocker |
|---|---|---|---|---|---|---|---|---|---|
| selector-containment | REQ-001;REQ-002;REQ-003 | AC-001;AC-002;AC-003;AC-004 | Legacy production callers cannot act as a second selector. | none | focused tests + diff/scope audit | `LEGACY_CAPABILITY_SELECTOR_AUTHORITY_CONTAINED_AT_SOURCE` | medium | CANDIDATE | Nexus Gateway checkout is stale; use current-base governed GitHub worktree, not stale MCP mutation. |

## 21. Out of scope

Receipt completeness, wiring audit closure, model-context physical consumption, runtime-wide C9.
