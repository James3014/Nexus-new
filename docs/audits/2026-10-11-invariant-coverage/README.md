---
artifact_authority: evidence
status: audit-snapshot
purpose: Repository-wide invariant enforcement coverage audit (2026-10-11). Evidence only; not normative authority.
---

# Invariant Enforcement Coverage Audit — 2026-10-11

**Question audited:** does each important invariant that Nexus claims, or depends on, have **executable enforcement** at the **correct authority boundary**? The correct boundary is the consumer or sink that performs the effect, not only a producer or validator.

This is not a Golden Behavior Corpus. It does not track one known bug. No production code was changed.

## Method

For every invariant the audit recorded:

`Invariant → normative authority → enforcement point → caller paths → positive evidence → negative/tamper evidence → runtime evidence → coverage status`

Coverage status values:

| Status | Meaning |
|---|---|
| `ENFORCED` | Enforced where the effect happens, with rejection evidence. |
| `PARTIALLY_ENFORCED` | Enforced on some paths or fields only. |
| `TEST_ONLY` | Checked only in tests, not at runtime. |
| `DOCUMENTED_ONLY` | Stated in docs or contracts, with no executable check. |
| `ENFORCED_AT_WRONG_LAYER` | Checked at the producer, or by a self-hash, but not at the consumer. |
| `BYPASS_PATH_EXISTS` | Enforced, but an alternate path reaches the effect without the check. |
| `EVIDENCE_INSUFFICIENT` | Not enough evidence to classify. |

Every gap counted as confirmed has a minimal reproducer in `repro/<repo>/` that imports the real production code. Each reproducer was run, and the output quoted in its Issue is that real output.

**Private-repository findings** (`nexus-deployment-lab`, `nexus-hardware-lab-research`) are referenced here by Issue number only. Their details and reproducers live in those private Issues.

**Baseline HEADs:**

| Repository | HEAD |
|---|---|
| Nexus-new | `12830c3` |
| devspace | `e7f6397` |
| nexus-core | `61d06ff` |
| nexus-runtime | `650ec60` |
| nexus-learning | `e1c7fa0` |
| nexus-open-swe-runtime | `79a1262` |
| nexus-workbench | `5ca3049` |
| nexus-opencli-reviewer | `fd3eaf8` |
| repository-intelligence-engine | `b76c9c7` |
| repo-learning | `94f448f` |
| nexus-deployment-lab | `ac0f38c` |
| nexus-hardware-lab-research | `ee3c597` |

## Ranked highest-risk uncovered invariants

