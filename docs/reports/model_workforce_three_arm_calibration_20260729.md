# Nexus Model Workforce Three-Arm Calibration — 2026-07-29

## Status

- **Task:** `u3a-composite-v1`
- **Scope:** 25 enrolled models × Bare / Nexus-Bounded / Nexus-Full = 75 arms
- **Run type:** historical universal calibration baseline
- **Benchmark role:** historical baseline and comparative diagnostic instrument
- **Claim ceiling:** `HISTORICAL_BASELINE_ONLY`
- **Role definitions final:** `false`
- **Public claim allowed:** `false`
- **Historical scores:** immutable (frozen at 2026-07-29)
- **Requalification rule:** cumulative evidence + stable-floor regression + target/current frontier + failure-family/hidden probes + transport/protocol/isolation; FIRST_PASS and VERIFIER_GUIDED_REPAIR remain distinct.

This report records the internal 2026-07-29 routing calibration baseline. It does not replace James's model-role authority, CapabilityPlanner, Verifier, Receipt, Git controls, or provider account-pool rules. A semantic pass in this synthetic composite task is not proof of repository implementation ability, production readiness, or permission to mutate the formal workspace. Workforce governance enforces three distinct layers: semantic capability lineage != exact execution identity != admitted authority.

## Composite task and verifier

Each arm received the same three-part bounded task:

1. identify the correct started-provider-call count when the first process starts and a retry fails before process creation;
2. implement a pure `normalize_status(value)` function;
3. preserve the evidence ceiling: five focused tests without full regression, runtime canary, and sealed receipt must remain `NOT_PROVEN`.

The deterministic verifier applied 11 checks covering envelope parsing, accounting semantics, executable behavior, and claim boundaries. The Full arm additionally traversed the current Unified Runtime planner, capability selection, verifier, receipt, and learning seams. `receipt_complete=false` remained correct for this benchmark because the task intentionally lacks full closure evidence.

## Settlement

| Category | Count |
|---|---:|
| Models | 25 |
| Arms | 75 |
| Required cohort | 14 |
| Discovery cohort | 11 |
| `PROVISIONAL_PASS` | 13 |
| `CONDITIONAL` | 1 |
| `UNQUALIFIED` | 5 |
| `BLOCKED_PROVIDER` | 4 |
| `THREE_ARM_INCOMPLETE` | 1 |
| `ISOLATION_CONTRACT_VIOLATION` | 1 |

Six models scored 11/11 on all three semantic arms, but two have separate disqualifiers or ceilings:

- `grok_45`
- `opencode_mimo_free`
- `opencode_ling_free`
- `opencode_deepseek_v4_flash`
- `opencode_laguna` — **not promotable** because it wrote `output.json` inside the isolated benchmark directory
- `local_deepseek14b` — **not default-routable** on the 16 GB M4 because the three arms consumed about 307 seconds in total and belong to the resource-risk tier

## Complete result matrix

Scores are `passed checks / 11`. Role recommendations are benchmark-local and remain subordinate to Owner-approved role ceilings.

