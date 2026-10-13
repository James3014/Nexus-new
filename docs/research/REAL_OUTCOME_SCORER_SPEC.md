# Real-Outcome Scorer Specification (v1)

Status: pre-registration candidate for #1216 (hybrid deployment replication).
Scorer identity: `nexus.research.real_outcome_scorer`, `SCORER_VERSION = "1.0.0"`.
Receipt schema: `nexus.research.real_outcome.v1`.

This document is frozen once its SHA-256 is pre-registered. Any change is made
in a new file `REAL_OUTCOME_SCORER_SPEC.v2.md`; this file is never edited.

## 0. Purpose and non-goals

The existing hybrid replication score (`HybridReplicationStore.score_task`) records
the merged human PR's changed files and check runs. It never applies or tests
the agent's sealed candidate. This scorer answers one question per task:

> Does the agent's own sealed candidate make the human fix's tests pass on the
> captured base, without breaking tests that passed before?

It is a **post-hoc, read-only** scorer, SWE-bench style. It:

- never writes into the experiment store, the daemon state, frozen bindings or
  the live shadow clones;
- never dispatches a model or provider;
- writes only to its own outcome store (create-only receipts).

## 1. Inputs

Per task directory `<store>/tasks/<task_key>/` the scorer reads exactly four files:

| File | Use |
|---|---|
| `state.json` | phase, `raw_seal`, `ground_truth.sha256`, `ground_truth.terminal_state` |
| `raw_seal.json` | `raw_sha256` |
| `raw.json` | the sealed candidate (§2) |
| `ground_truth.json` | merged PRs (the oracle source) |

`effects/`, provider logs, journals and live shadow trees are **not** inputs.

Repository objects come from a scorer-owned git repository (one per repo),
populated by fetching from the local checkout and from `origin`. Every commit
the scorer uses is addressed by full SHA; refs are never used.

## 2. Candidate format (sealed)

From `raw.json`:

- `raw_response.candidate_packet.source_revision` → **BASE** commit SHA.
- `raw_response.strong_online_raw_response` (`so`):
  - `diff_gzip_base64` → gzip of `git diff --binary HEAD` over tracked files.
    If `diff_sha256` is present it must equal `sha256(decompressed diff)`.
  - `untracked_files[]` → `{path, sha256, size, gzip_base64}` new files that are
    not in the diff. Each decompressed payload must match `sha256` and `size`.
  - `status`, `failure_kind`, `scope_valid`, `wall_time_seconds`.
- `raw_response.strong_online_timeout_seconds` → the provider cap.
- top-level `route`, `wall_time_seconds`.

**Empty candidate**: decompressed diff is empty or whitespace-only **and**
`untracked_files` is empty.

## 3. Seal verification (refusal rules)

Before any other read is interpreted, the scorer verifies, and **refuses**
(exit non-zero, no receipt written) on any mismatch:

1. `sha256(raw.json bytes) == raw_seal.json.raw_sha256`.
2. `state.json.raw_seal == raw_seal.json` (same object).
3. If the task is terminal: `sha256(ground_truth.json bytes) == state.ground_truth.sha256`.
4. Candidate payload digests (§2) match.

Refusal is not a label. A refused task is reported as `REFUSED_SEAL` in the
run log and is excluded from every denominator; any refusal in a replay is a
blocking defect to be investigated.

## 4. Order of operations (leakage control)

1. Verify the raw seal (§3.1–3.2). Decode the candidate and record
   `candidate_digest = sha256(diff) + sorted untracked (path, sha256)`.
2. Only then open `ground_truth.json` and verify it (§3.3).
3. Build the oracle (§6) from ground truth and BASE **only**. The oracle
   construction never reads the candidate.
4. Score the candidate against the frozen oracle.

Leakage rules:

- The oracle (test files, F2P/P2P node lists) is derived only from
  `ground_truth.json` after the raw is sealed. It is never written into the
  experiment store or anywhere the agent could read during generation.
