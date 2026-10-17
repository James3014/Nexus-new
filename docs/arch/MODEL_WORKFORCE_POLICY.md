# Nexus Model Workforce Policy

**Authority:** current

**Owner:** James Chen

**Status:** active, evidence-bounded

**Machine source:** `nexus/config/model_workforce.yaml`

**Benchmark matrix:** `nexus/config/model_three_arm_matrix.yaml`
**Last verified:** 2026-10-12

This file defines workforce eligibility: which model workers Nexus may admit,
the context each worker may receive, its autonomy ceiling, and the conditions
that require escalation. It does not select routes or capabilities, and it does
not replace `CapabilityPlanner`, `HybridRouteDecision`, execution
authorization, Verifier, Receipt, Learning, Git safety, or account-pool policy.

Provider eligibility is open across the registered adapter surface. `auto` and
`agy` are defaults, not an allowlist. An explicit provider still requires a
registered adapter, exact model identity, executable/authorization preflight,
bounded scope, parser/verifier evidence, and a receipt. Unknown providers fail
closed. Cline CLI / `glm-5.2` is registered as a conditional L1 bounded
candidate; its registration does not grant route, approval, integration, push,
or production-claim authority.

The `workers` map in `nexus/config/model_workforce.yaml` is the single model
identity source for OpenCode, MiMo, Grok, Ollama/local models, Cline, and the
other registered providers. A request may use a worker ID, an exact model ID,
or a provider default; blocked/disabled identities still fail closed under the
existing workforce admission rules.

## 1. Interpretation rules

A CLI being installed, a provider catalog listing a model, or a model producing one good answer does not make it an approved Nexus worker.

Every candidate is governed across three distinct architectural layers:

1. **Semantic capability lineage** — the underlying model family and reasoning capability lineage (e.g. `gemini-3.7-flash-medium`, `deepseek-v4-flash`). Models sharing lineage share reasoning characteristics but do not share execution identity or admitted authority.
2. **Exact execution identity** — the specific provider, exact model string, and transport adapter (e.g. `agy` with `gemini-3.7-flash-medium`, `opencode` with `opencode/deepseek-v4-flash-free` vs `opencode` with `opencode-go/deepseek-v4-flash`). Identity matching is exact and fails closed.
3. **Admitted authority** — the repository-governed state, autonomy ceiling (e.g. L3 for Gemini 3.7 Flash Medium, L2 for DeepSeek V4 Flash), admitted roles, required controls, and forbidden actions recorded in `nexus/config/model_workforce.yaml`. Admitted authority is never automatic from lineage or execution availability.

`CapabilityPlanner` is the sole route and capability-selection authority.
`HybridRouteDecision` is a Planner-derived decision contract/projection, not a
second selector, router, or planner. This policy is a workforce eligibility
constraint consumed after route authorization, not another router or selector.
Since 2026-10-13 the sole `fast_bounded_implementation` default route is
`agy_flash_38` (Gemini 3.8 Flash Medium; see section 15). DeepSeek V4 Flash is
not a default route.
Neither worker is granted L4 autonomy; L4 remains experimental and non-admitted.

## 2. Uniform three-arm benchmark status

On 2026-07-29, all 25 enrolled models received the same composite task and deterministic verifier:

- **Bare** — model baseline without Nexus semantic assistance.
- **Nexus-bounded** — compact diagnosis, assertions, and exact schema.
- **Nexus-full** — Planner, evidence, model call, Verifier, Learning, and Receipt wrapping.

The task covered started-call accounting, a bounded Python implementation, and claim-boundary judgment. There were 11 deterministic checks.

| Metric | Result |
|---|---:|
| Enrolled models attempted | 25 / 25 |
| Models with semantic scores | 21 |
| Provider/client blocked | 4 |
| Models scoring 11/11 on all three arms | 6 |
| Models proving Full receipt closure | 0 |
| Stable promotions proven | 0 |

The 2026-07-29 matrix is a historical baseline and comparative diagnostic instrument. Historical 2026-07-29 scores remain frozen and immutable. Future requalification uses cumulative evidence, stable-floor regression, target/current frontier assessment, failure-family/hidden probes, and transport/protocol/isolation verification rather than requiring re-execution of the initial matrix from zero.

## 3. Current active workforce

