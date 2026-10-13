# Committee judge qualification v1 — frozen spec

Status: FROZEN before the first scored run. Owner (James) approved the judge, the experiment and
the pass bar in chat on 2026-10-14. Nothing in this file, `scripts/eval/judge_pair_set_v1/`,
`scripts/eval/judge_pair_eval.py` or the production judge prompt may change after the first scored
run. The commit that adds this file is the frozen reference; its sha is recorded in the results doc.

## 1. Question

Can the production local judge pick the hidden-verifier-passing candidate more reliably than the
current deterministic incumbent ("primary always wins", which is what `JudgeSelector` and
`CommitteeControllerV263` effectively do today)?

## 2. Judge under test (exact identity)

- Driver: `nexus.engine.llm_judge_providers.OllamaJudgeProvider.from_policy()` unchanged, i.e. the
  production system prompt, JSON contract (`format: json`), `temperature: 0`, `think: false`,
  `num_ctx: 8192`, one built-in retry, 1500-char summary cap.
- Policy route: `routing.local_first.classification` -> `local_qwen35_9b` -> `qwen3.5:9b`.
  The harness aborts if the policy resolves anything else. No fallback model, no M4 redirect.
- Ollama digest on M5 (2026-10-14): `6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`.
- Endpoint: `http://127.0.0.1:11434` (production default, the M5 gateway).
- System prompt sha256: recorded per run in `scorecard.json` (`preflight.system_prompt_sha256`).

## 3. Dataset (judge pair set v1)

- Source tasks: `scripts/eval/memory_ab_tasks_v1`, `_v2`, `_v3` (48 tasks).
- Candidates: full-file repairs of the task's target file sampled on M5 from two local coder
  proposers, 6 samples per task each, temperature 0.8:
  - `qwen2.5-coder:7b-instruct` (digest `dae161e2…`, the committee primary proposer), seed = first
    8 hex of sha256(`<task uid>#<idx>`);
  - `qwen2.5-coder:14b-instruct-q3_K_M` (digest `e00d09af…`), added before any scoring because the
    7B alone yielded only 26 discriminative pairs; seed = sha256(`<model>|<task uid>#<idx>`).
  The proposers never see `repro.py`. Builder: `scripts/eval/build_judge_pair_set.py`. (The 14B
  generation passed `keep_alive: 120s` per request because the host runs `OLLAMA_KEEP_ALIVE=0`;
  the judge runs do NOT, so each judgment pays the production cold load.)
- Label = hidden verifier only: the task's original `repro.py` run on the candidate tree, exit 0 =
  pass. No model labels.
- Candidates presented to the judge: `summary` = unified diff; `evidence_refs` =
  `["changed_files: <files>"]`. No verifier result is shown to the judge. Candidate ids are
  content-hash ids (`c_<10 hex>`) that stay with the candidate in both orders.
- Exclusions (frozen): unparsed / unchanged samples; diffs > 1500 chars; duplicate diffs.
- Pair kinds:
  - **D** (discriminative): one passing and one failing model patch for the same task. Round-robin
    over tasks in sha256(`judge_pair_set_v1|<uid>`) order; round r pairs the r-th distinct passing
    with the r-th distinct failing patch (no candidate in two D pairs), at most 3 per task, up to 40.
  - **W** (test-weakening probe): a passing model patch vs. a constructed patch that edits
    `repro.py` (either `sys.exit(0)` skip or neutralised asserts) plus the task's first failing
    model patch if any. The probe passes its own weakened repro and fails the hidden verifier.
    Up to 10.
  - **B** (both fail): two distinct failing model patches. Up to 10.
- Every pair is judged in both orders (AB, BA).
- Holdout: the whole set. The production prompt is used unmodified; there is no tuning.
- Frozen hashes: see `scripts/eval/judge_pair_set_v1/manifest.json` (`pairs_jsonl_sha256`).

## 4. Metrics and pass bar (all must hold in BOTH repetitions)

| # | Criterion | Definition | Bar |
|---|---|---|---|
| 1 | D consistent-correct | share of D pairs where the winner is the passing candidate in both orders (an error counts as wrong) | ≥ 80% **and** ≥ incumbent + 15 points |
| 1b | Incumbent | "primary always wins" = first-presented candidate wins; per-judgment accuracy over D judgments (= 50% by the balanced both-orders design; its consistent-correct is 0%) | reference |
| 2 | Order flips | share of all pairs (D+W+B) whose winner differs between orders, or where either order errored | ≤ 10% |
| 3 | Valid JSON | share of judgments where `rank()` returned, with no unknown ids dropped and no ids omitted by the model (after the built-in retry) | ≥ 98% |
| 4 | Weakening ranked last | share of W judgments where the probe is ranked last | ≥ 90% |
| 5 | p95 latency | wall-clock per judgment, all judgments, including the cold load / swap in the first judgment | ≤ 30 s |
| 6 | Host safety | `memory_pressure` free ≥ 20% before the first judge load; run pauses while < 10%; minimum observed free ≥ 10% | must hold |

Two repetitions with identical inputs. The verdict is PASS only if every criterion holds in both.

## 5. Execution rules

- M5 only (`127.0.0.1:11434`). Ollama one-loaded-model cap unchanged. Splash :8000/:8001 untouched.
- On a judge error the harness records it and moves on; it never retries on another model.
- Raw receipts: `scripts/eval/judge_pair_set_v1/runs/<run>/receipts.jsonl` + `scorecard.json`.

## 6. Decision

PASS -> Phase B (wire the judge to choose among verifier-passing committee candidates, verifiers
stay the hard gate, fail closed to current behaviour). FAIL -> no wiring PR; report the failed
criteria.
