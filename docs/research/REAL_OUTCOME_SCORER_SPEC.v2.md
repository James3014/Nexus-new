# Real-Outcome Scorer Specification v2

**v2 = v1 + A5.** v1 is `docs/research/REAL_OUTCOME_SCORER_SPEC.md`, sha256
`315d95de21ea7ec82c97bf80165feaa052cb8a36fe99f3a1072d45ff74bb2bda`. That file stays
byte-identical. Every v1 rule applies in v2 unless A5 below says otherwise. The v1
amendment notes (A1–A4, `REAL_OUTCOME_SCORER_SPEC.amendments.md`) apply to v2 too.

This file is frozen once merged. A later rule change needs a v3 file.

## Status: post hoc, not pre-registered

A5 was designed **after** we saw the V11/V12 replays, where 12 tasks were
`NOT_SCORABLE_ORACLE_INVALID / GOLD_PORT_FAILED`. So v2 results are **not pre-registered
evidence**, and they are always reported apart from v1:

- A receipt whose GOLD needed the fallback (`gold_port_method` is not `"3way"`) records
  `spec_version: "v2"` and this file's sha256 in `spec_sha256`. Every other receipt records
  `spec_version: "v1"` and the v1 sha256. A receipt with no `spec_version` key predates
  v2 and is v1.
- `--summarize` gives its headline numbers exactly as v1 would report them: every v1
  receipt, plus every v2 receipt counted at its v1 label,
  `NOT_SCORABLE_ORACLE_INVALID / GOLD_PORT_FAILED` (under v1 the PR patch did not apply).
  So the v1 counts are complete and the valid-oracle denominator is the v1 one. A
  separate `v1_plus_v2` block counts the v2 receipts at their own labels.
  `spec_version_counts` counts every receipt by version. A receipt whose `spec_version`
  is present but is neither `"v1"` nor `"v2"` (including an empty or null value) is in
  neither block; `unknown_spec_versions` counts those by version.
- For every task whose PR patches all apply whole (step 1 below), v2 builds the same GOLD,
  oracle and label as v1. The receipt only gains the keys `spec_version` and
  `gold_port_method = "3way"` (scorer 1.2.0).

## A5: GOLD port fallback when main moved

**Problem.** v1 §5 builds GOLD by applying each merged PR's net patch (`M^1..M`) onto
BASE with `git apply --3way`. When main moved between BASE and the merge, the patch can
conflict, or touch a file that does not exist at BASE. v1 then gives up with
`GOLD_PORT_FAILED`.

### Rule 1: building GOLD

For each PR, in §5 order:

1. Apply the whole net patch with `git apply --3way --binary`, exactly as v1. If it
   applies with no unmerged index entries, go on to the next PR.
2. Otherwise restore the pre-PR state and replay the PR **file by file**
   (`gold_port_method = "3way_per_file_fallback"`):
   - A file whose own 3-way apply succeeds keeps the result.
   - An **oracle test file** (§5 definition) that does not merge is set to its content in
     the merge commit `M`, or deleted if `M` deletes it (the SWE-bench rule: tests are
     taken at their post-fix state). It is listed in `gold_port_test_files_from_merge`.
   - A **documentation file** that does not merge is left at its pre-PR state and listed
     in `gold_port_dropped_non_code_paths`. Documentation is:
     - prose (`.md`, `.rst`), and
     - text or data (`.txt .json .jsonl .yml .yaml .csv`) inside a documentation tree
       (first path segment `docs`, or a segment ending in `_wiki_vault`).

     A file is **never** documentation if it is an oracle test file, is under `.github/`,
     has an ancestor directory that contains `__init__.py` at BASE (package data the code
     may read at runtime), or has a directory segment named `prompts`, `templates` or
     `data` (any case).
   - **Any other file** that does not merge (all code and config) leaves the task
     `GOLD_PORT_FAILED`, with the paths in `gold_port_failed_paths`. So does a path that is
     not a safe relative path, and unmerged index entries left after the PR.
3. If a merge-taken oracle test file is **not** a test module (for example
   `conftest.py`, `__init__.py`, test data or a helper), whether or not it exists at BASE,
   the task is `NOT_SCORABLE_ORACLE_INVALID / GOLD_PORT_FAILED` with
   `detail = "merge_taken_test_support_file:<paths>"`. Such a file can change BASE tests
   in other files (a new `conftest.py` can even stop them being collected), and Rule 3
   re-runs only test modules.

GOLD's non-test content is therefore BASE plus a **subset** of the human fix's non-test
changes. It never contains a non-test change made by another main commit, so an F2P node
(fails 3/3 on `BASE+T`, passes 3/3 on `GOLD`, §6.2) still flips only because of the human
fix. Tests that a merge-taken file brings in from other main commits cannot enter F2P
unless the human fix alone makes them pass. If they pass on both trees they are P2P(a),
which only makes the check stricter. As a diagnostic, the receipt records
`gold_port_merge_test_nodes_failing_on_gold`: the number of nodes in merge-taken test
modules that fail on all GOLD oracle runs. It has no effect on the label.