| Model ID | Bare | Bounded | Full | First-run disposition | Important boundary |
|---|---:|---:|---:|---|---|
| `codex_luna` | 0 | 0 | 0 | `BLOCKED_PROVIDER` | Current CLI requires upgrade; this is not a model-capability failure |
| `agy_flash` | 10 | 11 | 10 | `PATCH_CANDIDATE_GENERATOR` provisional | Owner role may remain L2; this one task does not re-grade its full engineering authority |
| `grok_45` | 11 | 11 | 11 | `BOUNDED_ENGINEERING_CANDIDATE` provisional | Independent verification still mandatory |
| `gemini_36_flash` | 0 | 0 | 0 | `BLOCKED_PROVIDER` | Direct Gemini client is unsupported; Agy is the current working Gemini path |
| `opencode_mimo_free` | 11 | 11 | 11 | `BOUNDED_ENGINEERING_CANDIDATE` provisional | Remains candidate-only until repetition and physical patch suite |
| `opencode_ling_free` | 11 | 11 | 11 | Semantic pass; v2 proposal suggests read-only L0 | The proposal is not Owner-approved; prior diff/apply evidence still prevents automatic engineering promotion |
| `local_advisor_3b` | 9 | 11 | 10 | `BOUNDED_REVIEW_AND_AUDIT` provisional | Keep classification/extraction/compression-only ceiling |
| `local_qwen7b` | 10 | 10 | 10 | `BOUNDED_REVIEW_AND_AUDIT` provisional | Code remains candidate-only and requires parser/compile/tests |
| `local_deepseek67b` | 8 | 9 | 0 | `UNQUALIFIED` | Full governance context caused envelope failure |
| `local_ornith9b` | 0 | 0 | 0 | `BLOCKED_PROVIDER` | Ollama HTTP 500 on all arms |
| `local_qwythos9b` | 10 | 10 | 10 | `BOUNDED_REVIEW_AND_AUDIT` provisional | Historical primary-role refusal/empty-patch evidence still applies |
| `local_qwen35_9b` | 10 | 0 | 0 | `UNQUALIFIED` / runtime-blocked | Custom GGUF template cannot stably suppress thinking on bounded/full prompts |
| `local_qwen14b` | 10 | 10 | 10 | `BOUNDED_REVIEW_AND_AUDIT` provisional | Resource-risk; no default 16 GB route |
| `mimo_cli` | 0 | 0 | 0 | `BLOCKED_PROVIDER` | Upstream account balance blocker |
| `opencode_big_pickle` | 11 | 11 | 0 | `UNQUALIFIED` | Full arm envelope failure |
| `opencode_deepseek_v4_flash` | 11 | 11 | 11 | `BOUNDED_ENGINEERING_CANDIDATE` provisional | v2 proposes an L1.5 candidate/reviewer ceiling; it remains unapproved and formal workspace mutation is forbidden |
| `opencode_laguna` | 11 | 11 | 11 | `ISOLATION_CONTRACT_VIOLATION` | Wrote an output file despite isolated no-mutation expectations |
| `opencode_nemotron` | 11 | 11 | 0 | `THREE_ARM_INCOMPLETE` | Full arm streaming/subprocess failure |
| `opencode_north_mini_code` | 10 | 11 | 0 | `UNQUALIFIED` | Bounded improved accuracy, Full failed to produce envelope |
| `local_qwen15b` | 9 | 9 | 9 | `READ_ONLY_SCHEMA_EXECUTOR` conditional | L0.5 maximum; no code or claim authority |
| `local_qwen3_8b` | 11 | 11 | 10 | `PATCH_CANDIDATE_GENERATOR` provisional | Full arm changed an exact accounting field; bounded use only |
| `local_qwythos_v2_9b` | 10 | 0 | 10 | `UNQUALIFIED` / runtime-blocked | Prompt-level `/no_think` is unstable across arms |
| `local_deepseek_coder_v2_lite` | 9 | 10 | 10 | `BOUNDED_REVIEW_AND_AUDIT` provisional | Missed implementation edge case; verifier required |
| `local_deepseek14b` | 11 | 11 | 11 | `BOUNDED_ENGINEERING_CANDIDATE` provisional | About 92 s / 86 s / 128 s; experiment-only resource tier |
| `local_gemma12b` | 10 | 10 | 10 | `BOUNDED_REVIEW_AND_AUDIT` provisional | About 71 s / 55 s / 87 s and roughly 8–9 GB runtime RSS |

## Main findings

### 1. Nexus-Bounded often helps; Full prompt context often hurts

Bounded context improved Agy, the 3B advisor, DeepSeek 6.7B, North Mini, and DeepSeek Coder V2 Lite. Full lifecycle governance did not justify injecting full governance prose into every model prompt. Several models lost envelope compliance or semantic precision under the Full prompt.

**Routing decision:** keep the full Nexus lifecycle outside the model, while giving each worker a model-specific bounded evidence pack. "Nexus-Full" must mean planner/verifier/receipt/learning around the call, not unrestricted governance text inside the prompt.

### 2. Provider availability is not model capability

The following are infrastructure or account states, not semantic scores:

- Codex: current client upgrade required
- direct Gemini CLI: unsupported client
- MiMo CLI: balance blocked
- Ornith: Ollama HTTP 500