| Worker | Current role | Ceiling | Preferred context | Current status |
|---|---|---:|---|---|
| Codex Luna — `gpt-5.6-luna` | Main engineering, milestone closure, integration | Historical L3 | Governed mainchain | Available; Codex CLI 0.146.0 with `gpt-5.6-luna` returned exactly `OK` in a read-only smoke on 2026-07-29 |
| Agy Flash — `gemini-3.6-flash-high` | Fast bounded implementation and focused verification | L2 | **Nexus-bounded** | **UNAVAILABLE since 2026-10-13** (Agy 1.3.4 no longer serves Gemini 3.6; section 15); kept registered for history and benchmark lineage (historical benchmark 10/11 → 11/11 → 10/11) |
| Agy Flash Medium — `gemini-3.6-flash-medium` | Bounded candidate/implementation and focused verification only | L1 | **Nexus-bounded** | **UNAVAILABLE since 2026-10-13** (Agy 1.3.4 no longer serves Gemini 3.6; section 15); registered conditional identity kept for history; non-default route |
| Agy Flash 3.7 Medium — `gemini-3.7-flash-medium` | Bounded candidate/implementation and focused verification | L3 | **Nexus-bounded** | **UNAVAILABLE since 2026-10-13** (Agy 1.3.4 rejects the model id; section 15); former `fast_bounded_implementation` default (section 10), now `default_route: false`; registered conditional identity and calibration evidence kept for history and not inherited by 3.8 |
| Agy Flash 3.8 Medium — `gemini-3.8-flash-medium` | Bounded candidate/implementation and focused verification | L3 | **Nexus-bounded** | Registered conditional identity; **sole `fast_bounded_implementation` default route since 2026-10-13** (Owner decision, section 15); L3 is the 2026-10-12 registration, no 3.8 calibration ceiling is recorded; exact Task Card, parser/verifier, and independent verification required; experimental L4 non-admitted |
| OpenCLI ChatGPT Web — `opencli_chatgpt/balanced` | Campaign-scoped bounded Candidate generation | L1 | **Nexus-bounded** | Owner-approved conditional identity only for `open-swe-resident-five-repo-canary-20260908`; `balanced` is a mutable UI capability alias, not a fixed backend model revision; never a global default; host transport identity is enforced by External Intelligence activation/runtime gates |
| OpenCLI ChatGPT Web — `opencli_chatgpt/advanced` | External Intelligence consumer bounded Candidate generation | L1 | **Nexus-bounded** | Owner-approved conditional identity only for consumer `external_intelligence` (owner decision 2026-10-13); runs on the personal free plan where `advanced` is the Thinking toggle (`aria-pressed=true`), a mutable UI alias, not a fixed backend model revision; never a global default |
| Grok 4.5 | Independent review, hidden-defect search, evidence audit; bounded candidate generation | L2+ | Bounded or Full semantic context | Available; benchmark 11/11 on all arms |
| OpenCode MiMo — `opencode/mimo-v2.5-free` | Bounded code candidate | L1 | Bounded isolated prompt | Available; admitted ceiling stays L1; 2026-08-17 cumulative calibration records semantic stable floor L1.5 and semantic frontier L3 separately; NOT_PROMOTED; tool-discipline requalification pending; high fixed input-token overhead |
| OpenCode Ling — `opencode/ling-3.0-flash-free` | Bounded code candidate | Current L1 | Bounded isolated prompt | Available; 11/11 all arms; high fixed input-token overhead. The unapproved v2 proposal would lower it to read-only L0 |
| OpenCode DeepSeek V4 Flash — `opencode/deepseek-v4-flash-free` | Bounded OpenCode code candidate | L2 | Bounded isolated prompt | Owner-approved 2026-08-15; admitted autonomy ceiling L2; non-default route; experimental L4 non-admitted; shares semantic capability lineage with `opencode-go/deepseek-v4-flash` while execution identities remain exact and separate; high fixed input-token overhead |
| Cline — `glm-5.2` | Bounded code candidate | L1 | Bounded isolated prompt | Registered conditional; Cline CLI adapter and external-runtime authorization required |
| Local Advisor — `qwen2.5-s2t-advisor:3b` | Classification, extraction, compression, compact diagnosis | L0.5 | **Nexus-bounded only** | Available; 9/11 → 11/11 → 10/11 |
| Local Coder — `qwen2.5-coder:7b-instruct` | Small bounded code candidate | L1 | Bounded exact contract | Available; 10/11 on every arm; no measured Nexus uplift |
| Local Qwen3 — `qwen3:8b` | Bounded reasoning/code shadow candidate, counterexample search | L1 shadow | **Nexus-bounded** | Available; 11/11 → 11/11 → 10/11; Full context caused schema drift |
| Local Qwen3.5 — `qwen3.5:9b` | Provisional bounded reasoning/review candidate, counterexample search | L1 ceiling | **Nexus-bounded** | Re-enabled 2026-08-06 with the official tag; two mutation-free repetitions scored 10/11 on all arms using API `think:false`; code assignment remains blocked pending counterexample and role-specific suites |