### Rule 2: the GOLD_REF detector for dropped files

When any file was dropped, the scorer builds `GOLD_REF`: GOLD with each dropped file set
to its content in the **last** merge commit whose PR changed that path. `GOLD_REF` is
never a scoring tree.

- The oracle modules run once on `GOLD_REF`. If any stable oracle node (not flaky, §6.2)
  has a different outcome than on GOLD, or is collected on only one of the two trees, the
  task is `GOLD_PORT_FAILED` with `detail = "dropped_paths_change_oracle_outcome"`, and
  `gold_ref_mismatch` lists the nodes.
- In §6.4 step 2 a P2P suspect is `gold_also_fails` only if it fails on **both** GOLD and
  GOLD_REF. A suspect that passes on GOLD is a new failure whatever GOLD_REF says, so it
  is judged without GOLD_REF. For a P2P target, the GOLD_REF run is made only when at
  least one of its suspects (failing 3/3 on the candidate tree, passing 3/3 on the base
  tree) fails on GOLD.
- If the `GOLD_REF` oracle run times out or exits outside {0, 1}, the task is
  `NOT_SCORABLE_ORACLE_INVALID / GOLD_REF_RUN_FAILED`. The same holds when a `GOLD_REF`
  P2P run that was made (above) times out or exits outside {0, 1, 5}: the suspects that
  GOLD fails on that target get no verdict, neither excused nor counted against the
  candidate. This sub-reason takes precedence over `NOT_RUNNABLE` and over any other
  label.

**Known limit.** The `GOLD_REF` outcome check compares oracle modules only. A dropped file
that only non-oracle tests or runtime code read is guarded in two ways. First, the
`gold_also_fails` rule above. Second, the narrow documentation class in Rule 1, which
keeps package data and `prompts`/`templates`/`data` trees out of the droppable set.

### Rule 3: P2P(d), BASE tests lost from merge-taken test files

When a test file is taken from `M`, BASE tests that later main commits deleted or rewrote
in that file are gone from every scored tree. P2P(b/c) also ignores oracle files. So for
each merge-taken file that is a test module and exists at BASE, the scorer also runs
**the BASE version of that file** as a P2P(d) target. All trees in this comparison carry
the BASE bytes of **every** oracle file:

| Tree | Content |
|---|---|
| `BASE` | BASE |
| `CAND@BASE_TESTS` | the candidate's tree, with every oracle file set to BASE |
| `GOLD@BASE_TESTS` | GOLD, with every oracle file set to BASE |
| `GOLD_REF@BASE_TESTS` | GOLD_REF, with every oracle file set to BASE (only when files were dropped) |

§6.4 is applied unchanged, with these trees in place of `BASE+T`, `CAND+T`, GOLD and
GOLD_REF (and Rule 2 decides when `GOLD_REF@BASE_TESTS` is run). A node that passes on BASE run 0 and does not pass on CAND run 0 is a suspect.
It is a new failure if it fails 3/3 on `CAND@BASE_TESTS`, passes 3/3 on `BASE`, and does
not fail on both `GOLD@BASE_TESTS` and `GOLD_REF@BASE_TESTS`. Oracle node ids are **not**
excluded, because the BASE test body may differ from the merge-tree one. The receipt
records `p2p_d_targets` and `p2p_d_total`. A BASE test that the human fix itself retires
fails on `GOLD@BASE_TESTS`, so it is `gold_also_fails`.

**Why this rather than refusing.** The alternative was to refuse a task whenever BASE
nodes of a merge-taken file are missing from GOLD. That catches deletions only. A BASE
test that main **rewrote** under the same node id would still pass the check. It would
also discard every task where main merely renamed or regrouped tests. Rule 3 checks the
BASE behaviour directly, so it covers both deletions and rewrites.

### Rule 4: oracle sources are never followed through links

When oracle files are copied into a tree (BASE+T, CAND+T and the Rule 3 trees), a source
that is a symlink is refused. For BASE+T this gives
`NOT_SCORABLE_ORACLE_INVALID / ORACLE_FILE_UNSAFE`. In the Rule 3 trees, any unsafe path
met while building `GOLD@BASE_TESTS` or `GOLD_REF@BASE_TESTS` (candidate-independent
trees), and a symlinked BASE source for any of them, also gives
`NOT_SCORABLE_ORACLE_INVALID / ORACLE_FILE_UNSAFE`. Only an unsafe destination path in
`CAND@BASE_TESTS` is the candidate's `NOT_RUNNABLE / APPLY_FAILED`. A destination link is removed, never
written through. This refusal also applies to v1 tasks: it rejects unsafe input in the
same way as amendment A3.
