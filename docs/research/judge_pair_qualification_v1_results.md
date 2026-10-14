# Committee judge qualification v1: results

Date: 2026-10-14. Host: Mac mini M5 Pro (64 GB). Judge: `qwen3.5:9b` (`local_qwen35_9b`, digest
`6488c96f…`) through the production `OllamaJudgeProvider.from_policy()` at `127.0.0.1:11434`.

Labels: **[F]** = measured or read directly. **[I]** = inference.

## Verdict: FAIL (no wiring PR)

**[F]** Four of the six frozen criteria failed, with the same numbers in both repetitions. The
judge is not admitted to choose committee winners, and Phase B (wiring) was not started.

- Frozen spec: `docs/research/judge_pair_qualification_v1_spec.md`, commit
  `db46c3d785ea7f8674d06ec413821b66978dfbf9` (pushed to `eval/judge-pair-qualification-v1`
  before the first scored run).
- Pair set: `scripts/eval/judge_pair_set_v1/pairs.jsonl`, sha256
  `ab2a84565b86f059c2b940386175b10b4ebc22edc6627a099ad7c81d0e1c4334`. It has 60 pairs: 40 D, 10 W
  and 10 B, giving 120 judgments per run.

| # | Criterion | Bar | Run 1 | Run 2 | Result |
|---|---|---|---|---|---|
| 1 | D consistent-correct (both orders) | ≥ 80% and ≥ incumbent + 15 | **40.0%** (16/40) | **40.0%** | FAIL |
| 1b | Incumbent "primary wins", per judgment | reference | 50.0% | 50.0% | — |
| 2 | Order flips (all 60 pairs; an error counts as a flip) | ≤ 10% | **38.3%** (23/60) | **38.3%** | FAIL |
| 3 | Valid JSON after the built-in retry | ≥ 98% | **80.0%** (96/120) | **80.0%** | FAIL |
| 4 | Test-weakening probe ranked last | ≥ 90% | 95.0% (19/20) | 95.0% | pass |
| 5 | p95 latency per judgment | ≤ 30 s | **112.6 s** | **172.6 s** | FAIL |
| 6 | Host memory (free ≥ 20% at start, min ≥ 10%) | must hold | start 48%, min 12% | start 37%, min 14% | pass |

Notes on the table:
- **Criterion 3.** A judgment counts as invalid if it raised an error, or if the model dropped or
  added ids. There were 14 errors per run (24 invalid judgments in total).
- **Criterion 5.** The median latency was 13.9 s in run 1 and 15.4 s in run 2. The maximum was
  323.5 s and 180.0 s.

## Why each criterion failed

### Criterion 1: picking the winner
- **[F]** On D judgments that returned a valid ranking, the judge picked the passing patch 46 out
  of 70 times (66%). The first-presented candidate won 43 out of 70 times (61%).
- **[F]** Of the 40 D pairs, 16 were judged correctly in both orders and 7 were judged wrong in
  both orders. The other 17 flipped with the order or errored.
- **[F] Upper bound.** Suppose every errored judgment had been correct. Criterion 1 would then be
  23/40 = 57.5%, still below 80%. The failure therefore does not depend on the JSON errors.
- **[F] By task set, valid D judgments correct:**
  - v1: 3/3;
  - v2: 19/25;
  - v3: 24/42, close to chance.
  - **[I]** The judge cannot tell, by reading a diff, whether the subtler v3 bugs are fixed. These
    include timezone handling, float/Decimal rounding, greedy regex and consumed iterators.

### Criterion 2: order flips
- **[F]** 10 of the 47 pairs where both orders were valid flipped with presentation order. The
  other 13 counted flips come from errors.
- **[F]** On B pairs (both candidates fail) the first-presented candidate won 10 out of 16 valid
  judgments. **[I]** This is a mild bias toward the first position.

### Criterion 3: invalid JSON
**[F]** Run 1 had 14 errors:
- 10 × `RuntimeError: ollama judge returned no usable ranking after 2 attempts`;
- 4 × `JudgeProviderUnavailable … timed out` at the provider's 180 s timeout.

Run 2 errored on the same 14 judgments. The split was 8 RuntimeError and 6 timeout.

