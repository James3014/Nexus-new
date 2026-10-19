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
| `1.2.2` | oracle-module run failure diagnostic (#2297), A7 below | unchanged from 1.2.1; A7 only adds a receipt field |
| `1.2.3` | pytest `--rootdir` pinned to the tree (#2707), A8 below | unchanged from 1.2.2; A8 fixes node ids under one work-dir layout |
| `1.2.4` | opt-in OS sandbox for pytest runs (#2723), A9 below | unchanged from 1.2.3 with `--sandbox none` (the default); A9 adds a receipt field and an opt-in run mode |
| `1.3.0` | opt-in spec v3 (#2709), A10 below | unchanged from 1.2.4 with `--spec-version v1` (the default: v1, or v2 for the GOLD port fallback). `--spec-version v3` scores under `REAL_OUTCOME_SCORER_SPEC.v3.md` (the same rules plus a metadata-only stub for the BASE project); those receipts record `spec_version: "v3"`, are left out of the headline and `v1_plus_v2`, and are counted in a separate `v3` summary block |

Current scorer: `SCORER_VERSION = "1.3.0"`. Receipts record the version that wrote them.

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

## 2026-10-15: A6, scratch cleanup, caps and lock (operational, #2291)

Every pytest run gets `HOME=scratch/home` and `TMPDIR=scratch/tmp` (§8). Before 1.2.1,
neither was ever emptied, so one leaky test in any tree could fill the disk and the
leak carried over to every later task (#2291: 96 GB in one run).

Scorer 1.2.1:
- **Cleanup.** After every task that reached the tree stage, `scratch/tmp` and
  `scratch/home` are emptied, in the same cleanup step that removes the worktrees, also
  with `--keep-trees`. Only the junit report of a run still in flight is kept; each
  report is deleted as soon as its results are parsed. Cleanup never follows a symlink
  and never raises: errors go to `scratch_tmp_cleanup_errors` in the timing receipt.
- **Receipt.** `real_outcome_timing.json` records `scratch_tmp_bytes` and
  `scratch_home_bytes`, the sizes before cleanup (regular files, symlinks not followed).
- **Process group.** Each pytest run starts in its own session. When it exits or times
  out, the whole process group is killed, so a child it left behind cannot keep writing
  while the next run is measured. A child that starts its own session escapes this.
- **Per-run cap.** A run that leaves more than `SCRATCH_TMP_CAP_BYTES` (20 GiB) in
  `scratch/tmp` + `scratch/home` (its junit report excluded) is never read as test
  results and is not cached:
  - on a candidate tree (`CAND+T`, `CAND@BASE_TESTS`): `NOT_RUNNABLE` /
    `SCRATCH_TMP_CAP_EXCEEDED`, no `shadow_label`;
  - on any other tree (`BASE+T`, `GOLD`, `GOLD_REF`, the P2P(d) trees):
    `NOT_SCORABLE_ORACLE_INVALID` / `ORACLE_RUN_FAILED`.
- **Per-task cap.** When the runs of one task together leave more than
  `SCRATCH_TMP_TASK_CAP_BYTES` (40 GiB), the task fails with sub-reason
  `SCRATCH_TMP_TASK_CAP_EXCEEDED`, not cached. If the run that crosses it is a candidate
  run, the label is `NOT_RUNNABLE` (the candidate stays in the denominator); otherwise it
  is `NOT_SCORABLE_ORACLE_INVALID`.
- In both cap cases, `detail` names the cap, tree, target, run, role and the bytes left.
- **Not limited:** the peak usage while a single run is still going (only the
  `SpeculativeSandbox` guard of #2291 prevents the 96 GB case), and writes outside
  `scratch/` (a test that writes elsewhere is not measured).
- **Old caches.** A `scratch/pytest-cache` written by a pre-release 1.2.1 build (PR
  #2295 at `2cf90bc`) may hold cap failures cached as exit `-2`; clear it before use.
- **Symlinked scratch.** If `scratch/tmp` or `scratch/home` is a symlink when a run
  starts or when cleanup runs, the scorer refuses (`ScratchUnsafe`, no receipt).
- **Lock.** `score_task` holds an exclusive `flock` on `<work>/.scorer.lock`, because
  cleanup would delete another scorer's in-flight files. A second scorer on the same
  `--work` stops at once (`ScorerBusy`, CLI exit 6).

Timeouts and crashes keep their v1 meaning (§8, A2): their expected nodes count as
`fail`, and a P2P baseline failure is a diagnostic only. The cap is a new refusal, like
the unsafe-input refusals of A3, and is never a benchmark label. The env and
test-result cache keys include the scorer version (A4), so 1.2.1 rebuilds its envs and
does not reuse 1.2.0 results.

## 2026-10-17: A7, oracle-module run failure diagnostic (no rule change)

Issue #2297 asked whether a timed-out or killed oracle run should change a label.
Decision: no. This is a diagnostic, never changes a label, like A2.

Scorer 1.2.2 adds the receipt field `run_failure_diagnostics[]`. It lists every oracle-module
run on `BASE+T` (runs 0-2) and every `CAND+T` run (majority reruns included) that timed
out or was killed by a signal (negative exit code, or above 128). Each entry records
`tree`, `target`, `run`, `exit_code` and `timed_out`, sorted by tree, target, run. The
field is `[]` when nothing failed, and is absent on receipts that end before the
candidate is evaluated.

- **Exit code 2 is not listed.** An oracle module that fails to collect on `BASE+T`
  exits 2; that is the normal way an F2P test fails there. Only a timeout or a signal
  counts as a crash.
- **GOLD runs are not listed.** A failed GOLD oracle run already refuses the task
  (`GOLD_COLLECTION_FAILED`).
- Scoring is unchanged: v1 labels, sub-reasons and `shadow_label` do not read the field.
  Receipts already sealed are neither changed nor recomputed.
- The test-result cache key includes the scorer version (A4), so 1.2.2 does not reuse
  1.2.1 results.

## 2026-10-19: A8, pytest rootdir pinned to the tree (no rule change)

Every pytest run now passes `--rootdir=<tree>`. Without it, a `--work` directory inside
another repository whose `pytest.ini` sits above the tree made pytest use that outer
directory as rootdir. Node ids then carried the path prefix (`work.tree.tests...`), no
expected F2P/P2P id matched, and a gold candidate was labelled `UNRESOLVED`
(nexus-runtime#200 in the layer-1 verifier audit, knowledge
`nexus/research/2026-10-19-layer1-remaining-verifiers/`).

- This adds one flag to the literal §8 test-run command. Scoring rules are unchanged:
  §8 already runs pytest with cwd = tree root, and v1 §6 always meant ids relative to
  that root. The flag only stops an outer directory from overriding it.
- Work directories outside any repository (all #2147 batches so far) gave the same ids
  before and after.
- One layout does change ids: a tree whose only pytest config file sits in a
  subdirectory (e.g. `py/pytest.ini`) now gets ids with that prefix (`py.tests...`).
  Labels do not change, because GOLD, BASE+T and CAND+T all run with the same flag and
  the oracle ids come from those runs. No Nexus repository has this layout.
- `--rootdir` does not stop pytest from loading an outer config file when the tree has
  none of its own. Keep `--work` outside other repositories.
- The test-result cache key includes the scorer version (A4), so 1.2.3 does not reuse
  1.2.2 results.

## 2026-10-19: A9, opt-in OS sandbox for pytest runs (no rule change when off)

The CLI gains `--sandbox {none,os}` and `PytestRunner` a matching `sandbox` argument.
The default is `none`.

- **`none` (default).** The pytest command, its environment, its timeout and its
  process-group kill are exactly those of 1.2.3 (§8 plus A8). Network is not blocked,
  as §8 says. #2147 v1 numbers stay comparable. Nothing in v1 changes.
- **`os`.** The same command runs under macOS `sandbox-exec`, with the shared profile
  from `nexus.engine.sandboxed_lane`. The environment is the §8 one, except that HOME
  and TMPDIR point to a fresh directory for this run only
  (`<scratch>/runs/<key>-<random>/{home,tmp}`, with the junit report beside them). That
  directory is deleted after the junit report is read, also after a timeout, an error
  or a cap refusal. So no run can read what an earlier run left in HOME or TMPDIR (for
  example a GOLD test's copy of the fix in a pytest basetemp), and no run can plant
  files there for a later one. A run can still change its own tree, which later runs on
  that same tree see, as under `none`.
- **Fresh tree paths under `os`.** Every scoring of a task builds its trees under a new
  `<work>/trees/<task_key>-<random>/` instead of `<work>/trees/<task_key>/`. They are
  removed at the end as before, unless `--keep-trees` is set. Sandbox write access is
  granted by path. A session-escaping child could otherwise plant files (for example a
  `conftest.py`) at a tree path that the next scoring of the same task, with the same
  `--work`, reuses. Cache keys use tree ids (content), never tree paths, so this changes
  no cached result. Under `none` the tree paths are unchanged.
  - Network is denied.
  - Writes are allowed only in the tree under test and the run's own directory.
  - Reads are allowed only in those places, the env directory, the interpreter it
    resolves to, the env's extra import roots and fixed system and toolchain paths.
    `$HOME` stays denied apart from those roots, and credential stores stay denied.
    `<work>/repos` and the experiment store are denied, so a test cannot read the merged
    fix from git objects. Other trees of the same task are not readable.
  - Every read root other than the tree and the run's own directory (the env
    directory, the interpreter prefix and each extra import root) is refused before the
    run (`SandboxError`) when it is or contains the work directory, or lies inside
    `<work>/repos`, `<work>/trees` or the store. Otherwise such a root would expose
    sibling trees, such as GOLD. `<work>/trees` is not also denied in the profile: the
    shared profile applies its deny rules last, so that would deny the run's own tree.
  - File metadata (`stat`, existence checks) stays readable everywhere, and
    `mach-lookup` is allowed. Both come from the shared profile. Signals reach only
    processes inside the same sandbox, so a test may kill its own subprocesses.
  - The timeout, the process-group kill, the junit parsing and the A6 caps are the same
    as for `none`. The A6 size checks at the start and end of each run count everything
    under `<scratch>/runs/` as well as the shared HOME and TMPDIR. So the run's own
    directory counts as what the run left. A directory that a session-escaping child
    re-creates after deletion, and keeps writing to, is measured and capped like the
    shared TMPDIR under `none`.
  - A child that leaves the process group (`setsid()`, `start_new_session=True`) is not
    killed when the run ends, in either mode. Under `os` it stays confined: it can write
    only to its own (deleted) run directory and its tree, never to a later run's HOME,
    TMPDIR, junit report or the result cache. Under `none` it is unconfined, as in
    1.2.3. Leftover run directories are removed by the A6 cleanup after each task.
- **Fail closed.** `--sandbox os` exits 7 before scoring anything when no OS sandbox
  exists (non-macOS, or `NEXUS_DISABLE_OS_SANDBOX` /
  `NEXUS_ULTRA_REVIEW_DISABLE_OS_SANDBOX` set to `1`). A runner bound to `os` refuses a
  run (`SandboxError`, no receipt) rather than run it unconfined.
- **Scoring with `os`.** The labels and rules are those of v1. A test that needs
  network, a git repository outside its tree or a path outside the allowed roots fails
  on GOLD or BASE and drops out of the oracle, as §8 already describes for network and
  secrets. So `os` and `none` results can differ, and they are reported separately.
  Example: on nexus-runtime#200 with `--candidate-override gold`, both modes give
  `RESOLVED`; under `os` one P2P test that runs `git` on the worktree
  (`test_source_ownership::test_ownership_source_tree_matches_head`) fails on BASE and
  drops out (953 P2P nodes instead of 954).
- Every receipt records `runner_sandbox` (`"none"` or `"os"`) and
  `runner_sandbox_profile_sha256`. That field is `null` for `none`. For `os` it is the
  sha256 of the scorer's SBPL profile. It comes from the same root list
  (`_PROFILE_ROOT_SPEC`) and builder as every run, with each
  run- or machine-specific path replaced by a fixed placeholder: the tree, the per-run
  directory, the env directory, the interpreter prefix, the extra import roots, the
  developer toolchain, the work directory, the store and `$HOME`. System and toolchain
  roots appear unresolved, whether or not they exist on the machine. The same scorer
  therefore gives the same hash on any machine, and any change to the shared profile or
  to the scorer's roots changes it.
- The test-result cache key includes the mode and the profile hash when the mode is
  `os`. So `os` and `none` results never share a cache entry, and a profile change never
  reuses older `os` results. The env build is not sandboxed and is the same for both
  modes, so the env cache key is unchanged. The test-result cache key includes the
  scorer version (A4), so 1.2.4 does not reuse 1.2.3 results.

## 2026-10-19: A10, spec v3, metadata-only project stub (opt-in rule set, #2709)

`REAL_OUTCOME_SCORER_SPEC.v3.md` holds the rule. In short: after
`uv sync --no-install-project`, the env gets a `<name>-<version>.dist-info` with only
`METADATA`, `INSTALLER` and `RECORD`, taken from BASE `pyproject.toml` `[project]`, so
`importlib.metadata.version(<project>)` works while imports still resolve only through
`PYTHONPATH=<tree>`. Without it, nexus-core's `pytest tests` stops at a
`PackageNotFoundError` for `nexus-certify` and collects about 2 nodes, which hides
regressions (Issue #2709).

- This is a rule change, so it is a new spec file and it is opt-in: the CLI gains
  `--spec-version {v1,v3}`, default `v1`. With `v1` nothing changes (env build, pytest
  command and environment, cache-key formulas, receipt fields). Scorer 1.3.0 does not
  reuse 1.2.4 envs or results, only because every key covers the scorer version (A4).
- v3 receipts are post hoc, not pre-registered, and are reported apart. The v1 headline
  and `v1_plus_v2` never include them.
- Owner decision (James, in session, 2026-10-19): 「同意」, approving Issue #2709 option 1,
  "Install only the project's metadata without letting it shadow the tree", as spec v3,
  opt-in, with the affected V12 tasks rescored and reported next to the unchanged v1
  headline.
