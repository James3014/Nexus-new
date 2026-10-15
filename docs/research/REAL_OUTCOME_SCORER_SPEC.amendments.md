# Real-Outcome Scorer Specification: amendment notes

These notes go with `docs/research/REAL_OUTCOME_SCORER_SPEC.md` (v1, pre-registered,
sha256 `315d95de21ea7ec82c97bf80165feaa052cb8a36fe99f3a1072d45ff74bb2bda`).

The v1 header says that file is frozen and never edited. So these notes live in this
sibling file, and the pre-registered file and its sha256 stay unchanged. No note
changes a scoring rule in v1. Any rule change still needs a new
`REAL_OUTCOME_SCORER_SPEC.v2.md`.

## 2026-10-14: A1, scorer version string

The v1 header names `SCORER_VERSION = "1.0.0"`. The scorer versions are:

| Version | Change | Scoring rules |
|---|---|---|
| `1.0.0` | first implementation (#1951) | v1 |
| `1.0.1` | the trusted impact-gate copy is registered in `sys.modules`, so the P2P(b) selector no longer fails silently | v1, unchanged |
| `1.1.0` | post-merge review follow-ups (#1951 review): input validation, write containment, a P2P run diagnostic, a summary fix and cache keys | v1, unchanged; A2–A4 below only add diagnostics, refusals for malformed or unsafe input, and operational behaviour |
| `1.2.0` | GOLD port fallback (#2233) | v1 for every task whose PR patches apply whole; `REAL_OUTCOME_SCORER_SPEC.v2.md` (v1 + A5) for the tasks that need the fallback. Each receipt records `spec_version` and that spec file's sha256. For all tasks, a symlinked oracle source file is refused (`NOT_SCORABLE_ORACLE_INVALID` / `ORACLE_FILE_UNSAFE`), an unsafe-input refusal like A3. `--summarize` headline numbers are what v1 would report (each v2 receipt counted as `NOT_SCORABLE_ORACLE_INVALID` / `GOLD_PORT_FAILED`); receipts of any other spec version are left out of both blocks (`unknown_spec_versions`) |
| `1.2.1` | scratch TMPDIR cleanup and cap (#2291), A6 below | unchanged from 1.2.0 (v1, or v2 for the GOLD port fallback); A6 is operational behaviour only |

Current scorer: `SCORER_VERSION = "1.2.1"`. Receipts record the version that wrote them.

## 2026-10-14: A2, P2P(b/c) run diagnostic (no rule change)

v1 already decides what happens when a P2P(b/c) run times out or fails to collect:
- §8: "A timeout yields no junit; all expected nodes of that invocation count as `fail`".
- §6.2: collection failure and absence from the junit count as `fail`.

So scoring stays exactly as v1 says:
- A failed `BASE+T` run contributes no base-pass nodes.
- A failed `GOLD` suspect run makes its suspects `gold_also_fails`. One case: the
  human fix deletes a module that an unchanged test imports.

Scorer 1.1.0 only adds a diagnostic field, `p2p_baseline_failures[]`, to the receipt.
It lists every candidate-independent P2P run (`BASE+T` runs 0–2, and the `GOLD` suspect
run) that timed out or exited with a code other than 0, 1 or 5. Exit code 5 means
nothing was collected. Each entry records tree, target, run, exit code and `timed_out`.
The field never changes a label, a sub-reason or `shadow_label`. It shows a reader
where a P2P set is empty, or a `gold_also_fails` comes from, because a run failed
rather than because tests failed.

## 2026-10-14: A3, input validation and write containment (clarification)

- Every merge-commit SHA in `ground_truth.json` must be a lowercase 40-hex SHA
  (§1: commits are addressed by full SHA only). A non-SHA value is a seal refusal
  (`ground_truth_merge_commit_sha_invalid`). The scorer refuses before any git call.
- A malformed base64 or gzip candidate payload is a seal refusal
  (`payload_malformed:*`, §3.4).
- A malformed untracked `size` (not an integer) is a seal refusal
  (`untracked_size_invalid`). A malformed ground-truth shape is also a seal refusal
  (`ground_truth_shape_invalid`). That covers:
  - the document is not an object;
  - `details` is not an object;
  - `merged_prs` is not a list.
- The following are `NOT_RUNNABLE/APPLY_FAILED` (§7 row 6, "escapes the tree"):
  - After the candidate diff is applied, any symlink anywhere in the worktree that
    resolves outside the tree. This covers git-ignored paths and chains of links. The
    worktree is walked without following links, and `.git` is skipped. A symlink
    tracked unchanged in BASE belongs to the repository and is not counted.
  - An untracked file whose resolved target escapes the tree or already exists. This
    includes a dangling symlink.
  - An oracle-file overwrite that would pass through an escaping parent symlink.
- An untracked path with a `.git` component at any depth, matched case-insensitively,
  is `untracked_path_unsafe` (APPLY_FAILED).

None of these changes how a candidate that applies cleanly is scored.

## 2026-10-14: A4, memory check and caches (clarification)

- §8 memory check: if `memory_pressure` returns nothing usable, free memory is treated
  as low. The runner waits with a bounded backoff (60, 120, 240, 300, 300 s). If no
  reading arrives, it stops the batch (exit 5) and does not score without the check.
- The env key (§8) also covers the resolved interpreter path and version, the extra
  import roots and the scorer version.
- The test-result cache key covers the same items. It also covers the run's role, so
  `CAND+T` runs are never replayed from a `GOLD` run with the same tree id
  (self-check (a)).

## 2026-10-15: A6, scratch TMPDIR cleanup and cap (operational, #2291)

Every pytest run gets `HOME=scratch/home` and `TMPDIR=scratch/tmp` (§8). Before 1.2.1,
`scratch/tmp` was never emptied, so one leaky test in any tree could fill the disk and
the leak carried over to every later task (#2291: 96 GB in one run).

Scorer 1.2.1:
- Empties `scratch/tmp` after every task that reached the tree stage, in the same cleanup
  step that removes the worktrees, and also when `--keep-trees` is set. Only the runner's
  own `junit-*.xml` files are kept while a run reads them; each is deleted as soon as its
  results are parsed and cached.
- Records the size of `scratch/tmp` before that cleanup as `scratch_tmp_bytes` in
  `real_outcome_timing.json`. The walk never follows symlinks.
- Fails a run that leaves more than `SCRATCH_TMP_CAP_BYTES` (20 GiB) in `scratch/tmp`.
  The run is treated like a crashed run on that tree: no outcomes (§8: its expected
  nodes count as `fail`), exit code `-2`, and the diagnostic `SCRATCH_TMP_CAP_EXCEEDED`.
  The diagnostic appears in `p2p_baseline_failures[]` (A2) or in the
  `GOLD_COLLECTION_FAILED` detail. `scratch/tmp` is then emptied.

No scoring rule changes: a run over the cap goes down the path v1 already defines for a
run without a usable junit report. The env and test-result cache keys include the scorer
version (A4), so 1.2.1 rebuilds its envs and does not reuse 1.2.0 results.