**[F] One diagnostic re-run, not scored.** D-06 AB was re-run once after scoring, with the raw
content captured (`diagnostics/D-06_AB_unscored_rerun_content.txt`):
- the model returned a correct-looking ranking;
- but its `reason` string contained unescaped double quotes (`.get("email", None)`);
- so `json.loads` failed at char 590, and so did the provider's strict and lenient parsers;
- the retry produced the same bytes.

**[I]** So `format: "json"` on this gateway path does not guarantee valid JSON for this model.
**[I]** The timeouts look like long or runaway generations, because the provider sets no
`num_predict` cap.

### Criterion 5: latency
- **[F]** The host runs Ollama with `OLLAMA_KEEP_ALIVE=0`, read from the launchd environment of
  `com.james.local-models-ollama`, and the production provider sends no `keep_alive`. Every
  judgment therefore cold-loads `qwen3.5:9b`, which puts the median at about 14–15 s.
- **[F]** The p95 is dominated by the error and timeout tail. Successful judgments alone had a p95
  of 24.3 s in run 1 and 55.4 s in run 2.
- **[I]** Run 2 was slower because free memory was lower (37% at start, down to 14%).

## Determinism
**[F]** The two runs gave the same winner on all 120 judgments, and the same `response_sha256` on
every judgment that succeeded. The same 14 judgments errored in both runs; only the error type
changed for 2 of them. Temperature 0 makes the outcome reproducible. The failure is not noise.

## Host safety
- **[F]** Free memory was ≥ 20% before each run (48% and 37%).
- **[F]** The minimum observed during the runs was 12% and 14%, so no pause was triggered.
- **[F]** Ollama's one-model cap was not changed. Splash :8000/:8001 were not touched. No other
  model was used as a fallback.
- **[I]** The dips to 12–14% came from load outside this experiment, such as Splash or other
  sessions, because only `qwen3.5:9b` was in the Ollama slot during the runs.

## Raw receipts (sha256)
| File | sha256 |
|---|---|
| runs/run1/receipts.jsonl | 91c6cd00a451e2be9e8d48816c1685271f76f6004ba6a81aec42c469256fc53b |
| runs/run1/scorecard.json | d709229add5ac7462cf555e57211d26b35667434c20af99e4a19540c593e8c81 |
| runs/run2/receipts.jsonl | c89377dc992f3875182c11c670d6d4427f4b5eab7cbf982089e05557ec5eba4e |
| runs/run2/scorecard.json | a518fe5ed4c1781e851c34b8b8d18c3f4f6b82cd3d8657983c3ff6d1ab5c9b37 |
| candidates_7b.jsonl | 132030945ea389b8f6d9954ce5c0f858bbf8f16b845af9fee129fedb6ebf5aa0 |
| candidates_14b.jsonl | 6e31624d705cabc70ce42e3a064ff6d3502d9c64ac15d8b8f196e93e2652c759 |

- Paths are relative to `scripts/eval/judge_pair_set_v1/`.
- Each receipt row records:
  - the pair and order, and the presented ids;
  - the expected winner and the judge's winner and ranking;
  - the error, if any;
  - response sha256, wall time, and memory free before the call.
- System prompt sha256 (both runs): `8212297a58b39360ed45ad8316e05d549d1bd25bc5d38ab323067e39e225d633`.

## What this means for Nexus [I]
- **No change to committee winner selection.** The deterministic incumbent stays, and so does the
  verifier as the hard gate. Under the frozen spec, wiring this judge would let a model that is
  near chance on the harder v3 pairs choose the winner.
- **Criterion 4 passed.** The judge reliably demotes patches that edit or skip the test (19/20).
  That supports keeping it as an advisory test-tampering flag, which is a separate question with
  its own bar.
- **Options, each needing a new Owner decision and a new frozen spec (v2), not a re-score of v1:**
  - a provider fix: salvage the ranking, cap `num_predict`, and keep the model warm only inside a
    committee run;
  - a stronger judge: Splash Qwen3.6, which needs zero extra memory;
  - showing the judge each candidate's own verifier output.
  - None of these changes the v1 verdict.
