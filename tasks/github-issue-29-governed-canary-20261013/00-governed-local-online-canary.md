# Task Card 00: Issue #29 governed same-task Local -> Online consumption canary (2026-10-13)

## Identity

- task_id: `github-issue-29-governed-canary-20261013-r1`
- campaign_id: `github-issue-29-governed-canary-20261013`
- issue: `https://github.com/James3014/Nexus-new/issues/29`
- artifact_authority: current
- status: ACTIVE
- owner: James Chen (James3014)
- AUTO_CHAIN: false
- allow_deletions: false
- worker_may_commit: false
- worker_may_approve: false
- worker_may_integrate: false
- worker_may_push: false
- durable_marker: `ONLINE_LOCAL_SAME_TASK_CAUSAL_CONSUMPTION_VERIFIED`
- base_main_sha: `ace9fbdcafb7f49a4b759a1875dc9a14a71646a2`
- supersedes_card: `tasks/github-issue-29-local-online-canary-20261005/00-local-online-canary.md` (kept unchanged as history)

## Lineage / replay fence

This is a fresh execution identity. It does not retry, relabel, or reinterpret
`issue-29-local-online-canary-20261001`, the 2026-10-05 v9 Agy run (invalid:
`--dangerously-skip-permissions` mutated the canonical worktree), or the PR
#1408 script `scripts/ops/canary_issue29_physical_local_online.py`, which the
Owner ruled is not closure evidence (decision 4, 2026-10-13): it called Ollama
and the Gemini REST API directly, bypassed Planner/Workforce/runtime, wrote its
own verifier string, and had no RootReceipt or learning stage.

The physical run binds whatever exact `main` SHA is checked out at run time;
the harness records `HEAD`, tree, runtime pin, and the raw-blob SHA-256 of this
card read back from Git `HEAD`. `base_main_sha` above is the authoring base only.

## Execution identities

- Route authority: `CapabilityPlanner` only (no caller route, world, worker,
  provider, or model input; `execute_canonical_product_task` rejects them).
- Local demand: `bounded_code_candidate` -> `local_coder_7b` /
  `ollama` / `qwen2.5-coder:7b-instruct` (World C `local_armor`,
  `ISOLATED_TARGET`), reached via `com.james.local-models-ollama`
  (127.0.0.1:11435) through the gateway (127.0.0.1:11434).
- Online demand: `fast_bounded_implementation` -> `agy_flash_38` /
  `agy` / `gemini-3.8-flash-medium`.
- Fallback: none. `routing.online.fast_bounded_implementation_fallback` is
  `null`. If Workforce Admission does not lawfully ALLOW `agy_flash_38` for
  this task, the canary records `BLOCKED` and returns to the Owner. There is
  no silent substitution to 3.7/3.6 or any other worker.

## Workforce controls supplied lawfully

`agy_flash_38` requires `task_card, allowed_files, mandatory_commands, parser,
verifier, independent_verification`. On the canonical product path:

- `task_card`: only from a `VerifiedTaskCardIdentity` for this exact
  `task_id`, built by reading this tracked card back from Git `HEAD` and
  re-verified (bytes hash) inside `execute_canonical_product_task`.
- `allowed_files`, `mandatory_commands`, `verifier`,
  `independent_verification`, `parser`, `compile`: from the bounded target file
  and the deterministic verifier command below
  (`_actual_runtime_controls`).

No control is injected to reach ALLOW without the physical capability behind it.

## Objective

Prove one lawful same-task execution in which:

1. `CapabilityPlanner` remains the sole route/capability-selection authority;
2. Workforce Admission separately constrains and admits the Local and Online
   workers above;
3. the task carries this tracked Task Card authority, which the Online path
   requires;
4. Local/World C produces a physically executed, identity-bound result
   (isolated candidate, selected hash == applied hash, World C verifier PASS);
5. the Online stage consumes that exact Local/World C evidence: the
   VerifiedAssistPacket (VAP) is frozen before Online and carried inline in
   the Online input (VAP inline; no `read_file` needed);
6. the final receipt records whether and how the Local result contributed to
   the final outcome;
7. verifier/claim gates remain authoritative and fail closed on missing,
   stale, substituted, or tampered Local evidence.

## Required evidence contract

The harness receipt must carry current equivalents of:

- exact task / attempt / contract / source identity (`task_id`,
  `execution_attempt.attempt_id`, this card's SHA-256 + Git blob, Nexus-new
  `HEAD`/tree, nexus-runtime pin, fixture revision);