These rows must never be used to claim that the underlying model is weak.

### 3. Thinking suppression requires a real model control plane

The benchmark added optional top-level Ollama `think` support and verified 52 upstream provider tests. Standard Ollama templates can consume this field. Two custom GGUF models use `TEMPLATE {{ .Prompt }}` and ignore that API control. Prompt-level `/no_think` worked on a trivial probe but was unstable on bounded/full tasks, including empty one-token responses.

**Decision:** do not strip `<think>` in the parser and do not promote these models. Rebuild their Ollama template with explicit `IsThinkSet/Think` support or keep them runtime-blocked.

### 4. Semantic score cannot override isolation and authority

Laguna's 11/11 semantic result is invalid for promotion because it mutated the isolated directory. Ling's 11/11 result does not supersede the existing read-only Owner ceiling or prior patch instability. One benchmark can lower operational confidence immediately, but cannot raise authority automatically.

### 5. 12B–14B local models are capability-rich but economically poor defaults

DeepSeek R1 14B passed all checks, while Gemma 12B and Qwen 14B remained at 10/11. Their latency and memory footprint make them explicit experiments or escalations, not default local routing on the current 16 GB M4.

## Current routing recommendation

1. **Deterministic first.** Use rules, AST, schema checks, exact search, receipts, and verifiers before any model.
2. **Cloud main engineering authority remains Owner-defined.** A single synthetic benchmark cannot demote or promote Codex, Agy, or Grok authority; availability is tracked separately.
3. **Free remote candidates:** MiMo and DeepSeek V4 Flash may enter a second repetition and physical patch suite. Ling remains read-only L0. Laguna is blocked by isolation violation.
4. **Local default:** 3B for fixed-schema assistance; 7B for small reversible candidates only. No local reasoner is currently approved as a default claim/decision worker.
5. **Local experimental:** Qwen3 8B, Qwythos 9B, DeepSeek Coder V2 Lite, and 12B–14B candidates require role-specific suites and resource budgets.
6. **Escalate on verifier failure, disagreement, architecture, security, irreversible operations, production claims, or cross-module closure.**

## Verification evidence

- Provider regression: `52 passed` across LocalModelProvider, P3 diagnosis, P3 cheap verifier, and AUTOMEM tests.
- GitNexus index refreshed at HEAD `4127f1c`; `OllamaLocalModelProvider.generate` blast radius: 39 upstream dependants, `MEDIUM` risk.
- Raw benchmark receipts: `/tmp/nexus-model-bench/`
- Matrix source: `nexus/config/model_three_arm_matrix.yaml`
- Harness: `scripts/bench/experimental/model_workforce_three_arm.py`
- Machine summary: `docs/reports/model_workforce_three_arm_calibration_20260729.json`

## Historical baseline status and future requalification

This document serves as the permanent historical baseline from the initial 2026-07-29 universal three-arm run. All historical scores and records are frozen and immutable.

For subsequent workforce updates and candidate requalification:

1. The three-arm benchmark operates as a baseline comparative diagnostic fixture, not a required rerun-from-zero constraint for every minor change.
2. Future qualification uses cumulative evidence: stable-floor regression, target/current frontier validation, failure-family/hidden defect probes, and transport/protocol/isolation checks.
3. Autonomous `FIRST_PASS` reliability, hidden defect checks, and `VERIFIER_GUIDED_REPAIR` remain distinct evidence phases and must not be conflated.
4. Observed higher-tier repair capabilities (such as L4 repair) remain experimental and are NOT admitted autonomy.
5. Autonomy ceilings (e.g. Gemini 3.7 Flash Medium at L3, DeepSeek V4 Flash at L2) and non-default routing are governed by `nexus/config/model_workforce.yaml` and Owner authority. Lineage sharing (such as between `opencode/deepseek-v4-flash-free` and `opencode-go/deepseek-v4-flash`) does not collapse exact execution identity matching.

---

# 2026-08-17 MiMo cumulative calibration amendment

