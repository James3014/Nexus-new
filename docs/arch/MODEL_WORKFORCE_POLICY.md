# Nexus Model Workforce Policy

**Authority:** current

**Owner:** James Chen

**Status:** active, evidence-bounded

**Machine source:** `nexus/config/model_workforce.yaml`

**Benchmark matrix:** `nexus/config/model_three_arm_matrix.yaml`
**Last verified:** 2026-07-29

This file defines which model workers Nexus may assign, the context each worker may receive, its autonomy ceiling, and the conditions that require escalation. It does not replace CapabilityPlanner, HybridRouteDecision, execution authorization, Verifier, Receipt, Learning, Git safety, or account-pool policy.

Provider selection is open across the registered adapter surface. `auto` and
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

Every candidate has two independent dimensions:

1. **Capability state** — what prior governed evidence and the current benchmark support.
2. **Operational availability** — whether the current CLI, account, model alias, and local runtime can deliver a response now.

Provider/client failure is not scored as model reasoning failure. Conversely, a semantic answer passing the Full arm is not lifecycle closure: the 2026-07-29 matrix did not establish `receipt_complete=true` or `capability_closure_complete=true` for any model.

CapabilityPlanner and HybridRouteDecision remain the only route authority. This policy is a workforce constraint consumed after route authorization, not another router.

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

The matrix is an initial uniform calibration. Stable promotion still requires a second repetition, a role-specific suite, and a physical patch verifier for mutating roles.

## 3. Current active workforce

| Worker | Current role | Ceiling | Preferred context | Current status |
|---|---|---:|---|---|
| Codex Luna — `gpt-5.6-luna` | Main engineering, milestone closure, integration | Historical L3 | Governed mainchain | Available; Codex CLI 0.146.0 with `gpt-5.6-luna` returned exactly `OK` in a read-only smoke on 2026-07-29 |
| Agy Flash — `gemini-3.6-flash-high` | Fast bounded implementation and focused verification | L2 | **Nexus-bounded** | Available; benchmark 10/11 → 11/11 → 10/11 |
| Grok 4.5 | Independent review, hidden-defect search, evidence audit; bounded candidate generation | L2+ | Bounded or Full semantic context | Available; benchmark 11/11 on all arms |
| OpenCode MiMo — `opencode/mimo-v2.5-free` | Bounded code candidate | L1 | Bounded isolated prompt | Available; 11/11 all arms; high fixed input-token overhead |
| OpenCode Ling — `opencode/ling-3.0-flash-free` | Bounded code candidate | Current L1 | Bounded isolated prompt | Available; 11/11 all arms; high fixed input-token overhead. The unapproved v2 proposal would lower it to read-only L0 |
| Cline — `glm-5.2` | Bounded code candidate | L1 | Bounded isolated prompt | Registered conditional; Cline CLI adapter and external-runtime authorization required |
| Local Advisor — `qwen2.5-s2t-advisor:3b` | Classification, extraction, compression, compact diagnosis | L0.5 | **Nexus-bounded only** | Available; 9/11 → 11/11 → 10/11 |
| Local Coder — `qwen2.5-coder:7b-instruct` | Small bounded code candidate | L1 | Bounded exact contract | Available; 10/11 on every arm; no measured Nexus uplift |
| Local Qwen3 — `qwen3:8b` | Bounded reasoning/code shadow candidate, counterexample search | L1 shadow | **Nexus-bounded** | Available; 11/11 → 11/11 → 10/11; Full context caused schema drift |

### Assignment consequences

- The 3B model is the clearest measured Nexus-bounded uplift. It must not receive Full governance context or mutate code.
- The 7B model remains a code **candidate** generator because previous repository evidence exists, but this benchmark did not prove uplift or self-verification.
- Qwen3 8B is a stronger bounded shadow candidate than the current 9B reasoning models, but its latency and Full-context regression prevent default promotion.
- OpenCode free models are subscription-free, not context-cheap. Typical calls carried roughly 20k+ fixed input tokens. They require isolated execution and external verification.
- Grok may review or generate a bounded candidate, but cannot be the sole production-readiness adjudicator.
- Agy should receive a locked task card, exact file scope, and mandatory commands. It should not own architecture authority.

## 4. Conditional, committee-only, and shadow workers

| Model | Permitted use | Why it is not a default worker |
|---|---|---|
| `deepseek-coder:6.7b-instruct` | Committee secondary proposer only | 8/11 → 9/11 → 0/11; Full envelope failure |
| `qwythos:9b` | Bounded second opinion or committee candidate | 10/11 across arms, no uplift, Full latency about 95 s |
| `opencode/deepseek-v4-flash-free` | Shadow bounded engineering candidate | 11/11 all arms, but only one uniform run and no physical patch suite |
| `deepseek-coder-v2:lite` | Bounded secondary code candidate | 9/11 → 10/11 → 10/11; missed implementation edge case |
| `qwen2.5:1.5b` | Simple extraction or read-only fixed-schema candidate | 9/11 across arms; no uplift and weak implementation behavior |