| Rank | Issue | Repo | Invariant | Status | Why it ranks here |
|---|---|---|---|---|---|
| 1 | Nexus-new#1749 | Nexus-new | No silent GOVERNED→DIRECT downgrade; Owner-only lane rebind | BYPASS_PATH_EXISTS + ENFORCED_AT_WRONG_LAYER | The required merge check `Trusted verifier` lets the PR author pick `OWNER_INLINE`. The Owner rebind is an unkeyed self-hash, and `sender` is ignored. PRs numbered below 1061 skip the check by number. This is the governed merge-authority boundary itself. |
| 2 | Nexus-new#1750 | Nexus-new | Owner standing grant is Owner-issued; Task Card only for a Ready Issue with frozen paths; Project Entry precedes governed effects | ENFORCED_AT_WRONG_LAYER + DOCUMENTED_ONLY | "Owner" `GITHUB_MERGE`/`TASK_CARD_CREATE` authority is minted from a caller boolean. `project_binding_hash` has no consumer. |
| 3 | Nexus-new#1754 | Nexus-new | Required CI gates cannot be rewritten by the candidate they gate | ENFORCED_AT_WRONG_LAYER | The secret audit, exact-base tool gate and impact gate run PR-head copies of their own scripts. A PR can self-certify `G2_VERIFIED`. There is no `sk-ant-` detector. Bandit and Pyright run only on `nexus/core/**`. |
| 4 | Nexus-new#1752 | Nexus-new | Workers cannot push or commit, hold no credentials, and die on timeout | BYPASS_PATH_EXISTS | `git -C . push` and `gh repo delete` are accepted. `HOME` is inherited, so gh and git credentials are readable. A `setsid` descendant survives `killpg`. |
| 5 | Nexus-new#1761 | Nexus-new | Model execution requires Workforce Admission; CapabilityPlanner is the sole selector | BYPASS_PATH_EXISTS | Untracked (NONE / OWNER_INLINE) tasks pick the provider themselves and pass the provider boundary. |
| 6 | Nexus-new#1757 | Nexus-new | Missing verifier artifact or source hash fails claim gates closed (#453) | BYPASS_PATH_EXISTS | The local_model_executor and local_heal adapters mint `gate_passed` / `public_claim_safe`. The hybrid route never compares its two hashes. |
| 7 | devspace#496 | devspace | File tools never leave the approved root | BYPASS_PATH_EXISTS | The lexical check is defeated by a symlink, giving read/write outside the root (for example `~/.devspace/auth.json`). |
| 8 | nexus-open-swe-runtime#112 | open-swe | The effect-authorization write ceiling binds physical writes | BYPASS_PATH_EXISTS | `write_paths` is never consulted by `ScopedRepairBackend`. The receipt still claims BOUND authorization. |
| 9 | nexus-learning#85 | learning | An adoption never mutates planner, route or workforce authority | ENFORCED_AT_WRONG_LAYER | The consumer checks only its self-hash. A forged `CapabilityPlanner.force_route` / `workforce_admission: open` delta is persisted and projected. |
| 10 | nexus-runtime#137 | runtime | OUTCOME_UNKNOWN is never a blind retry | BYPASS_PATH_EXISTS | Stripping the unhashed `effect_journal_bindings` makes replan re-dispatch the same logical effect. |
| 11 | Nexus-new#1751 (+ #652) | Nexus-new | Independent acceptance is from a non-implementer, for this PR | PARTIALLY_ENFORCED | A negated verdict ("do not accept candidate") is accepted. The comment is not bound to the PR. A self-authored comment is accepted (issuer authentication is owned by #652). |
| 12 | Nexus-new#1758 | Nexus-new | Integration and approval consume acceptance, a grant and a recomputed receipt hash | BYPASS_PATH_EXISTS | The competition integrator merges unverified output to `nexus/integration*`. Legacy `approve_promotion` approves with no grant. |
| 13 | nexus-core#203 | core | `--require-trusted-config` fails closed | BYPASS_PATH_EXISTS | A candidate-chosen `base_ref=HEAD~1` produces `kind=base-ref` from the candidate's own config. CI is mitigated by `--expect-config-commit`. |
| 14 | Nexus-new#1753 | Nexus-new | The verifier runs with no shell, on every path | BYPASS_PATH_EXISTS | `sh -c` is exempt. `cli_pregate` runs `shell=True` with the full env (GH_TOKEN). |
| 15 | devspace#498 | devspace | Workers stay within `writePaths` | ENFORCED_AT_WRONG_LAYER | The observer cannot see `.git/hooks` or ignored files, so a planted hook executes on `git_commit`. |

Remaining confirmed gaps, MEDIUM/LOW:
- **Nexus-new:** #1755 (redaction misses), #1756 (degenerate assist patch reported as COMPLETED), #1759 (zero-verifier contract counts as verified), #1760 (Candidate receipt identity not bound).
- **devspace:** #497 (push to the remote default branch), #499 (artifact host matched by prefix only).
- **nexus-core:** #204 (Nexus Verify reports VALID on forged evidence), #205 (issue-check repository binding; runtime verify).
- **nexus-runtime:** #138 (custom runner skips effect authorization).
- **nexus-open-swe-runtime:** #113 (legacy-path symlink).
- **nexus-learning:** #84 (worker-write policy poisoning), #86 (scorecard pair count trusted), #87 (lesson content address).
- **nexus-workbench:** #21 (target identity unbound).
- **nexus-opencli-reviewer:** #84 (`receipt_id` not recomputed), #85 (wheel hash not checked), #86 (WebMCP Origin/Host).
- **repository-intelligence-engine:** #86 (readiness re-hash forgery).
- **repo-learning:** #50 (contract fingerprint fails open), #51 (mastery and privacy enforced only at the producer).
- **Private repos:** nexus-deployment-lab #19 and #20; nexus-hardware-lab-research #1.

### Cross-cutting patterns