- canonical execution decision and `CapabilityPlanner` authority;
- Local demand/admission and exact provider/model identity;
- Online demand/admission and exact provider/model identity;
- real Local provider call(s) (`model_call_count >= 1`);
- real Online provider call(s) (`provider_call_count >= 1`, process started,
  `provider_permission_mode = plan_no_autoapprove`, runtime-ephemeral cwd);
- exact Local output/candidate/evidence hash presented to the Online stage
  (VAP `packet_hash`, derived from the selected Local candidate hash);
- consumption proof binding the Online input to that exact Local evidence
  (proof recomputed; `final_prompt_hash == provider_input_sha256`; VAP
  fragment is in the physical input);
- final outcome receipt with `online_consumed` and
  `final_outcome_contributed` / `claim_boundary.outcome_contributed`
  recorded by the runtime, never by the harness;
- authoritative World C verifier result bound to task/attempt/source;
- negative controls (tests) for missing / stale / substituted / tampered
  Local evidence, caller route override, Online model not admitted, and
  host preflight abort.

A run where Local and Online both execute but the Online input never consumes
the Local evidence does not satisfy this card.

## Owner decisions applied (Issue #29 comment, 2026-10-13)

1. Online model `agy / gemini-3.8-flash-medium` (`agy_flash_38`); no fallback;
   not lawfully admitted -> `BLOCKED`, return to Owner.
2. Agy runs `--mode plan --sandbox --model gemini-3.8-flash-medium` with no
   permission grants; the exact VAP is inline in the Online input. No new
   admission mechanism; the shared Agy `settings.json` is not touched.
3. nexus-runtime#64 post-hoc review is a separate gate (not in this card).
4. The PR #1408 script is not closure evidence; this governed harness replaces it.
5. Host: no service changes. Before the physical run: the
   `com.james.local-models-ollama` service answers on its own port :11435
   (observed read-only; the harness never calls the service manager);
   `/api/ps` on :11435 is empty or holds only `qwen2.5-coder:7b-instruct`; the :11434 gateway and
   Splash on :8000 answer; abort and return to the Owner if unused memory is
   below about 6 GB.
6. #49 keeps `SERIALIZE_AFTER:#29`.

## Fixture

The canary target is a harness-materialized fixture workspace under the state
directory (never the canonical Nexus-new checkout):

- `calc.py`: `def add_one(x): return x` (bug: must return `x + 1`).
- Task statement: "Repair add_one in calc.py so that add_one(x) returns x + 1.
  Answer only from the inline evidence in this prompt; do not use tools and do
  not read or write files."

## Allowed Files

- `tasks/github-issue-29-governed-canary-20261013/INDEX.md`
- `tasks/github-issue-29-governed-canary-20261013/00-governed-local-online-canary.md`
- `scripts/ops/issue29_governed_canary.py`
- `tests/ops/test_issue29_governed_canary.py`
- `nexus/engine/canonical_task_seam.py`
- `nexus/contracts/root_receipt.py`
- `scripts/ops/canary_issue29_physical_local_online.py` (docstring note only)

Fixture target (runtime, not repository): `calc.py`.

## Verification commands

```bash
PYTHONPATH=$PWD .venv/bin/python -m pytest tests/ops/test_issue29_governed_canary.py -q
PYTHONPATH=$PWD .venv/bin/python -m pytest tests/engine/test_canonical_task_seam.py tests/unit/local_heal/test_world_c_root_receipt.py -q
.venv/bin/ruff check scripts/ops/issue29_governed_canary.py tests/ops/test_issue29_governed_canary.py
.venv/bin/ruff format --check --preview scripts/ops/issue29_governed_canary.py tests/ops/test_issue29_governed_canary.py
PYTHONPATH=$PWD .venv/bin/python scripts/ops/run_golden_behavior_eval.py
```

Fixture verifier (World C, inside the isolated workspace):

```bash
python3 -c "import py_compile; py_compile.compile('calc.py', doraise=True); import calc; assert calc.add_one(1) == 2; assert calc.add_one(-1) == 0"
```

## Physical run (Owner-gated, M5 only)

```bash
PYTHONPATH=$PWD .venv/bin/python scripts/ops/issue29_governed_canary.py \
  --physical --confirm-task-id github-issue-29-governed-canary-20261013-r1
```

Run from a clean checkout of the bound `main`. The harness aborts with
`ABORTED_PREFLIGHT` if any host check fails, and with `BLOCKED` if the Task
Card readback, route policy, or Workforce Admission refuses.

## Claim ceiling

One governed same-task canary receipt plus source/test artifacts. No Candidate
approval, merge, release, runtime activation, model promotion, production or
public claim. The durable marker requires independent review of the physical
receipt by a reviewer distinct from the implementer.