These workers require explicit bounded scope, deterministic parsing, focused tests, and an external verifier. They do not gain route, claim, or direct-apply authority.

## 5. Disabled, blocked, quarantined, and experiment-only models

### Operationally blocked

| Model | Blocker |
|---|---|
| Direct Gemini CLI `gemini-3.6-flash` | Client rejected as unsupported; use Agy instead |
| MiMo CLI `xiaomi/mimo-v2.5` | HTTP 402 insufficient account balance |
| `ornith:9b` | Ollama HTTP 500 on all arms |

Blocked models receive no active assignment. Their zero benchmark scores are not semantic model scores.

### Protocol-disabled

| Model | Evidence | Re-enable gate |
|---|---|---|
| `nexus-qwen35-9b-q4km:latest` | Bare 10/11; API `think:false` is ignored by its `TEMPLATE {{ .Prompt }}` Modelfile, while prompt-level `/no_think` produced unstable empty Bounded/Full responses | Rebuild with template-level `IsThinkSet/Think` control plus a clean three-arm retest |
| `nexus-qwythos-v2-9b-q4km:latest` | Bare and Full reached 10/11 with `/no_think`, but Bounded returned an empty one-token response; control remains unstable | Rebuild with template-level `IsThinkSet/Think` control plus a clean three-arm retest |

### Resource-risk or experiment-only

| Model | Result | Decision |
|---|---|---|
| `qwen2.5-coder:14b-instruct-q3_K_M` | 10/11 all arms; Full about 80 s | Disabled by default; no quality uplift over smaller workers |
| `deepseek-r1-14b-q4km:latest` | 11/11 all arms; about 92/86/128 s | Explicit high-latency second-opinion experiment only |
| `gemma4-coder-12b-q4km:latest` | 10/11 all arms; about 71/55/87 s | Explicit experiment only |
| `opencode/big-pickle` | Bare/Bounded pass; Full envelope failure | Experiment only |
| `opencode/nemotron-3-ultra-free` | Bare/Bounded pass; Full streaming failure | Experiment only |
| `opencode/north-mini-code-free` | Bounded pass; Full envelope failure | Experiment only |

### Quarantined

`opencode/laguna-s-2.1-free` scored 11/11 on all arms but wrote `output.json` inside the isolated working directory despite a text-only task. The formal Nexus workspace was not changed, but the behavior demonstrates tool-discipline drift. It remains quarantined until tool denial is verified and a clean three-arm rerun passes.

## 6. Routing policy

Nexus must route in this order:

1. Complete the task deterministically when rules, AST, exact search, schema validation, or existing evidence are sufficient.
2. Use Local Advisor 3B for compact classification, extraction, compression, or diagnosis.
3. Use Local Coder 7B for a small bounded code candidate protected by parser, compile, and focused tests.
4. Use Qwen3 8B only as a bounded shadow candidate or counterexample searcher.
5. Use Agy for fast bounded online implementation.
6. Use Grok for independent review, hidden defects, or evidence pressure testing.
7. Use Codex for complex milestone closure when the governed adapter, independent verification, and receipt controls are present.
8. Use OpenCode candidates when subscription-free remote execution is useful and high fixed context overhead is acceptable.

No Local model is approved as a default Full-context worker. Full context is not assumed to be better: several models regressed, leaked thinking traces, changed schema, or lost the answer envelope.

Mandatory escalation applies to architecture or authority choices, ambiguous product behavior, security or irreversible risk, production/claim adjudication, unbounded multi-file work, Local disagreement or verifier failure, integration/runtime closure, and unsafe resource pressure.

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

## 9. Promotion gate

Higher autonomy requires all of the following:

- explicit model identity and provider/CLI version;
- governed adapter and authorization path;
- two complete comparable three-arm repetitions;
- role-specific tasks, not only the composite calibration;
- exact output/schema compliance;
- physical patch/apply evidence for mutating roles;
- deterministic verification and receipt completeness;
- failure classification separating model, transport, permission, quota, and resource pressure;
- measured token, latency, and retry cost;
- no unresolved unsafe overclaim, thinking leak, schema drift, or tool-discipline pattern.

Until those gates pass, the lower autonomy level and stricter context policy remain authoritative.

## 10. Pending v2 collaboration proposal

`NEXUS_MULTI_MODEL_COLLABORATION_STANDARD_v2.0_20260728` remains `PROPOSED_FOR_OWNER_APPROVAL`. Its proposed changes—including Ling at read-only L0 and DeepSeek V4 Flash at L1.5 candidate/reviewer—are recorded as review inputs, not active authority. This policy and `nexus/config/model_workforce.yaml` remain current until James explicitly approves a replacement or amendment.