### Assignment consequences

- The 3B model is the clearest measured Nexus-bounded uplift. It must not receive Full governance context or mutate code.
- The 7B model remains a code **candidate** generator because previous repository evidence exists, but this benchmark did not prove uplift or self-verification.
- Qwen3 8B is a stronger bounded shadow candidate than the current 9B reasoning models, but its latency and Full-context regression prevent default promotion.
- Qwen3.5 9B is conditionally re-enabled for bounded reasoning/review and counterexample search only. It is not admitted for Full-context or code assignments until the counterexample and role-specific suites pass; its current evidence does not authorize a public claim.
- OpenCode free models are subscription-free, not context-cheap. Typical calls carried roughly 20k+ fixed input tokens. They require isolated execution and external verification.
- Grok may review or generate a bounded candidate, but cannot be the sole production-readiness adjudicator.
- Agy should receive a locked task card, exact file scope, and mandatory commands. It should not own architecture authority.
- OpenCLI ChatGPT Web is admitted only for the exact resident canary campaign's `bounded_candidate_generation` demand. Workforce Admission binds the Task Card, isolated workspace, parser, focused verifiers, and independent acceptance; the External Intelligence activation/runtime layer separately binds OpenCLI 1.8.7, Browser Bridge 1.0.24, foreground ephemeral transport, launcher, and runtime artifact identity. It cannot fall back to another provider or claim approval, integration, push, release, production readiness, or public truth.
- The Gemini 3.6 Flash identities (L2 High, L1 Medium) and Gemini 3.7 Flash Medium (L3) are UNAVAILABLE since 2026-10-13. Gemini 3.8 Flash Medium is the sole `fast_bounded_implementation` default at the registered ceiling L3 with no fallback (section 15). DeepSeek V4 Flash stays at ceiling L2 and is not a default route; no L4 authority is granted.

## 4. Conditional, committee-only, and shadow workers

| Model | Permitted use | Why it is not a default worker |
|---|---|---|
| `deepseek-coder:6.7b-instruct` | Committee secondary proposer only | 8/11 → 9/11 → 0/11; Full envelope failure |
| `qwythos:9b` | Bounded second opinion or committee candidate | 10/11 across arms, no uplift, Full latency about 95 s |
| `opencode/deepseek-v4-flash-free` | L2 bounded OpenCode code candidate | Owner-approved 2026-08-15; admitted ceiling L2; candidate-only and externally verified; shares semantic capability lineage with `opencode-go/deepseek-v4-flash` while execution identity remains exact and separate; `default_route: false` |
| `deepseek-coder-v2:lite` | Bounded secondary code candidate | 9/11 → 10/11 → 10/11; missed implementation edge case |
| `qwen2.5:1.5b` | Simple extraction or read-only fixed-schema candidate | 9/11 across arms; no uplift and weak implementation behavior |

These workers require explicit bounded scope, deterministic parsing, focused tests, and an external verifier. They do not gain route, claim, or direct-apply authority.

## 5. Disabled, blocked, quarantined, and experiment-only models

### Operationally blocked

| Model | Blocker |
|---|---|
| Direct Gemini CLI `gemini-3.6-flash` | Client rejected as unsupported; use Agy instead |
| MiMo CLI `xiaomi/mimo-v2.5` | HTTP 402 insufficient account balance |

Blocked models receive no active assignment. Their zero benchmark scores are not semantic model scores.

### Protocol-disabled

| Model | Evidence | Re-enable gate |
|---|---|---|
| *none currently* | | |

`nexus-qwen35-9b-q4km:latest` was retired on 2026-08-06 and replaced by the official `qwen3.5:9b` tag, which correctly consumes API `think:false`; `local_qwen35_9b` was re-enabled as `LOCAL_CONDITIONAL` with an L1 ceiling after two mutation-free three-arm repetitions (10/11 on all arms). Both repetitions missed the same implementation edge case, so the current evidence supports bounded reasoning/review and counterexample search only; code assignment remains blocked until counterexample and role-specific suites pass. `nexus-qwythos-v2-9b-q4km:latest` was removed from the local machine on 2026-08-06; the matrix roster records it under `excluded` with `local_model_removed_from_machine_after_protocol_failure`.

### Resource-risk or experiment-only