1. **Self-hash used as authority.** Unkeyed `sha256(canonical_json)` proves consistency, not provenance. Instances: lane rebind, effect authorization, adoption, receipts in core/runtime, RIE readiness, the reviewer `receipt_id`.
2. **Producer validates; consumer trusts.** Instances: claim adapters, `approve_promotion`, adoption, worker writes, the learning backend, the readiness verifier.
3. **Identity present but outside the decision.** Instances: `sender`, `comment_author`, `project_binding_hash`, effect-authorization repository/workspace, workbench `target_identity`, issue-binding repository, Candidate receipt `task_id`/`contract_hash`.
4. **Fail-closed on one entrypoint only.** Instances: gateway versus legacy MCP/CLI (approval, zero-verifier, admission), `execute_attempt` versus `custom_runner`, ADMIT versus the legacy worker path.
5. **Candidate-controlled gate logic.** Instances: CI scripts from PR head (#1754, related #1619); candidate-chosen `base_ref` (nexus-core#203).
6. **Shape-only tests.** Instances: `status_code in {200,422}`, `ownerConfirmation` presence, tamper tests that do not recompute the self-hash, schema tests never wired into src.

## INVARIANT_COVERAGE_MATRIX

Columns:
- **Auth** = normative authority
- **Enf** = enforcement point
- **Callers** = caller paths
- **+** = positive evidence
- **−** = negative/tamper evidence
- **RT** = runtime/CI evidence
- **Issue** = owning Issue, where one exists

### Nexus-new — governance, merge and authority

| ID | Invariant | Auth | Enf | Callers | + | − | RT | Status | Issue |
|---|---|---|---|---|---|---|---|---|---|
| G1 | No silent GOVERNED→DIRECT downgrade | AGENTS.md; TEC:395-397; op-mode yaml | `trusted_merge_lane_gate.py:554-577` | any PR body | test :157,169 | no OWNER_INLINE-on-governed test | trusted-deletion-anchor.yml | BYPASS_PATH_EXISTS | #1749 |
| G2 | Owner lane rebind is genuine | AGENTS.md:92-95; TEC:410-416 | gate :396-469 (self-hash) | PR body edit | :180 | :254 hash-consistency only | same | ENFORCED_AT_WRONG_LAYER | #1749 |
| G3 | Every new PR carries a binding and closure intent | TEC:397-399 | gate :490-497 | 48 open PRs < 1061 | :150 | :140 asserts legacy PASS | same | BYPASS_PATH_EXISTS | #1749 |
| G4 | Trusted verifier binds the exact head and PR | AGENTS.md | anchor workflow :279 | pull_request_target | yes | yes | ruleset-required | ENFORCED | — |
| G5 | Task Card change during merge blocks | TEC:422-424 | gate :585-591 | — | — | test :216 | yes | ENFORCED | — |
| G6 | Standing grant is Owner-issued | AGENTS.md:57-77 | `unified_mcp_gateway.py:3544-3715` | MCP grant tool | yes | shape-only | — | ENFORCED_AT_WRONG_LAYER | #1750 |
| G7 | Grant creates a card only for a Ready Issue with frozen paths | AGENTS.md:76-77 | gateway :3300-3388 | task_card_create | — | none | — | DOCUMENTED_ONLY | #1750 |
| G8 | Project Entry precedes governed effects (#842) | AGENTS.md:49-63 | none (hash unconsumed) | 12 effectful tools | — | none | — | DOCUMENTED_ONLY | #1750 |
| G9 | Independent acceptance is from a non-implementer | AGENTS.md:74-81 | `github_orchestration.py:540-594` | evidence CLI | test :1149 | SHA mismatch only | — | PARTIALLY_ENFORCED | #1751, #652 |
| G10 | MERGE_INTENT is evidence; drift re-checked | AGENTS.md:81 | `github_orchestration.py:244-294` | completion loop | yes | yes | — | ENFORCED | — |
| G11 | Evidence hashes (checks, reviews, lineage) are recomputed | contracts | `contracts/github_orchestration.py:420-441` | — | yes | yes | — | ENFORCED | — |
| G12 | GOVERNED merge needs a `GITHUB_MERGE` grant | op-mode yaml | `github_orchestration.py:297-342` | in-repo loop only; external sink | yes | yes | — | EVIDENCE_INSUFFICIENT (sink not in repo) | — |
| G13 | Expected-head CAS and fresh main at merge | AGENTS.md:78-80 | external merge tool; ruleset non-strict | — | — | — | — | EVIDENCE_INSUFFICIENT | — |
| G14 | #441 requalification before rebase | AGENTS.md:83-91 | completion_loop :605-621 (governed) | DIRECT has no sink | yes | yes | — | PARTIALLY_ENFORCED | — |
| G15 | Operating mode fails closed when missing or invalid | AGENTS.md:28-29 | none (file only hashed) | — | — | text/shape test | — | DOCUMENTED_ONLY | — |
| G16 | Fast Start #549 is advisory only | AGENTS.md:48 | none (producer only) | agent | — | doc-grep test | producer workflows | DOCUMENTED_ONLY | — |
| G17 | Policy lane gate | workflow | head `policy_lane_precommit.py` | path-filtered | yes | — | not required | PARTIALLY_ENFORCED | — |
| G18 | Delegated workers never merge | AGENTS.md:70-71 | none (0 required approvals) | — | — | — | — | DOCUMENTED_ONLY | — |

### Nexus-new — lifecycle, receipts, claims and workforce

| ID | Invariant | Auth | Enf | Callers | + | − | RT | Status | Issue |
|---|---|---|---|---|---|---|---|---|---|
| L1 | Missing verifier artifact or source hash fails claim gates closed | AGENTS.md:186; CLAIM overlay | `capability_receipt_adapters.py:533-600` | local_model_executor / local_heal adapters bypass | — | claim_gate rejects | — | BYPASS_PATH_EXISTS | #1757 |
| L2 | HybridRouteDecision is a projection; hashes equal | AGENTS.md:182-183 | `contracts/hybrid_route.py:208-224` | LocalHeal | — | boolean only | — | BYPASS_PATH_EXISTS | #1757 |
| L3 | Completion requires a verifier | AGENTS.md:115 | gateway only | legacy MCP / CLI / service | yes | none | — | PARTIALLY_ENFORCED | #1759 |
| L4 | Candidate is receipt-bound to its task, contract and lease | AGENTS.md:107-110 | `candidate_commit.py:101-257` | main + recovery | yes | none | — | PARTIALLY_ENFORCED | #1760 |
| L5 | Integration needs acceptance, a grant and a verified receipt | AGENTS.md:71-82 | `integrate_authorized_task_state` | competition `integrate_task_state` bypass | yes | none | MCP tool | BYPASS_PATH_EXISTS | #1758 |
| L6 | Models cannot approve; approval needs a grant | AGENTS.md:116 | gateway :6331 | legacy MCP / CLI `approve_promotion` | test enshrines grant-less | downstream only | — | PARTIALLY_ENFORCED | #1758 |
| L7 | `verified_receipt_hash` recomputed at consumers | CLAIM overlay | verify_task, adoption replay | approve / integrate / recovery do not | — | — | — | PARTIALLY_ENFORCED | #1758 |
| L8 | Model execution requires Workforce Admission | WORKFORCE overlay | tracked dispatch only | untracked submits, `_assist_submit` | yes | tracked only | — | BYPASS_PATH_EXISTS | #1761 |
| L9 | CapabilityPlanner is the sole selector | AGENTS.md:182 | envelope checked if present | `build_contract` picks the worker | — | — | — | BYPASS_PATH_EXISTS | #1761 |
| L10 | Admission receipt is fresh and untampered | WORKFORCE overlay | `_workforce_admission_readback_matches` | tracked / retry | yes | yes | — | ENFORCED | — |
| L11 | Dispatch envelope identity | AGENTS.md | `_revalidate_tracked_dispatch_task_card` | tracked | yes | yes | — | ENFORCED (tracked) | — |
| L12 | Verifier evidence consistency (exe sha, argv, env) | CLAIM overlay | `candidate_verifier.py:217-250` | all | yes | yes | — | ENFORCED | — |
| L13 | Closure acceptance bound to artifact digest | AGENTS.md:80 | service :10461-10481 | gateway closure | yes | yes | — | ENFORCED | — |
| L14 | Closure reviewer is not the implementer | AGENTS.md:71 | advisory reducer only | closure path | — | — | — | EVIDENCE_INSUFFICIENT | #652 |
| L15 | Integration authorization bound to recomputed state | AGENTS.md:79-82 | `validate_current` with self-fallbacks | service integrate | — | — | — | PARTIALLY_ENFORCED (mitigated) | — |
| L16 | Release gate is real | CLAIM overlay | `release/control_plane.py` returns True | unreferenced | — | — | — | DOCUMENTED_ONLY (dead stub) | — |
| L17 | `public_claim_allowed` never unlocked | evidence/claim_boundary.py | ClaimBoundary | all | yes | yes | — | ENFORCED | — |

### Nexus-new — runtime, sandbox and CI

| ID | Invariant | Auth | Enf | Callers | + | − | RT | Status | Issue |
|---|---|---|---|---|---|---|---|---|---|
| R1 | Worker cannot commit, push or publish | AGENTS.md; cli_worker.py:28-59 | `_validate_worker_argv` :105-131 | all worker launches | yes | simple form only | runtime | BYPASS_PATH_EXISTS | #1752 |
| R2 | No GitHub credential in a worker | cli_worker.py:133-150 | env allowlist (HOME kept) | same | yes | env keys only | runtime | PARTIALLY_ENFORCED | #1752 |
| R3 | Timeout kills the process tree | candidate_verifier evidence | cli_worker.py:409-420 | same | yes | none | runtime | PARTIALLY_ENFORCED | #1752 |
| R4 | Verifier runs without a shell | cli_worker.py:1 | candidate_verifier.py:181-196 | verify | yes | `;` only | runtime | BYPASS_PATH_EXISTS | #1753 |
| R5 | All verifier paths use the scrubbed launcher | same | — | `cli_pregate` `shell=True` | — | none | engine | BYPASS_PATH_EXISTS | #1753 |
| R6 | Secrets redacted in trajectory evidence | trajectory_continuity.py | `_SECRET_PATTERNS` | executors | yes | few formats | runtime | PARTIALLY_ENFORCED | #1755 |
| R7 | Degenerate output fails closed | AGENTS.md | `_assist_refresh` | assist | yes | garbage only | runtime | PARTIALLY_ENFORCED | #1756 |
| R8 | Gateway reads confined to the workspace | gateway | `_safe_relative_path`, `_safe_search_target` | read / search | yes | partial | runtime | ENFORCED | — |
| R9 | Governed push only to `nexus/integration*` with a grant | AGENTS.md | `governed_push.py:118-170` | push manager | yes | partial | runtime | ENFORCED (at this sink) | — |
| R10 | Lifecycle JSON not hand-edited | AGENTS.md | schema only, no seal | `_read_state` | — | none | — | DOCUMENTED_ONLY | — |
| R11 | Git history has no secrets | secret-audit workflow | PR-head scanner | PR / push | yes | none | CI | ENFORCED_AT_WRONG_LAYER | #1754 |
| R12 | Bandit and Pyright gate security code | security/typecheck workflows | `nexus/core/**` only | PR | — | none | CI | PARTIALLY_ENFORCED | #1754 |
| R13 | Pytest regression gate is trustworthy | pytest.yml | head `pr_impact_gate.py` | PR | — | — | CI | ENFORCED_AT_WRONG_LAYER | #1754 (related #1619) |
| R14 | Actions pinned; least privilege | #592 | most SHA-pinned; `upload-artifact@v4` and `continue-on-error` remain | — | — | — | CI | PARTIALLY_ENFORCED | — |

### devspace

| ID | Invariant | Enf | Status | Issue |
|---|---|---|---|---|
| D1 | File tools stay within the approved root | `roots.ts:21-57` (lexical) | BYPASS_PATH_EXISTS | #496 |
| D2 | `git_push` never targets the default branch | `git-candidate.ts:618-638` (fails open) | PARTIALLY_ENFORCED | #497 |
| D3 | `git_push` requires a managed worktree | `server.ts:6489` | ENFORCED | — |
| D4 | Worker stays within `writePaths` | `workspace-reconciliation.ts:108-124` (post hoc, blind to `.git` and ignored files) | ENFORCED_AT_WRONG_LAYER | #498 |
| D5 | `.git` never inside `writePaths` | `local-effect-enforcement.ts:131` (prefix only) | PARTIALLY_ENFORCED (suspected) | — |
| D6 | Governed lane never becomes OWNER_DIRECT | literal / `.strict()` contract | ENFORCED | — |
| D7 | MCP needs an owner-approved OAuth bearer | `oauth-provider.ts`, `requireBearerAuth` | ENFORCED | — |
| D8 | Host operations pinned by exe sha and argv | `host-operation-policy.ts` | ENFORCED (TOCTOU suspected) | — |
| D9 | Artifact download only from trusted hosts | `incoming-artifacts.ts:12` (prefix) | PARTIALLY_ENFORCED | #499 |

### nexus-core and nexus-runtime

| ID | Invariant | Enf | Status | Issue |
|---|---|---|---|---|
| C1 | Effective config from base ref; `--require-trusted-config` | `local_golden_path.py:575,1704` | BYPASS_PATH_EXISTS (CI mitigated) | core#203 |
| C2 | Issue binding tied to origin repository | init only; `check_issue` trusts the file | PARTIALLY_ENFORCED | core#205 |
| C3 | Issue contract unchanged since binding | `issue_golden_path.py:465` | ENFORCED | — |
| C4 | Receipt self-hash recomputation | `local_golden_path.py:2230` | ENFORCED (integrity only) | — |
| C5 | `subject_head` derived from inputs | shape only | DOCUMENTED_ONLY (signature-reliant) | — |
| C6 | CI receipt authenticity (Sigstore + `--expect-*`) | receipt-verify action | ENFORCED | — |
| C7 | Nexus Verify VALID only for trusted evidence | `nexus_verify.py:331-445` | ENFORCED_AT_WRONG_LAYER | core#204 |
| C8 | Runtime verify means produced by this runtime | `service.py:598,424-432` | ENFORCED_AT_WRONG_LAYER | core#205 |
| C9 | Verifier cannot mutate the target | post-tree compare | ENFORCED | — |
| C10 | Material transitions need an authorized author | `check_repository:1717` | ENFORCED | — |
| C11 | Fork guard; no candidate code on the runner | workflow `if:` | ENFORCED | — |
| RT1 | Effect authorization fails closed | `coordinator.py:685` (`execute_attempt` only) | BYPASS_PATH_EXISTS | runtime#138 |
| RT2 | Effect authority comes from an external authority | unkeyed hash | ENFORCED_AT_WRONG_LAYER | runtime#138 |
| RT3 | Authorization identity binding | `assert_identity` skips None | PARTIALLY_ENFORCED | — |
| RT4 | OUTCOME_UNKNOWN never blind retry | `runtime.py:3124-3131` | BYPASS_PATH_EXISTS | runtime#137 |
| RT5 | Receipt hash lineage | `validate_receipt_base` | ENFORCED (covered fields) | — |
| RT6 | Effect journal resolves UNKNOWN only via reconcile | public `transition()`; no tests | PARTIALLY_ENFORCED / TEST gap | — |

### nexus-learning, nexus-open-swe-runtime and nexus-workbench

| ID | Invariant | Enf | Status | Issue |
|---|---|---|---|---|
| O1 | Effect-authorization ceiling never widened | `cli.py:180-210` ignores `write_paths` | BYPASS_PATH_EXISTS | open-swe#112 |
| O2 | Authorization repository / workspace bind execution | hashed only | DOCUMENTED_ONLY | open-swe#112 |
| O3 | Tool surface ⊆ `selected_tools` | `cli.py:701,720` | ENFORCED | — |
| O4 | Writes confined to authorized paths | lexical; symlink check on ADMIT only | BYPASS_PATH_EXISTS | open-swe#113 |
| O5 | OUTCOME_UNKNOWN reconcile-only | `cli.py:2464-2522` | ENFORCED | — |
| O6 | Worker cannot approve, merge or push | fixed tool universe | ENFORCED | — |
| O7 | No secrets in OpenCLI child env | name denylist | PARTIALLY_ENFORCED | — |
| O8 | Runtime identity bound to modules | `_package_sha256` | ENFORCED | — |
| N1 | Only QUALIFIED episodes tune policy | producer only; `append_worker_write` raw | BYPASS_PATH_EXISTS | learning#84 |
| N2 | Explicit state root | `state_root.py` | ENFORCED | — |
| N3 | Adoption never mutates planner or workforce | consumer self-hash only | ENFORCED_AT_WRONG_LAYER | learning#85 |
| N4 | ADOPT needs genuine eligible pairs | trusts scorecard summary | BYPASS_PATH_EXISTS | learning#86 |
| N5 | Independent validator | substring checks | PARTIALLY_ENFORCED (suspected) | — |
| N6 | Simulated lessons not retrievable | `lesson_id` excludes origin | PARTIALLY_ENFORCED | learning#87 |
| N7 | No runtime authority imports | AST test | ENFORCED (static) | — |
| N8 | Frozen research modules | marker test | TEST_ONLY | — |
| W1 | Execution bound to target identity | string compare only | BYPASS_PATH_EXISTS | workbench#21 |
| W2 | READY claimed once; UNKNOWN reconciles | `store.py:294-414` | ENFORCED | — |
| W3 | Records immutable-idempotent | `store.py:112-214` | ENFORCED (except Candidate) | — |
| W4 | G2 executor physically read-only | `read_only_executor.py` | ENFORCED | — |
| W5 | Candidate claim ceiling | `model.py:366` | ENFORCED | — |
| W6 | `effectiveness_claim_allowed` is false | `benchmark.py:586` | ENFORCED (independence partial) | — |

### nexus-opencli-reviewer, repository-intelligence-engine and repo-learning

| ID | Invariant | Enf | Status | Issue |
|---|---|---|---|---|
| V1 | Publication is comment-only, PRE_REVIEW_ONLY | `publication.py:83-121` | ENFORCED | — |
| V2 | Fresh PR identity before publish | `_fresh_identity` | ENFORCED (identity substitutable, see V3) | — |
| V3 | `receipt_id` binds identity and response | none at sink | BYPASS_PATH_EXISTS | reviewer#84 |
| V4 | No duplicate publication | journal + author login | ENFORCED | — |
| V5 | CFI capsule hash-bound | `ci_failure_evidence_manifest` | ENFORCED | — |
| V6 | Vendored wheel matches provenance | tests only; action does not check | ENFORCED_AT_WRONG_LAYER | reviewer#85 |
| V7 | Action never runs PR code; read-only token | composite env | ENFORCED | — |
| V8 | WebMCP localhost-only | no Host/Origin check | BYPASS_PATH_EXISTS | reviewer#86 |
| E1 | CFI report cannot be re-hashed | `verify_ci_failure_intelligence_report` | ENFORCED | — |
| E2 | Readiness cannot be re-hashed | identity / type only | BYPASS_PATH_EXISTS | RIE#86 |
| E3 | Terminal bound to a 40-hex head | `_validate_head` | ENFORCED | — |
| E4 | Self-action immutably pinned | mutable tag | DOCUMENTED_ONLY | RIE#78 (partial) |
| E5 | Consumers verify `content_sha256` | length check | PARTIALLY_ENFORCED | — |
| K1 | Installed Skill matches pinned contract hash | `deployment.py:131` (fails open) | BYPASS_PATH_EXISTS | repo-learning#50 |
| K2 | Loaded-contract attestation reflects loaded bytes | self-report | DOCUMENTED_ONLY | — |
| K3 | Consumer AGENTS.md pin compared | none | DOCUMENTED_ONLY | — |
| K4 | Mastery ceiling at persistence | producer only | ENFORCED_AT_WRONG_LAYER | repo-learning#51 |
| K5 | `learning-event.v1` schema at sink | tests only | TEST_ONLY | repo-learning#51 |
| K6 | Projection bound to the ledger | `read_current_state` | ENFORCED | — |
| K7 | Event id idempotency | `backends.py:175` | ENFORCED | — |

### Private repositories

| Repo | Findings (details in the private Issues) | Status | Issues |
|---|---|---|---|
| nexus-deployment-lab | Activation and canary hash recomputation; doctor rollback ordering | PARTIALLY_ENFORCED / BYPASS_PATH_EXISTS | #19, #20 |
| nexus-hardware-lab-research | Archive manifest verification | DOCUMENTED_ONLY | #1 |

## Suspected, not reproduced (no Issue filed)

These are candidates for follow-up only, not confirmed gaps:

- **Required-check spoofing.** The "Nexus Core issue completion" required context has no `integration_id`. The ruleset is non-strict. `.github/workflows/**` is not rule-protected.
- **DIRECT finish on a governed task.** `nexus_task_finish` with `DIRECT_CANONICAL` on a governed `task_id`.
- **Caller-overridable hashes.** `canonical_core_transport` lets the caller override binding/contract hashes.
- **Attempt-ID skip in the merge gate.** The gate skips the attempt-ID check when the card has no `attempt_id:`.
- **nexus-runtime `RetryService` and placement.** These do not consult the effect journal for OUTCOME_UNKNOWN.
- **open-swe reconcile identity checks.** They skip any field the request omits.
- **nexus-learning qualification.** `build_episode_from_receipts` self-declares qualification.

## Reproducers

They are in `repro/<repo>/` and are evidence only. They assume checkouts at `/home/user/<repo>`. For example:

```
cd /tmp && python3 <path-to>/repro/Nexus-new/merge_lane_gate_governed_downgrade.py
```

The TypeScript devspace reproducers run with `npx tsx` from a devspace checkout after `npm ci`, with `DEVSPACE_SRC` set to that checkout's `src`.
