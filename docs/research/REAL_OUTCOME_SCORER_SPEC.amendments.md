# Real-Outcome Scorer Specification: amendment notes

These notes go with `docs/research/REAL_OUTCOME_SCORER_SPEC.md` (v1, pre-registered,
sha256 `315d95de21ea7ec82c97bf80165feaa052cb8a36fe99f3a1072d45ff74bb2bda`).

The v1 header says that file is frozen and never edited. So these notes live in this
sibling file, and the pre-registered file and its sha256 stay unchanged. A1–A4 change
no scoring rule in v1. A5 is the one exception: it adds a GOLD-construction fallback that
runs only where v1 has already given up (`GOLD_PORT_FAILED`), so no task v1 could score
is affected. Any other rule change still needs a new `REAL_OUTCOME_SCORER_SPEC.v2.md`.

## 2026-10-14: A1, scorer version string

The v1 header names `SCORER_VERSION = "1.0.0"`. The scorer versions are:

| Version | Change | Scoring rules |
|---|---|---|
| `1.0.0` | first implementation (#1951) | v1 |
| `1.0.1` | the trusted impact-gate copy is registered in `sys.modules`, so the P2P(b) selector no longer fails silently | v1, unchanged |
| `1.1.0` | post-merge review follow-ups (#1951 review): input validation, write containment, a P2P run diagnostic, a summary fix and cache keys | v1, unchanged; A2–A4 below only add diagnostics, refusals for malformed or unsafe input, and operational behaviour |
| `1.2.0` | GOLD port fallback (A5) | v1 for every task whose PR patches apply whole; A5 only for tasks v1 labels `GOLD_PORT_FAILED` |

Current scorer: `SCORER_VERSION = "1.2.0"`. Receipts record the version that wrote them.

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

## 2026-10-15: A5, GOLD port fallback when main moved (GOLD_PORT_FAILED tasks only)

**Problem.** §5 builds GOLD by applying each merged PR's net patch (`M^1..M`) onto BASE
with `git apply --3way`. When main moved between BASE and the merge, the patch can
conflict or touch a file that does not exist at BASE. v1 then labels the task
`NOT_SCORABLE_ORACLE_INVALID / GOLD_PORT_FAILED`. In the V11/V12 replays 12 tasks failed
this way. In every case BASE was an ancestor of `M^1`, and the failing files were:
- generated or documentation files (`README.md`, `docs/*.md`, `docs/*.json`, wiki
  generated JSON, an action `.yml`);
- an oracle test file that a later main commit had edited or added;
- in 3 tasks, a Python source file.

**Rule (scorer 1.2.0).** For each PR in §5 order:

1. Apply the whole net patch with `git apply --3way --binary`, exactly as v1. If it
   applies with no unmerged index entries, go on to the next PR. `gold_port_method = "3way"`.
2. Otherwise, restore the pre-PR state and replay the PR **file by file**
   (`gold_port_method = "3way_per_file_fallback"`):
   - If the file's own 3-way apply succeeds, keep the result.
   - If an **oracle test file** (§5 definition) does not merge, set it to its content
     in the merge commit `M`, or delete it if `M` deletes it. This is the SWE-bench
     rule: tests are taken at their post-fix state. The path is listed in
     `gold_port_test_files_from_merge`.
   - If a **documentation file** does not merge, leave it at its pre-PR state. The path
     is listed in `gold_port_dropped_non_code_paths`. Documentation files are:
     - prose (`.md .rst .txt`) anywhere;
     - data (`.json .jsonl .yml .yaml .csv`) only inside a documentation tree (first
       segment `docs`, or a segment ending in `_wiki_vault`).

     A path under `.github/`, and any config, workflow or action file, is never
     documentation.
   - If **any other file** (Python and all other code) does not merge, the task stays
     `GOLD_PORT_FAILED`. The paths are listed in `gold_port_failed_paths`.

**Why F2P/P2P semantics are unchanged.** `BASE+T` is BASE with every oracle test file
set to its GOLD content (§5). So `GOLD` and `BASE+T` share the same test files. Under
A5, GOLD's non-test content is BASE plus a **subset** of the human fix's non-test
changes. It never contains a non-test change made by another main commit. So an F2P
node (fails on all 3 `BASE+T` runs, passes on all 3 `GOLD` runs, §6.2) still flips only
because of the human fix.

Tests that a merge-tree test file brings in from other main commits do not pass on GOLD
unless the human fix makes them pass, so they cannot enter F2P. If they pass on both
trees they are P2P(a), and the candidate must keep them passing. That makes the check
stricter, never looser. §6.2–§6.4 and §7 are applied unchanged.

**Guard against a dropped file hiding an oracle node (`GOLD_REF`).** A test could read
a dropped doc/data file. That test would then fail on GOLD and silently leave F2P, so a
candidate that skips that part of the fix could still reach `RESOLVED`. To rule this
out, the scorer builds a detector tree whenever a file was dropped. `GOLD_REF` is GOLD
with each dropped file set to its merge-commit content. `GOLD_REF` is never a scoring
tree.

- The oracle modules run once on `GOLD_REF`. If any stable oracle node (not flaky, §6.2)
  has a different outcome than on GOLD, the task stays `GOLD_PORT_FAILED`, with
  `detail = "dropped_paths_change_oracle_outcome"` and `gold_ref_mismatch[]` listing the
  nodes. So a drop is accepted only when it provably changes no oracle outcome.
- If any `GOLD_REF` oracle invocation times out or exits with a code other than 0 or 1,
  the task stays `GOLD_PORT_FAILED` with `detail = "gold_ref_run_failed"` (fail closed).
- In §6.4 step 2, a P2P suspect is `gold_also_fails` only if it fails on **both** GOLD
  and a clean `GOLD_REF` run. A clean run exits 0, 1 or 5 and does not time out. If the
  suspect fails only on GOLD, or the `GOLD_REF` run is not clean, it stays a P2P new
  failure. This is stricter than v1, never looser.
- A path that one PR drops and a later PR changes again takes the later merge commit's
  content in `GOLD_REF`.

`trees.GOLD_REF` is recorded. A candidate that does not make the F2P nodes pass is still
`UNRESOLVED`/`PARTIAL`. The fixture tests
`test_fallback_cannot_make_a_wrong_candidate_resolved` and
`test_dropped_file_that_changes_an_oracle_outcome_stays_gold_port_failed` show this. The
fallback can still make F2P smaller in one case: a human test node that also needs a
non-test change from another main commit fails on GOLD. A candidate made at BASE could
not pass that node either. v1 already drops such nodes whenever the patch applies
cleanly.

**Previously scorable labels are unaffected.** Step 1 is v1's code path, unchanged. The
fallback runs only when step 1 fails for some PR, and v1 labels exactly those tasks
`GOLD_PORT_FAILED`. Every task v1 scored, whatever its label, builds the same GOLD tree,
the same oracle and the same label under 1.2.0. The new key `gold_port_method = "3way"`
is added to its receipt. The scorer version is part of the env and test-cache keys (A4),
so 1.2.0 never reuses 1.1.0 cached results.

Check (2026-10-15): the 1.2.0 scorer re-scored three V12 tasks into a fresh store, one
`RESOLVED`, one `UNRESOLVED` and one `BROKE_EXISTING`. All three labels matched the 1.1.0
receipts exactly. The PR for this amendment records the evidence.