| Model | Result | Decision |
|---|---|---|
| `qwen2.5-coder:14b-instruct-q3_K_M` | 10/11 all arms; Full about 80 s | Disabled by default; no quality uplift over smaller workers |
| `deepseek-r1-14b-q4km:latest` | 11/11 all arms; about 92/86/128 s | Explicit high-latency second-opinion experiment only |
| `opencode/big-pickle` | Bare/Bounded pass; Full envelope failure | Experiment only |
| `opencode/nemotron-3-ultra-free` | Bare/Bounded pass; Full streaming failure | Experiment only |
| `opencode/north-mini-code-free` | Bounded pass; Full envelope failure | Experiment only |

### Quarantined

`opencode/laguna-s-2.1-free` scored 11/11 on all arms but wrote `output.json` inside the isolated working directory despite a text-only task. The formal Nexus workspace was not changed, but the behavior demonstrates tool-discipline drift. It remains quarantined until tool denial is verified and a clean three-arm rerun passes.

## 6. Post-route worker dispatch guidance

This section applies only after `CapabilityPlanner` has selected the route and
capabilities and the route has been authorized. It is dispatch preference
guidance for choosing an eligible worker within that already-authorized
execution; it is not a routing order, capability selector, topology selector,
governance selector, or claim decision.

Immediately before dispatch, the caller must obtain a fresh Workforce Admission
receipt. The receipt's `ALLOW`, `BLOCK`, or `ESCALATE` result, exact worker and
model identity, provider, autonomy level, context/scope, policy hash, and
reasons are binding. A stale roster, prior benchmark result, or worker
preference cannot substitute for fresh admission.

Within the authorized route, prefer deterministic completion when rules, AST,
exact search, schema validation, or existing evidence are sufficient. When a
worker is required, use the following role guidance rather than a fixed model
sequence:

1. Use Local Advisor 3B for compact classification, extraction, compression,
   or diagnosis.
2. Use Local Coder 7B for a small bounded code candidate protected by parser,
   compile, and focused tests.
3. Use Qwen3 8B only as a bounded shadow candidate or counterexample searcher.
4. Use Agy for fast bounded online implementation.
5. Use Grok for independent review, hidden defects, or evidence pressure
   testing.
6. Use Codex for complex milestone closure when the governed adapter,
   independent verification, and receipt controls are present.
7. Use OpenCode candidates when subscription-free remote execution is useful
   and high fixed context overhead is acceptable.

These preferences never choose or revise a route, capability, execution
topology, governance depth, or claim outcome. They also do not bypass fresh
admission, parser/verifier gates, receipt requirements, or human authority.

Governance depth is task-driven: the authorized task's risk, mutation scope,
external side effects, ambiguity, integration requirements, and claim/evidence
sensitivity determine the required context and controls. Each dispatch must
respect the combined ceilings for autonomy, context, scope, provider/model
eligibility, resource budget, and claim authority. A worker may be eligible in
one dimension and still be blocked by another; no aggregate score or
Capability Index is introduced.

No Local model is approved as a default Full-context worker. Full context is
not assumed to be better: several models regressed, leaked thinking traces,
changed schema, or lost the answer envelope.

Mandatory escalation applies to architecture or authority choices, ambiguous
product behavior, security or irreversible risk, production/claim adjudication,
unbounded multi-file work, Local disagreement or verifier failure,
integration/runtime closure, and unsafe resource pressure.

## 7. Verification and claim rules

1. Local output is always a candidate, never evidence by itself.
2. Model output must pass a parser or schema before it can enter a receipt.
3. Code candidates require compile/static checks plus task-specific tests.
4. A semantic Full-arm pass does not imply `receipt_complete`, `capability_closure_complete`, production readiness, or public-claim permission.
5. Provider, account, quota, client, transport, and model-reasoning failures must remain separate.
6. A focused suite does not prove a full suite, natural quota behavior, combined E2E, or production readiness.
7. Model identity, provider, transport, actual call count, context arm, and verifier evidence must be recorded.
8. Models may not self-promote or self-assess production readiness.

## 8. How future agents remember

Repository authority, not chat memory, is the memory mechanism:

1. `AGENTS.md` requires this policy and `nexus/config/model_workforce.yaml` before model selection or delegation.
2. `nexus/config/model_workforce.yaml` records current availability, role boundaries, the 25-model benchmark snapshot, and routing constraints.
3. `nexus/config/model_three_arm_matrix.yaml` defines benchmark admission, common arms, and enrolled identities.
4. `tests/contracts/test_model_workforce_policy.py` prevents removal of the benchmark count, blocked/disabled boundaries, Local ceilings, and required authority references.
5. New evidence updates these fixed filenames. Do not create `v2`, `final`, or dated parallel workforce policies.