- The scorer module imports no human-PR data before step 2.
- The scorer cannot detect agent-side exposure to the human fix (for example,
  fix branches present in the agent's shadow clone). Such exposure is recorded
  from an external, pre-declared list (`--leakage-flags <json>`, mapping
  `task_key → reason`) as `leakage_flags` in the receipt. Flags never change the
  label; the headline is also reported excluding flagged tasks (§10).

## 5. Trees

All trees are scorer-owned detached worktrees of the scorer repo.

| Tree | Construction |
|---|---|
| `BASE` | checkout of BASE |
| `CAND` | `BASE` + `git apply --binary` of the sealed diff + write each untracked file |
| `GOLD` | `BASE` + each merged PR's net patch `git diff --binary M^1 M` (M = `merge_commit_sha`), PRs in ascending `merged_at` order (ties by PR number), each applied with `git apply --3way --binary` |
| `BASE+T` | `BASE` with every oracle test file set to its `GOLD` state |
| `CAND+T` | `CAND` with every oracle test file set to its `GOLD` state |

- Each tree is committed in the scorer repo so it has a git tree id; tree ids
  are recorded in the receipt.
- **Oracle test files** = paths changed by the merged PR net patches that match
  any of: first segment `tests/`; any `/tests/` segment; basename `test_*.py`;
  basename `*_test.py`; basename `conftest.py`.
- **Test-file overwrite** (SWE-bench rule): in `CAND+T`, every oracle test file
  is replaced by its `GOLD` content (deleted if `GOLD` deletes it). Candidate
  edits to those files are discarded. Candidate edits to other test files are
  kept.
- **Oracle modules** = oracle test files that exist in `GOLD`, end in `.py`, and
  whose basename matches `test_*.py` or `*_test.py`.

## 6. Oracle construction (candidate-independent)

### 6.1 Validity gates (in order)

| Gate | Failure label |
|---|---|
| `terminal_state != CLOSED_WITH_MERGED_PR` | `NOT_SCORABLE_NO_MERGED_PR` |
| merged PRs change no oracle test file | `NOT_SCORABLE_NO_ORACLE` |
| a merge commit is missing, or a PR patch fails to apply 3-way on the running `GOLD`, or the result has conflict markers in the index | `NOT_SCORABLE_ORACLE_INVALID` / `GOLD_PORT_FAILED` |
| the environment for BASE cannot be built (§8) | `NOT_SCORABLE_ORACLE_INVALID` / `ENV_FAILED` |
| any oracle-module pytest invocation on `GOLD` exits with a code other than 0 or 1, or times out | `NOT_SCORABLE_ORACLE_INVALID` / `GOLD_COLLECTION_FAILED` |
| F2P is empty after flake removal | `NOT_SCORABLE_ORACLE_INVALID` / `EMPTY_F2P` |

Environment failures are candidate-independent, so they are oracle-invalid,
not a candidate failure.

### 6.2 FAIL_TO_PASS (F2P)

Oracle modules are run on `BASE+T` 3 times and on `GOLD` 3 times (one pytest
invocation per module per run, §8). A node's outcome is `pass` or `fail`;
`error`, `skipped-with-error`, collection failure and absence from the junit
report all count as `fail`. `skipped`/`xfail` nodes are `skip`.

- A node is **flaky** if its outcome differs across the 3 runs on either tree.
  Flaky nodes are removed from F2P and P2P and counted in `flaky_dropped`.
- **F2P** = nodes that pass in all 3 `GOLD` runs and fail in all 3 `BASE+T` runs
  (absent nodes count as fail).
- **P2P(a)** = oracle-module nodes that pass in all 3 runs on both trees.

### 6.3 PASS_TO_PASS (P2P), regression set

**P2P(b), Nexus-new.** Target selection uses the **trusted base copy** of the
impact gate: the scorer imports `scripts/ops/pr_impact_gate.py` from the
`BASE` worktree (never from `CAND`/`CAND+T`/`GOLD`) in a subprocess and calls
`build_impact_plan(changed_paths=U, root=BASE)` with no SHAs, where
`U = paths changed CAND vs BASE ∪ paths changed GOLD vs BASE`.
Targets = `pytest_targets` minus oracle test files. The plan JSON and its
sha256 are recorded. The scorer runs and classifies the targets itself
(node-level, §6.4); it does not call the gate's `run`/`classify` subcommands,
whose provenance binding requires PR-shaped commits.

If `BASE` has no `scripts/ops/pr_impact_gate.py` or the call fails, P2P(b) is
empty and `p2p_selector_failed = true` is recorded (no label effect).

**P2P(c), small repos** (`nexus-runtime`, `nexus-core`, `nexus-learning`):
target = the repo's whole test suite (`tests/`), minus oracle test files.

**Running.** Each target is a separate pytest invocation (§8), run once on
`BASE+T` and once on `CAND+T`. P2P(b/c) base set = nodes that pass on `BASE+T`.

### 6.4 Candidate evaluation

Given a non-empty candidate that applies:

1. Run the oracle modules on `CAND+T` once. For each F2P or P2P(a) node that
   does not pass, rerun the oracle modules on `CAND+T` 2 more times; the node's
   candidate outcome is the majority of the 3 runs.
2. Run the P2P(b/c) targets on `CAND+T` once. A **suspect** is a node that
   passed on `BASE+T` and does not pass on `CAND+T` (absent = fail). For
   suspects: rerun the containing targets 2 more times on `CAND+T` and
   2 more times on `BASE+T`, and once on `GOLD`.
   - Suspect not failing on all 3 `CAND+T` runs, or not passing on all 3 `BASE+T` runs → `flaky_dropped`.
   - Suspect failing on `GOLD` → dropped as `gold_also_fails` (the intended change breaks it).
   - Otherwise it is a **P2P new failure**.
3. P2P(a) nodes whose candidate majority outcome is fail are also P2P new failures.

## 7. Labels

Evaluated in order; first match wins.

| # | Label | Rule |
|---|---|---|
| 1 | `PENDING_GROUND_TRUTH` | task has no `ground_truth.json` / not terminal |
| 2 | `NOT_SCORABLE_NO_MERGED_PR` | §6.1 |
| 3 | `NOT_SCORABLE_NO_ORACLE` | §6.1 |
| 4 | `NOT_SCORABLE_ORACLE_INVALID` | §6.1 (sub-reason recorded) |
| 5 | `NO_CANDIDATE` | empty candidate (§2) |
| 6 | `NOT_RUNNABLE` | sub-reasons, in order: `SCOPE_INVALID` (`so.scope_valid` is false); `SEALED_WHILE_PROVIDER_RUNNING` (`so.status == "TIMEOUT"`, i.e. the harness poller gave up and sealed before the provider operation was terminal); `APPLY_FAILED` (diff does not apply on BASE, or an untracked path already exists in the diff result or escapes the tree) |
| 7 | `BROKE_EXISTING` | ≥1 P2P new failure (outranks F2P success) |
| 8 | `RESOLVED` | all F2P nodes pass on `CAND+T` |
| 9 | `PARTIAL` | ≥1 but not all F2P pass |
| 10 | `UNRESOLVED` | 0 F2P pass |

For `NOT_RUNNABLE/SEALED_WHILE_PROVIDER_RUNNING` with a candidate that applies,
the scorer also evaluates it (§6.4) and records `shadow_label` (labels 7–10).
`shadow_label` is report-only and never enters the headline.

## 8. Execution environment

- **Env build** (network allowed; tests never run here):
  - Nexus-new: `UV_PROJECT_ENVIRONMENT=<env> uv sync --directory BASE --frozen --all-groups --all-extras --no-install-project`, then, if present in BASE, `uv pip install -r requirements/canonical-learning.txt` and `-r requirements/canonical-runtime.txt`.
  - Repos with `uv.lock`: `uv sync --frozen --all-groups --no-install-project`.
  - Repos without `uv.lock` (nexus-runtime): `uv venv` + `uv pip install pytest==9.0.2 pytest-asyncio==1.3.0 anyio==4.12.1 pydantic==2.13.5 PyYAML==6.0.3` + `nexus-learning` from the commit pinned in BASE's `.github/workflows/tests.yml` (the `ref:` of the `James3014/nexus-learning` checkout).
  - Env key = sha256 of (repo, recipe id, BASE `pyproject.toml`, `uv.lock`, canonical requirement files, workflow pin). Envs are cached by key. The env is always built from BASE; candidate or gold dependency changes are **not** installed.
  - Python: uv-managed `3.12`. uv, Python and lock digests are recorded.
- **Test run**: `<env>/bin/python -m pytest <target> -q -p no:cacheprovider --junitxml=<file>`, cwd = tree root, with a scrubbed environment: only `PATH=<env>/bin:/usr/bin:/bin`, `HOME=<scratch home>`, `TMPDIR=<scratch tmp>`, `PYTHONPATH=<tree>` (plus `<tree>/src` if it exists), `PYTHONHASHSEED=0`, `PYTHONDONTWRITEBYTECODE=1`, `LANG=en_US.UTF-8`, `TZ=UTC`. No GitHub, provider or Jev credentials are present. Network is not blocked; tests needing network or secrets fail on GOLD or BASE and drop out.
- Hard timeout per pytest invocation: 1800 s. A timeout yields no junit; all expected nodes of that invocation count as `fail`.
- Concurrency 1. Before each task the runner checks `memory_pressure`; if free memory < 20 % it waits (re-checking every 60 s) and records the wait.

## 9. Receipt

Written create-only to `<out>/tasks/<task_key>/`:

- `real_outcome.json` — deterministic content only: schema, scorer version,
  spec sha256, task key, repo, route, base SHA, `candidate_digest`,
  `candidate_raw_status`, `failure_kind`, `capped`, label, sub-reason,
  `shadow_label`, `leakage_flags`, merged PRs, oracle test files, tree ids
  (BASE, CAND, GOLD, BASE+T, CAND+T), env key, F2P/P2P(a) node lists,
  `f2p_pass`, `f2p_total`, `p2p_total`, `p2p_new_failures[]`, `flaky_dropped`,
  `gold_also_fails`, impact-plan sha256, and per-tree outcome digests
  (sha256 of the sorted node→outcome map). All lists are sorted.
- `real_outcome_seal.json` — `{schema, path, sha256}` of `real_outcome.json`.
- `real_outcome_timing.json` — wall times, memory-pressure waits, host,
  tool versions. Not covered by determinism.

`capped = top-level wall_time_seconds ≥ strong_online_timeout_seconds − 60`.

## 10. Headline metric

- **Valid-oracle set V** = tasks with label in {`NO_CANDIDATE`, `NOT_RUNNABLE`,
  `BROKE_EXISTING`, `RESOLVED`, `PARTIAL`, `UNRESOLVED`}.
- **Resolved rate** = `#RESOLVED / |V|`, with an exact (Clopper–Pearson) 95 % CI.
  `NO_CANDIDATE` and `NOT_RUNNABLE` count as failures.
- Always reported next to the counts of every `NOT_SCORABLE_*`,
  `PENDING_GROUND_TRUTH` and `REFUSED_SEAL`, never instead of them.
- Secondary breakdowns: by route (B/C); by `candidate_raw_status`; by `capped`;
  excluding `leakage_flags` tasks.
- **Partial-candidate timeouts** are reported separately: tasks in V whose raw
  status is `TIMEOUT`, or whose `failure_kind` is `TIMEOUT`, or `capped`, with a
  non-empty candidate; listed with label and `shadow_label`.

## 11. Self-checks

Fixture-repo tests (unit tests) and the replay both run these. All must pass
before any replay number is reported.

| # | Check | Expected |
|---|---|---|
| a | candidate := GOLD's net diff vs BASE, for every valid oracle | `RESOLVED` for 100 % |
| b | candidate := empty | `NO_CANDIDATE` |
| c | candidate := syntax error injected into a non-test module covered by P2P | `BROKE_EXISTING` |
| d | one byte of `raw.json` changed | refusal (no receipt) |
| e | the same task scored twice into two fresh outcome stores | byte-identical `real_outcome.json` |

In the replay, (a) and (b) run on every valid-oracle task; (c), (d), (e) run on
at least one task each (c needs a task whose GOLD changes a non-test `.py`
module with ≥1 P2P(b/c) node importing it; if none exists, (c) is
covered by the fixture test only, and that is stated).

## 12. Known limits

- Oracle over-specification: the human PR may do more than the Issue asked;
  `PARTIAL` and `f2p_pass/f2p_total` expose this.
- Docs/config-only fixes have no oracle (`NOT_SCORABLE_NO_ORACLE`).
- Binary hunks captured through text stdout may not apply → `APPLY_FAILED`.
- P2P(b) target selection inherits the impact selector's coverage.
