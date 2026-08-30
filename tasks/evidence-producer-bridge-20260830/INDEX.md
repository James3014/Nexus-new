# Evidence Producer Bridge Mission Closure

- **Campaign ID:** `CAMPAIGN-EVIDENCE-PRODUCER-BRIDGE-01`
- **Status:** `READY_FOR_EXECUTION`
- **Source mode:** `VALIDATED_SPEC`
- **Source spec ID:** `SPEC-EPB-EXTERNAL-CANDIDATE-ADOPTION-EXEC-001`
- **Source spec SHA-256:** `9e841f43d63ffc10704f00b4d21b88f9fbf78f3a473839a1409f278a951251a1`
- **Source basis snapshot:** `James3014/Nexus-new`; contract base `a33fbd65b21ddf67085be9fa4ea245f59626ddd8`; accepted EPB Candidate `b3343c95479f03857af7761381a1b839ac049e24`; Owner master authorization SHA-256 `1adad9c3cc0356c6bd7d7babf41bf980664c3ed38253909642b78e4992572133`
- **Auto-chain:** `false`
- **Parallel execution:** `false`
- **Current frontier:** `TASK-EPB-002`
- **Maximum campaign claim:** Adoption capability independently verified; no EPB approval, integration, remote merge, release, production, Task4, or public-stability claim.

The source specification's textual `READY_FOR_OWNER_REVIEW` state is superseded for execution by the exact Owner master authorization above, which explicitly changes it to `OWNER_APPROVED_FOR_EXECUTION` without changing the approved specification bytes or digest.

## 1. Source handoff import

| Source group | Requirements | Acceptance | Observable outcome | Dependency seam | Verification seam | Maximum claim | Scope class | Minimum MCP profile | Known blocker | Compiled tasks |
|---|---|---|---|---|---|---|---|---|---|---|
| Core external Candidate adoption service | `REQ-002`; `REQ-003`; `REQ-004`; `REQ-005`; `REQ-006` | `AC-002`; `AC-003`; `AC-005`; `AC-006`; `AC-007` | Core service physically verifies an immutable precommitted Candidate and atomically forms pending-approval state | Existing CandidateVerifier, CandidateCommitter, and durable lifecycle | Real immutable precommitted Candidate plus service hostile tests | Core lifecycle adoption service independently verified; no public Gateway action, EPB adoption, approval, integration, or remote claim. | medium | CANDIDATE | none | `TASK-EPB-002` |
| Public typed adoption action | `REQ-001`; `REQ-007` | `AC-001`; `AC-004` | Typed fail-closed public external Candidate adoption reaches pending approval only | Accepted and integrated core adoption service contract | Real Gateway/CLI action plus downstream-effect hostile tests | Adoption capability independently verified; no EPB approval, integration, remote merge, release, production, Task4, or public-stability claim. | medium | CANDIDATE | none | `TASK-EPB-003` |

## 2. Requirement coverage

| Requirement | Acceptance | Implementing task | Witness task | Coverage status |
|---|---|---|---|---|
| `REQ-001` | `AC-001` | `TASK-EPB-003` | `TASK-EPB-003` | FULL |
| `REQ-002` | `AC-005` | `TASK-EPB-002` | `TASK-EPB-002` | FULL |
| `REQ-003` | `AC-002` | `TASK-EPB-002` | `TASK-EPB-002` | FULL |
| `REQ-004` | `AC-006` | `TASK-EPB-002` | `TASK-EPB-002` | FULL |
| `REQ-005` | `AC-007` | `TASK-EPB-002` | `TASK-EPB-002` | FULL |
| `REQ-006` | `AC-003` | `TASK-EPB-002` | `TASK-EPB-002` | FULL |
| `REQ-007` | `AC-004` | `TASK-EPB-003` | `TASK-EPB-003` | FULL |

## 3. Dependency graph

| Task ID | Status | Type | Slicing strategy | Blocked by | Edge type | Unlock evidence | Observable outcome | Verification seam | Maximum claim | Scope class | MCP profile | Transport status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `TASK-EPB-002` | ACTIVE | IMPLEMENTATION | TRACER_BULLET | none | none | none | Core service physically verifies an immutable precommitted Candidate and atomically forms pending-approval state | Real immutable precommitted Candidate plus service hostile tests | Core lifecycle adoption service independently verified; no public Gateway action, EPB adoption, approval, integration, or remote claim. | medium | CANDIDATE | READY |
| `TASK-EPB-003` | PLANNED | IMPLEMENTATION | TRACER_BULLET | `TASK-EPB-002` | CONTRACT | Exact accepted/integrated core service Candidate SHA, tree, service API, verified receipt, and fresh base HEAD | Typed fail-closed public external Candidate adoption reaches pending approval only | Real Gateway/CLI action plus downstream-effect hostile tests | Adoption capability independently verified; no EPB approval, integration, remote merge, release, production, Task4, or public-stability claim. | medium | CANDIDATE | READY |

## 4. Ready candidates and frontier selection

- **Dependency-ready candidates:** `TASK-EPB-002`
- **Selected frontier:** `TASK-EPB-002`
- **Selection rationale:** It closes the only physical lifecycle gap preventing the already accepted immutable EPB Candidate from entering unchanged approval and integration gates.
- **Exact unblock condition:** none

## 5. Campaign authority and non-goals

Owner master authorization permits same-mission Task Card creation, implementation, bounded repair attempts, independent acceptance, governed approval, local integration, exact-head remote publication/default merge, Gateway reload, and post-merge verification. Workers may implement and commit only their scoped Candidate. They may not self-approve, integrate, merge, push protected/default refs, release, deploy, begin Task4, create a trust root, or make production/public-stability claims. `AUTO_CHAIN=false` prohibits only materially different missions; the explicitly authorized EPB closure sequence remains controller-managed.

## 6. Supersession and change history

- `TASK-EPB-001` remains retained negative evidence.
- `TASK-EPB-001-R1` produced exact accepted Candidate `b3343c95479f03857af7761381a1b839ac049e24` and is not rewritten.
- `TASK-EPB-002` is the Owner-authorized same-campaign lifecycle closure repair compiled from the approved specification.