A future agent must refresh runtime discovery when a CLI/model version changes, a blocked provider recovers, the benchmark snapshot is stale, or a high-cost task begins.

## 9. Promotion gate and requalification protocol

Higher autonomy requires evidence-bound qualification. Rather than re-running the uniform 2026-07-29 three-arm matrix from scratch for every evaluation, the historical three-arm matrix serves as a baseline comparative diagnostic, while future requalification uses cumulative evidence:

- **Stable-floor regression** — proving lower-tier behaviors have not regressed.
- **Target and current frontier evaluation** — targeted testing at the required autonomy boundary.
- **Failure-family and hidden defect probes** — specific checks for known failure modes (e.g. envelope loss, thinking drift).
- **Transport, protocol, and isolation verification** — adapter preflight, CLI version binding, and workspace containment.
- **Distinct evidence phases** — `FIRST_PASS` autonomous generation, hidden defect probes, and `VERIFIER_GUIDED_REPAIR` must remain strictly distinct and cannot be conflated.
- **Experimental boundaries** — observed higher-tier repair or frontier behaviors (such as L4 repair) remain experimental and are NOT admitted autonomy.

Until those gates pass and are formally recorded in `nexus/config/model_workforce.yaml`, the lower autonomy level and stricter context policy remain authoritative.

## 10. Dated Owner-approved amendment — 2026-08-15

The Owner-approved Model Workforce Lineage Writeback amendment is active:

1. **Three-Layer Architectural Separation**:
   - `semantic capability lineage != exact execution identity != admitted authority`.
   - Lineage calibration evidence does not self-promote or grant admission authority.
   - `CapabilityPlanner` remains the sole route and capability-selection authority.

2. **Gemini Medium exact identities**:
   - Existing `agy_flash_medium` remains bound to provider `agy`, exact model `gemini-3.6-flash-medium`, autonomy ceiling **L1**. It is not repurposed by this amendment.
   - New `agy_flash_37_medium` is bound to provider `agy`, exact model `gemini-3.7-flash-medium`.
   - `agy_flash_37_medium` admitted autonomy ceiling: **L3**.
   - `agy_flash_37_medium` is the sole `default_route: true` worker for the
     direct `fast_bounded_implementation` role; `agy_flash_medium` remains
     `default_route: false`.
   - L4 autonomy is **NOT GRANTED**; L4 remains experimental and non-admitted.
   - Exact model matching is fail-closed: 3.6 and 3.7 Medium cannot substitute for one another.
   - Requires exact Task Card, allowed files, mandatory commands, parser, verifier, and independent verification.

3. **DeepSeek V4 Flash (`opencode_deepseek_v4_flash`)**:
   - Provider: `opencode`; exact model: `opencode/deepseek-v4-flash-free`.
   - Admitted autonomy ceiling: **L2**.
   - `default_route`: **`false`**.
   - L4 autonomy is **NOT GRANTED**; L4 remains experimental and non-admitted.
   - `opencode/deepseek-v4-flash-free` and `opencode-go/deepseek-v4-flash` share semantic capability lineage (`deepseek-v4-flash`) only; their workforce and admission execution identities remain exact and separate. Requesting `opencode-go/deepseek-v4-flash` fails closed unless an exact registered worker exists.
   - Bounded context, isolated directory, JSON event receipt, parser, focused tests, and verifier controls remain mandatory. Output is candidate-only with no route, reviewer, approval, integration, merge, push, or production claim authority.

## 11. Dated Owner-approved MiMo calibration amendment — 2026-08-17

The Owner-approved MiMo cumulative calibration / governance writeback amendment is active:

1. **Exact execution identity** stays bound: provider `opencode`, exact model
   `opencode/mimo-v2.5-free`, state `REGISTERED_CONDITIONAL`, admitted autonomy
   ceiling **L1**, current bounded candidate roles unchanged.
2. **Measured semantic evidence (2026-08-17 cumulative calibration)**: semantic
   stable floor **L1.5**, current semantic frontier **L3**, 53 new non-baseline
   trials, semantic score **51/53**, frontier stress **15/15**, verifier-guided
   repair **4/5**, strict schema/protocol discipline **CONDITIONAL**, tool/scope
   discipline **HARD FAIL**.
3. **Critical invariant**: semantic capability frontier **L3** != trusted
   execution ceiling **L1** != admitted workforce authority **L1**. MiMo is
   **NOT_PROMOTED**; it is not promoted to L2 or L3.
4. **Authority conclusion**: trusted mutation/execution ceiling **L1**, admitted
   autonomy **L1**, state stays `REGISTERED_CONDITIONAL`, current bounded
   candidate roles stay unchanged, external independent verification remains
   required.
