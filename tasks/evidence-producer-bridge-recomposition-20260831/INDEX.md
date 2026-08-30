# Evidence Producer Bridge Adoption Recomposition

- **Campaign ID:** `CAMPAIGN-EVIDENCE-PRODUCER-BRIDGE-01`
- **Status:** `READY_FOR_EXECUTION`
- **Source mode:** `VALIDATED_SPEC`
- **Source spec ID:** `SPEC-EPB-EXTERNAL-CANDIDATE-ADOPTION-EXEC-001`
- **Source spec SHA-256:** `9e841f43d63ffc10704f00b4d21b88f9fbf78f3a473839a1409f278a951251a1`
- **Source basis snapshot:** repository `James3014/Nexus-new`; governance base `ee3558a65a416f55ac59e9060496c00df642d16a`; rejected mixed-scope core tip `a20712a5f454e7c1212209ddeb32e2764bf8b1a5`; historical Product Candidate `b3343c95479f03857af7761381a1b839ac049e24` remains `REJECTED/SUPERSEDED`; accepted Product successor `d70cdce975ca8394606d54d1492506cf5e392e4d`; Owner decision SHA-256 `18d0dcaa4e9fc80c984f0daa42bb67359eba9c0dc66f23902c1051757bd6ef1c`
- **Auto-chain:** `false`
- **Parallel execution:** `false`
- **Current frontier:** `TASK-EPB-003-R1`
- **Maximum campaign claim:** Adoption capability independently verified; no EPB approval, integration, remote merge, release, production, Task4, or public-stability claim.

## 1. Source handoff import

| Source group | Requirements | Acceptance | Observable outcome | Dependency seam | Verification seam | Maximum claim | Scope class | Minimum MCP profile | Known blocker | Compiled tasks |
|---|---|---|---|---|---|---|---|---|---|---|
| Core external Candidate adoption service | `REQ-002`; `REQ-003`; `REQ-004`; `REQ-005`; `REQ-006` | `AC-002`; `AC-003`; `AC-005`; `AC-006`; `AC-007` | Core service physically verifies an immutable precommitted Candidate and atomically forms pending-approval state | Existing CandidateVerifier, CandidateCommitter, and durable lifecycle | Real immutable precommitted Candidate plus service hostile tests | Core lifecycle adoption service independently verified; no public Gateway action, EPB adoption, approval, integration, or remote claim. | medium | CANDIDATE | none | `TASK-EPB-002-R1` |
| Public typed adoption action | `REQ-001`; `REQ-007` | `AC-001`; `AC-004` | Typed fail-closed public external Candidate adoption reaches pending approval only | Accepted and integrated core adoption service contract | Real Gateway/CLI action plus downstream-effect hostile tests | Adoption capability independently verified; no EPB approval, integration, remote merge, release, production, Task4, or public-stability claim. | medium | CANDIDATE | none | `TASK-EPB-003-R1` |

## 2. Requirement coverage

| Requirement | Acceptance | Implementing task | Witness task | Coverage status |
|---|---|---|---|---|
| `REQ-001` | `AC-001` | `TASK-EPB-003-R1` | `TASK-EPB-003-R1` | FULL |
| `REQ-002` | `AC-005` | `TASK-EPB-002-R1` | `TASK-EPB-002-R1` | FULL |
| `REQ-003` | `AC-002` | `TASK-EPB-002-R1` | `TASK-EPB-002-R1` | FULL |
| `REQ-004` | `AC-006` | `TASK-EPB-002-R1` | `TASK-EPB-002-R1` | FULL |
| `REQ-005` | `AC-007` | `TASK-EPB-002-R1` | `TASK-EPB-002-R1` | FULL |
| `REQ-006` | `AC-003` | `TASK-EPB-002-R1` | `TASK-EPB-002-R1` | FULL |
| `REQ-007` | `AC-004` | `TASK-EPB-003-R1` | `TASK-EPB-003-R1` | FULL |

## 3. Dependency graph

| Task ID | Status | Type | Slicing strategy | Blocked by | Edge type | Unlock evidence | Observable outcome | Verification seam | Maximum claim | Scope class | MCP profile | Transport status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `TASK-EPB-002-R1` | SUPERSEDED | IMPLEMENTATION | TRACER_BULLET | none | none | none | Core service physically verifies an immutable precommitted Candidate and atomically forms pending-approval state | Real immutable precommitted Candidate plus service hostile tests | Core lifecycle adoption service independently verified; no public Gateway action, EPB adoption, approval, integration, or remote claim. | medium | CANDIDATE | READY |
| `TASK-EPB-003-R1` | ACTIVE | IMPLEMENTATION | TRACER_BULLET | none | none | none | Typed fail-closed public external Candidate adoption reaches pending approval only | Real Gateway/CLI action plus downstream-effect hostile tests | Adoption capability independently verified; no EPB approval, integration, remote merge, release, production, Task4, or public-stability claim. | medium | CANDIDATE | READY |

## 4. Ready candidates and frontier selection

- **Dependency-ready candidates:** `TASK-EPB-003-R1`
- **Selected frontier:** `TASK-EPB-003-R1`
- **Selection rationale:** Exact core successor `913a90900b906f31d18e35efdd853863aad92400` / tree `96fb94032757f492ca49336a31d90d3ae700d6f7` was independently accepted; its dependency is physically satisfied and the typed public seam is now the highest-value frontier.
- **Exact unblock condition:** none

## 5. Campaign authority and non-goals

Owner master authority permits same-mission Task Card correction, bounded implementation, independent acceptance, lifecycle adoption, governed approval/integration, GitHub exact-head merge, and post-merge verification. This bundle creates no approval, integration, merge, release, production, Task4, signing, or trust-root authority. Workers cannot self-accept or perform downstream effects.

## 6. Supersession and change history

- `TASK-EPB-002-R1` supersedes the mixed-scope `TASK-EPB-002` Candidate contract after fresh rejection evidence.
- `TASK-EPB-003-R1` supersedes the historical public Candidate dependency only after the core successor is independently accepted.
- Validator status `SUPERSEDED` on `TASK-EPB-002-R1` records that its execution frontier was consumed by exact accepted Candidate `913a90900b906f31d18e35efdd853863aad92400`; it does not classify that Candidate as rejected. Validation receipt SHA-256 is `e7be5fb04a645309730cdd5d1e14b13298e3d2a7f87c0e38fc24e6a054a172a6`; independent acceptance receipt SHA-256 is `4dc212cd349f3f38954dc5849849c6ff31ee5cc8b0f7af24fea03bf03fda659e`.
- The original campaign bundle remains immutable historical governance evidence.