This is a dated, Owner-approved cumulative calibration and governance amendment
for OpenCode MiMo V2.5. It is **separate** from the original 2026-07-29
three-arm run above: the 2026-08-17 suite was not part of that run, and it does
not pretend to be. Historical 2026-07-29 scores remain frozen and unchanged.

## Exact identity and measured semantic evidence

- **Exact Free identity:** `opencode/mimo-v2.5-free`
- **Evidence date:** 2026-08-17
- **Evidence kind:** cumulative calibration (Owner-approved 2026-08-17 OpenCode MiMo V2.5 cumulative calibration / governance evidence)
- **Trials:** 53 new non-baseline trials
- **Semantic stable floor:** L1.5
- **Current semantic frontier:** L3
- **Semantic score:** 51/53
- **Frontier stress:** 15/15
- **Verifier-guided repair:** 4/5
- **Strict schema/protocol discipline:** CONDITIONAL
- **Tool/scope discipline:** HARD FAIL

## Authority conclusion

- **Trusted mutation/execution ceiling:** L1
- **Admitted autonomy:** L1
- **Promotion status:** NOT_PROMOTED
- **State:** `REGISTERED_CONDITIONAL` (unchanged)
- **Current bounded candidate roles:** unchanged
- **External independent verification:** remains required

**Critical invariant:** semantic capability frontier **L3** != trusted execution
ceiling **L1** != admitted workforce authority **L1**. MiMo is **not** promoted
to L2 or L3.

## Free / Go policy

Owner policy is **FREE_FIRST**:

- **Free:** `opencode/mimo-v2.5-free` — always first when eligible/runnable.
- **Paid Go:** `opencode-go/mimo-v2.5` — paid fallback only.
- Go fallback is permitted only before any Free mutation, and only for
  provider / transport / capacity / quota / exact-model availability blockers,
  with a fresh Go preflight.
- Once Free has mutated, created a patch, or physical state is UNKNOWN: no
  automatic Go switch; reconcile first.
- Semantic/verifier failure is not an in-place paid fallback trigger.
- No hidden fallback; no paid-first because Go may be faster/stronger.

`opencode-go/mimo-v2.5` is **not** registered as an admitted workforce worker.
Free and Go are **not** asserted to be one semantic capability lineage; that
relation remains unresolved unless exact current authoritative evidence proves
otherwise. No second route selector is created and `CapabilityPlanner` authority
is unchanged.

## Provenance and claim ceiling

The 2026-08-17 aggregate is an **`OWNER_APPROVED_CUMULATIVE_SUMMARY`**, not a
repository-bound raw benchmark receipt set. `raw_trial_receipt_status` is
`NOT_REPOSITORY_BOUND`, so this report does not claim independently reproducible
raw-trial evidence. Its claim ceiling is
`OWNER_APPROVED_CUMULATIVE_SUMMARY_ONLY`, with GitHub `main` baseline
`9296d68fe19d933cb78b9a0470a054ea5efd4c2f`; the supplied source artifacts and
OpenCode binary are bound by full SHA-256 identities in the machine policy.
Those content digests bind the aggregate source documents; they do not replace
the absent per-trial receipts.

Transport fallback enforcement belongs to DevSpace Issue #400, not
`CapabilityPlanner`. The latter remains the sole route/capability authority;
DevSpace owns the Free-first pre-mutation resolver and its clean-state gates.

## Tool-discipline blocker and promotion gate

MiMo previously violated an answer-only / bounded calibration by performing
unauthorized filesystem/tool mutation in an isolated temporary scope. This
counts as a real tool-discipline failure even though canonical Nexus was not
touched.

Promotion requires a dedicated **MiMo Tool Discipline Requalification** under
durable DevSpace execution contracts, checking at minimum:

- `expectedHead`
- exact `writePaths`
- `maxFiles`
- final physical reconciliation
- deliberate out-of-scope write rejection / violation detection
- external independent verification

GitHub Issue #400 tracks the durable DevSpace profile / follow-on transport
gate. **Issue #400 is not claimed completed.**

## Historical baseline unchanged

The frozen 2026-07-29 `opencode_mimo_free` scores (Bare 11/11, Nexus-bounded
11/11, Nexus-full 11/11) are not rewritten by this amendment.