5. **Tool-discipline blocker**: MiMo previously violated an answer-only / bounded
   calibration by performing unauthorized filesystem/tool mutation in an
   isolated temporary scope. This counts as a real tool-discipline failure even
   though canonical Nexus was not touched.
6. **Promotion gate**: dedicated MiMo Tool Discipline Requalification under
   durable DevSpace execution contracts, checking at minimum `expectedHead`,
   exact `writePaths`, `maxFiles`, final physical reconciliation, deliberate
   out-of-scope write rejection/violation detection, and external independent
   verification. GitHub Issue #400 tracks the durable DevSpace
   profile/follow-on transport gate; it is **NOT** claimed completed.
7. **Free-first paid-Go policy** (Owner policy = **FREE_FIRST**): Free `opencode/mimo-v2.5-free` is always first
   when eligible/runnable. Paid `opencode-go/mimo-v2.5` is a paid fallback only
   — only before any Free mutation, and only for provider / transport /
   capacity / quota / exact-model availability blockers, with a fresh Go
   preflight. Once Free has mutated, created a patch, or physical state is
   UNKNOWN, no automatic Go switch; reconcile first. Semantic/verifier failure
   is not an in-place paid fallback trigger. No hidden fallback; no paid-first
   because Go may be faster/stronger.
8. `opencode-go/mimo-v2.5` is **NOT** admitted as a workforce worker; Free and
   Go are **NOT** asserted to be one semantic capability lineage (that relation
   remains unresolved unless exact current authoritative evidence proves
   otherwise); no second route selector is created; `CapabilityPlanner`
   authority is unchanged.

9. **Evidence provenance and transport enforcement:** the 2026-08-17 aggregate
   is an `OWNER_APPROVED_CUMULATIVE_SUMMARY` only. Its raw trial receipts are
   `NOT_REPOSITORY_BOUND`; the claim ceiling is
   `OWNER_APPROVED_CUMULATIVE_SUMMARY_ONLY`, and the baseline is GitHub `main`
   `9296d68fe19d933cb78b9a0470a054ea5efd4c2f`. The supplied source artifact
   full SHA-256 identities are recorded in the machine policy. These bind the
   Owner-supplied source artifacts and OpenCode binary, but do not turn the
   absent per-trial receipts into an independently reproducible raw benchmark.
10. **Transport policy enforcement belongs to DevSpace Issue #400**, whose local
    Candidate is `65103307a014d5e51534828ab5e3c8469b60b732` and whose durable
    receipt is recorded in the machine policy. `CapabilityPlanner` remains the
    sole route/capability authority; it does not implement or relax this
    Free-first pre-mutation fallback contract.

## 12. Pending v2 collaboration proposal

`NEXUS_MULTI_MODEL_COLLABORATION_STANDARD_v2.0_20260728` remains `PROPOSED_FOR_OWNER_APPROVAL`. Its proposed changes—including Ling at read-only L0—are recorded as review inputs, not active authority. This policy and `nexus/config/model_workforce.yaml` remain current until James explicitly approves a replacement or amendment.

## 13. Dated amendment — 2026-10-12 (M5 inference host alignment)

All local model inference runs on the M5 host (64 GB); the 16 GB M4 no longer hosts models. The Ollama-compatible gateway (tunnel `127.0.0.1:11434`) and raw Ollama (`:11435`) serve exactly `qwen2.5-coder:14b-instruct-q3_K_M`, `qwen2.5-coder:7b`, `qwen2.5-coder:7b-instruct`, `qwen3.5:9b` and `nomic-embed-text:latest`; the gateway additionally maps `incoai/Qwen3.6-35B-A3B-Splash` to Splash on M5. `nexus/config/model_workforce.yaml` was aligned accordingly (`last_verified` 2026-10-12; `benchmark_snapshot` unchanged):

- **Added `local_splash_qwen36`** (`incoai/Qwen3.6-35B-A3B-Splash`): `LOCAL_CONDITIONAL`, L1, `bounded_code_candidate` and `bounded_reasoning_candidate`, same requirements and forbidden actions as `local_coder_7b`. Full-agent autonomy stays NOT_ADMITTED per lineage `qwen-3.6-35b-a3b` (CONDITIONAL/WATCH). Evidence: lineage waves in #1412 and 72 bounded local-heal repair attempts at about 50% calibrated solve (nexus-learning memory A/B rounds 8-9).
- **Added `local_splash_qwen38_27b`** (`incoai/Qwen3.8-27B-Splash`): `EXPERIMENT_ONLY`, L0. Installed on M5 but not served and not mapped by the gateway; lineage config `qwen3.8-27b-splash-q4-opencode-64k-wave3` shows tool-loop smoke PASS but full-agent T01 `STACK_UNQUALIFIED`.
- **Added `agy_flash_38`** (Gemini 3.8 Flash via agy, `gemini-3.8-flash-medium`): `REGISTERED_CONDITIONAL`, roles and autonomy copied from `agy_flash_37_medium`, not the default route at the time. The model id was taken from the dsh-agy-adapter model catalog and was not yet attested by a live agy run. *Superseded 2026-10-13 by section 15: `agy_flash_38` is now the sole default and its model id is live-attested (Nexus-new#1932 R0).*
- **`local_advisor_3b`, `local_deepseek67b`, `local_qwythos9b`** are not present on M5 Ollama: state `INSTALLED_NOT_CONNECTED`, reason `not_present_on_m5_ollama_2026-10-12`, roles kept for history. `routing.local_first` entries naming it were remapped later the same day (see the interim remap item below).
- **`local_qwen14b`** stays `DISABLED_RESOURCE_RISK`; the reason is now `no_semantic_uplift_over_7b; resource note superseded by m5_64gb_host_2026-10-12` (the 16 GB-host latency rationale is stale, the no-uplift finding stands).
- **Interim local advisor remap (issue #1845):** the 3B advisor is retired for now (its LoRA weights exist nowhere; `docs/reports/qwen3b_s2t_adapter_manifest.json` records `training_data_hash: sim_dataset_smoke_fixture`; `3b_override_verified_rate_analysis.md` measured abstain accuracy 40%). `routing.local_first` now maps `classification`, `extraction`, `compression` and `compact_diagnosis` to `local_qwen35_9b` (`qwen3.5:9b`, `LOCAL_CONDITIONAL`, L1, present on M5), whose roles gain those four with note `interim_replacement_for_local_advisor_3b_2026-10-12; unvalidated_for_role`. `routing.local_first.bounded_reasoning_shadow` is also remapped from `local_qwen3_8b` to `local_qwen35_9b` (note `bounded_reasoning_shadow_interim_2026-10-12; unvalidated_for_role`, nexus-runtime#173). `candidate_ranking` is not referenced by any routing entry and stays on the retired 3B worker. Claim ceiling `WORKFORCE_ROLE_REMAP_CONFIG_ONLY`: the 9B is not validated for these roles. The GB019 advisory tests no longer need a pre-M5 policy fixture and run against the live policy with the 9B worker identity.

The planner source copy of the YAML is `src/nexus_runtime/planning/config/model_workforce.yaml` in nexus-runtime and must stay byte-identical; this repository's copy aligns with the runtime package after the next runtime pin bump.

## 14. Dated amendment — 2026-10-13 (runtime pin bump to nexus-runtime #173, #177, #175)

This repository's `nexus/config/model_workforce.yaml` is again byte-identical to the pinned nexus-runtime planner copy.

- **nexus-runtime #173:** four more workers not present on M5 are `INSTALLED_NOT_CONNECTED`; `routing.local_first.bounded_reasoning_shadow` moves to `local_qwen35_9b` (see section 13).
- **nexus-runtime #177:** `local_splash_qwen38_27b` stays `EXPERIMENT_ONLY` but gains `bounded_code_candidate` at L1 so an explicitly authorized armor-on calibration can pass Workforce Admission; no routing entry names it and every admission still needs `explicit_experiment_authorization`.
- **nexus-runtime #175 (owner decision 2026-10-13):** External Intelligence runs on the personal free ChatGPT plan, whose only selectable level is the Thinking toggle. New worker `opencli_chatgpt_advanced_web` (`opencli_chatgpt/advanced`, `REGISTERED_CONDITIONAL`, L1, `CANDIDATE_ONLY`, same contract as the balanced web worker) receives `routing.online.consumer_routing.external_intelligence.bounded_candidate_generation` and the EIA consumer approval (`owner-decision-2026-10-13-eia-gpt-web-free-thinking`). `opencli_chatgpt_balanced_web` and the `open-swe-resident-five-repo-canary-20260908` campaign route are unchanged.

## 15. Dated Owner-decided amendment — 2026-10-13 (Gemini 3.8 Flash Medium default; runtime pin to nexus-runtime #192)

Owner decision (James, 2026-10-13, Nexus-new#1932): Agy 1.3.4 no longer serves Gemini 3.7 or any Gemini 3.6 tier, so the default switches directly to Gemini 3.8 without the planned §9 requalification. nexus-runtime #192 (squash `6782e38a57360893285227f4d2a68d7c649d4319`) carries the change; this repository pins that commit and `nexus/config/model_workforce.yaml` is again byte-identical to the pinned planner copy. Because Nexus-new loads the runtime's packaged policy (`WorkforcePolicyLoader()` → `DEFAULT_POLICY_PATH`), the pin bump itself changes routing.

- **`agy_flash_38` (`agy` / `gemini-3.8-flash-medium`) is the sole `default_route: true` worker** for `fast_bounded_implementation`: `routing.online.fast_bounded_implementation` and `route_defaults.fast_bounded_implementation.current_default` name it. Its autonomy ceiling L3 is inherited from the 2026-10-12 registration (section 13). **No calibration ceiling for 3.8 is recorded**; the 3.7 calibration evidence is not inherited. The model id is live-attested (Nexus-new#1932 R0).
- **`agy_flash_37_medium` (3.7 Medium), `agy_flash` (3.6 High) and `agy_flash_medium` (3.6 Medium) are `availability: UNAVAILABLE`** with reason `provider_no_longer_serves_model_agy_1.3.4_2026-10-13`: Agy 1.3.4 rejects `gemini-3.7-flash-medium` and lists no Gemini 3.6 tier. They stay registered for history and benchmark lineage; `agy_flash_37_medium` is now `default_route: false`.
- **The fallback is explicit `null` (fail closed)** in both `routing.online.fast_bounded_implementation_fallback` and `route_defaults.fast_bounded_implementation.fallback`. No other servable registered worker advertises the role; a failed default-routed request is not redirected or substituted.
- **`CAMPAIGN-NEXUS-LEARNING-CANONICAL-WIRING-01`** routes `fast_bounded_implementation` to `agy_flash_38`.
- Consumers aligned in the same change: the structural three-arm entry (`nexus/services/mainchain_entry.py`) and the unified-runtime scenario harness bind `agy_flash_38` with its required parser and verifier controls; `AgyWorkerAdapter`'s fallback model is `gemini-3.8-flash-medium`. The DSH Agy adapter's `listModels` catalog (`scripts/ops/dsh-agy-adapter/index.js`) no longer lists the retired 3.6/3.7 ids (#1932 follow-up), nor `gemini-3.1-pro-*`, which `agy models` no longer serves (2026-10-14).
- The pin also carries the other runtime changes merged since `2766c15`: nexus-runtime #182 (Agy permission fail-closed), #184 (`local_advisor_3b` retired: `REGISTERED_BLOCKED`, `UNAVAILABLE`, no roles), #188 (default models resolved from Workforce policy, `MODEL_DEFAULT_NOT_ADMITTED`), #187 (receipt `claim_boundary.simulated` derived from execution evidence, Issue #186) and #189 (Online authorization never trusts route self-attestation, Issue #178).
- **Future model-version updates** follow the automatic-update policy of Nexus-new#1996 (Owner decision 2026-10-13, option A): when a provider ships a newer model in the same family and tier, or retires the current default, the Workforce default moves to the newest servable model of that family and tier without manual Owner confirmation, provided a live attestation matches exactly and an independent AI review accepts the exact PR head before merge. The new model inherits the predecessor's autonomy ceiling and never raises it; new providers, tier, family or role changes, and autonomy increases stay out of scope and need the Owner. The live Gateway reload is done by the #2153 auto-deployer after the pin merges, with no Owner activation (#2155).

## 16. Dated operating rule — 2026-10-17 (DSH dispatch scope; Nexus-new#2537)

DSH work runs only through `nexus-dsh-workflow start-phase` with explicit RED and GREEN contracts, and only for small, well-specified bugs (a named failing behavior, a bounded `allowed_files` list, a runnable verification command). Open-ended Issue-level work (choosing a design, finding real artifacts, anything without a RED oracle) goes to Claude. Raw `dsh headless` runs with a free-form "manager + goal rounds" prompt are not a supported path: on 2026-10-17 two of them (nexus-core#294, Nexus-new#2455) ran about 45 minutes and 130 steps each and wrote no files.

`start-phase` now stops a phase with decision `NO_PROGRESS` (exit code 76, reason codes `NO_PROGRESS_STEPS` / `NO_PROGRESS_COMPACTIONS`) when the worktree is unchanged after `--no-progress-steps` agent steps (default 40) or `--no-progress-compactions` compactions (default 3); 0 disables a check. The Agy pool adapter caps each tool result fed back to the model at 8192 characters and appends a truncation note, which removes the single-huge-output cause of compaction churn.
