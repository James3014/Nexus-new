# Real-outcome replay of #1216 V11 (2026-10-13)

Post-hoc scoring of the sealed V11 (`automatic-v11-primary`) candidates with
the pre-registered real-outcome scorer (Issue #1950, PR #1951).

- **Spec:** `docs/research/REAL_OUTCOME_SCORER_SPEC.md` v1, sha256
  `315d95de21ea7ec82c97bf80165feaa052cb8a36fe99f3a1072d45ff74bb2bda`.
  It was pre-registered before any replay result existed and has not changed.
- **Scorer:** `nexus/research/real_outcome_scorer.py` 1.0.1. All receipts below were
  written by 1.0.1. Version 1.1.0 (post-merge review follow-ups, see the last section)
  did not rescore them.
- **Receipts:** `~/.local/state/nexus-real-outcome/v11-replay/receipts/tasks/<task>/`
  on the M5 host: `real_outcome.json`, `real_outcome_seal.json`, `real_outcome_timing.json`.
- **Inputs:** read-only copies (`chmod a-w`) of `state.json`, `raw.json`,
  `raw_seal.json` and `ground_truth.json` for the 37 V11 tasks that have a
  sealed raw. Copies are in `~/.local/state/nexus-real-outcome/v11-replay/store`.
  Nothing under `live/` was written.
- **Host:** M5, one task at a time, with `memory_pressure` checked before each
  task. Free memory stayed between 78 % and 81 %, so there were no pauses.
- No model or provider was dispatched.

## Method (summary of the spec)

1. **Seals.** The raw sha256, `state.raw_seal`, the ground-truth sha256, and the
   candidate diff and untracked-file digests must all verify. All 37 tasks verified.
2. **Trees.**
   - **BASE** is the captured `source_revision`.
   - **CAND** is BASE plus the sealed diff and the sealed untracked files.
   - **GOLD** is BASE plus each merged human PR's net patch (`M^1..M`), applied 3-way.
   - **BASE+T** and **CAND+T** have the human PR's test files overwritten with their GOLD versions.
3. **Oracle.** The oracle modules run 3× on GOLD and 3× on BASE+T.
   - **F2P** = nodes that pass all 3 times on GOLD and fail all 3 times on BASE+T.
   - **P2P(a)** = nodes that pass all 6 times.
   - Nodes that are flaky on either side are dropped.
4. **Regression set.**
   - **P2P(b), Nexus-new:** targets come from the trusted BASE copy of
     `pr_impact_gate.build_impact_plan`, applied to the union of the candidate's
     and gold's changed paths.
   - **P2P(c), nexus-runtime:** the full `tests/` suite.
   - A suspected regression counts only if it fails 3/3 on CAND+T, passes 3/3
     on BASE+T, and passes on GOLD.
5. **Labels** follow spec §7. NO_CANDIDATE and NOT_RUNNABLE count as failures
   in the headline.

## Results

### Label counts (37 tasks with a sealed raw)

| Label | n |
|---|---|
| RESOLVED | 3 |
| PARTIAL | 1 |
| UNRESOLVED | 4 |
| BROKE_EXISTING | 1 |
| NO_CANDIDATE | 3 |
| NOT_RUNNABLE (`SEALED_WHILE_PROVIDER_RUNNING`) | 2 |
| **Valid-oracle total** | **14** |
| NOT_SCORABLE_ORACLE_INVALID (`GOLD_PORT_FAILED`) | 5 |
| NOT_SCORABLE_NO_ORACLE | 1 |
| NOT_SCORABLE_NO_MERGED_PR | 1 |
| PENDING_GROUND_TRUTH | 16 |
| REFUSED_SEAL | 0 |

### Headline

- **Resolved rate:** 3 / 14 = **21.4 %**.
  - Exact Clopper–Pearson 95 % CI (the pre-registered interval): **[4.7 %, 50.8 %]**.
  - Wilson 95 % CI, for reference: [7.6 %, 47.6 %].
- **Excluding the leakage-flagged tasks** (#1858, #1896): 2 / 12 = 16.7 %.
  - Clopper–Pearson CI: [2.1 %, 48.4 %].
  - Wilson CI: [4.7 %, 44.8 %].
- **By route:**
  - B: 2 / 10 (CP CI [2.5 %, 55.6 %]).
  - C: 1 / 4 (CP CI [0.6 %, 80.6 %]).
- **By raw status:**
  - VALID: 3 / 8.
  - TIMEOUT: 0 / 3.
  - OUTCOME_UNKNOWN: 0 / 3.
- **By `capped`:**
  - capped: 0 / 8.
  - not capped: 3 / 6.

### Per task

| Task | Route | Raw status | Capped | Label | Sub-reason / note | F2P pass/total | P2P total | P2P new failures | Flaky dropped | Run time (s) |
|---|---|---|---|---|---|---|---|---|---|---|
| Nexus-new#1821 | B | TIMEOUT | yes | NO_CANDIDATE |  | –/9 | – | 0 | 0 | 3.6 |
| Nexus-new#1822 | C | OUTCOME_UNKNOWN | yes | BROKE_EXISTING | 1 confirmed: `tests.engine.test_forecast_gate_service::test_forecast_gate_service_reject_triggers_ash_and_state_persist` | 0/13 | 4185 | 1 | 0 | 1959.7 |
| Nexus-new#1823 | B | VALID | no | UNRESOLVED |  | 0/2 | 2681 | 0 | 0 | 516.7 |
| Nexus-new#1832 | C | VALID | no | NOT_SCORABLE_ORACLE_INVALID | GOLD_PORT_FAILED (PR #1833) | – | – | – | – | 1.8 |
| Nexus-new#1835 | B | TIMEOUT | yes | NOT_RUNNABLE | SEALED_WHILE_PROVIDER_RUNNING; shadow UNRESOLVED | 0/3 | 959 | 0 | 0 | 560.1 |
| Nexus-new#1844 | B | VALID | yes | NO_CANDIDATE |  | –/3 | – | 0 | 0 | 57.5 |
| Nexus-new#1850 | B | TIMEOUT | yes | NOT_SCORABLE_ORACLE_INVALID | GOLD_PORT_FAILED (PR #1863) | – | – | – | – | 8.0 |
| Nexus-new#1852 | C | OUTCOME_UNKNOWN | yes | UNRESOLVED |  | 0/25 | 3210 | 0 | 0 | 2089.6 |
| Nexus-new#1853 | C | OUTCOME_UNKNOWN | yes | NOT_SCORABLE_NO_MERGED_PR |  | – | – | – | – | 0.0 |
| Nexus-new#1854 | B | VALID | no | UNRESOLVED |  | 0/3 | 801 | 0 | 0 | 578.3 |
| Nexus-new#1856 | B | VALID | yes | UNRESOLVED |  | 0/6 | 2846 | 0 | 0 | 957.0 |
| Nexus-new#1858 | B | OUTCOME_UNKNOWN | yes | NO_CANDIDATE | LEAKAGE_POSSIBLE | –/2 | – | 0 | 0 | 45.1 |
| Nexus-new#1862 | B | OUTCOME_UNKNOWN | yes | NOT_SCORABLE_ORACLE_INVALID | GOLD_PORT_FAILED (PR #1863) | – | – | – | – | 4.6 |
| Nexus-new#1885 | C | TIMEOUT | yes | NOT_RUNNABLE | SEALED_WHILE_PROVIDER_RUNNING; shadow PARTIAL | 2/4 | 5673 | 0 | 0 | 2988.2 |
| Nexus-new#1896 | B | VALID | no | RESOLVED | LEAKAGE_POSSIBLE | 8/8 | 3312 | 0 | 0 | 2494.5 |
| Nexus-new#1904 | C | VALID | no | RESOLVED |  | 5/5 | 2083 | 0 | 22 | 1924.5 |
| nexus-learning#98 | B | VALID | no | NOT_SCORABLE_NO_ORACLE | human fix changed no test file | – | – | – | – | 0.2 |
| nexus-runtime#162 | B | VALID | no | PARTIAL |  | 5/6 | 692 | 0 | 0 | 31.8 |
| nexus-runtime#166 | B | VALID | no | NOT_SCORABLE_ORACLE_INVALID | GOLD_PORT_FAILED (PR #167) | – | – | – | – | 0.2 |
| nexus-runtime#172 | B | VALID | no | NOT_SCORABLE_ORACLE_INVALID | GOLD_PORT_FAILED (PR #173) | – | – | – | – | 0.2 |
| nexus-runtime#176 | B | VALID | no | RESOLVED |  | 2/2 | 844 | 0 | 0 | 32.9 |

Run time is the scorer's wall time per task. Oracle runs were reused from a
cache keyed by tree id, so a time can be shorter than a cold run.

**Pending ground truth (16, not scored):** Nexus-new #1820, #1841, #1845, #1869,
#1873, #1876, #1877, #1886, #1887, #1897, #1898, #1900, #1906, #1907;
nexus-core #243; nexus-runtime #178.

### Partial-candidate timeouts (reported separately, spec §10)

These are non-empty candidates whose raw status is TIMEOUT, or whose
failure_kind is TIMEOUT, or that hit the cap.

| Task | Label | Shadow label | Raw status | F2P |
|---|---|---|---|---|
| Nexus-new#1822 | BROKE_EXISTING | – | OUTCOME_UNKNOWN | 0/13 |
| Nexus-new#1835 | NOT_RUNNABLE | UNRESOLVED | TIMEOUT | 0/3 |
| Nexus-new#1852 | UNRESOLVED | – | OUTCOME_UNKNOWN | 0/25 |
| Nexus-new#1856 | UNRESOLVED | – | VALID (capped) | 0/6 |
| Nexus-new#1885 | NOT_RUNNABLE | PARTIAL | TIMEOUT | 2/4 |

None of the 5 is RESOLVED, even counting shadow labels.

### Why five oracles are invalid (GOLD_PORT_FAILED)

The human PR did not apply 3-way onto the captured base. The conflicting paths were:

| Task | Conflicting paths |
|---|---|
| Nexus-new#1832 (PR #1833) | four generated files under `nexus_wiki_vault/99_Schema/generated/` |
| Nexus-new#1850, #1862 (PR #1863) | `tests/services/test_mainchain_family_canary_matrix.py` |
| nexus-runtime#166 (PR #167), #172 (PR #173) | `README.md`, `docs/EXTRACTION_STATUS.md`, `docs/current-source-ownership.json` |

In 3 of the 5 tasks, only generated or docs files conflict. The v1 rule makes
these oracle-invalid by design. Any relaxation, such as skipping conflicting
non-code paths, would need a versioned v2 spec. It is not applied here.

## Self-checks (spec §11)

| # | Check | Scope | Result |
|---|---|---|---|
| a | candidate := GOLD | all 14 valid-oracle tasks | 14/14 RESOLVED (F2P all pass; 0 P2P new failures). This only shows that the gold diff round-trips; see "Self-check (a) detail" |
| b | candidate := empty | all 14 valid-oracle tasks | 14/14 NO_CANDIDATE |
| c | syntax error in a GOLD-changed non-test module | nexus-runtime#162 (`src/nexus_runtime/support/services/capability_registry.py`) | BROKE_EXISTING (691 P2P new failures) |
| d | one byte of `raw.json` changed (copy) | nexus-runtime#176 | refused (`raw_sha256_mismatch`), exit 3, no receipt |
| e | rescored in a fresh work dir (env rebuilt, tests rerun) | nexus-runtime#176 | `real_outcome.json` byte-identical |

The self-check receipts are in sibling stores under
`~/.local/state/nexus-real-outcome/v11-replay/`: `selfcheck-a-gold`,
`selfcheck-b-empty`, `selfcheck-c-broken`, `selfcheck-d-tamper` and
`selfcheck-e-repeat`.

## Run history (for audit)

- **`run_rt172.log`:** a one-task shakedown on nexus-runtime#172 with scorer
  1.0.0, before the full run. It gave GOLD_PORT_FAILED, which was confirmed by
  hand (see the conflict table above). That receipt went into the store that
  was later set aside, so it is not in `receipts/`.
- **`receipts.discarded-1.0.0-selector-bug/`:** the first full run used scorer
  1.0.0 and was stopped after 6 tasks.
  - The trusted impact-gate copy was loaded without being registered in
    `sys.modules`, so `dataclasses` with postponed annotations crashed.
  - As a result, every Nexus-new P2P(b) selection failed silently
    (`p2p_selector_failed: true`, targets empty).
  - Version 1.0.1 fixes this; the fixture gate now uses postponed annotations,
    so the test catches the bug.
  - All tasks were then rescored with 1.0.1 into a fresh receipt store. No receipt
    from 1.0.0 is used.
  - The rescoring reused the same `work/` directory. Its pytest result cache was keyed by
    (env key, tree id, target, ignores, run index), and the key did not include the
    scorer version. So pytest runs that 1.0.0 had already done on identical trees were
    replayed from the cache, not re-executed. These were the GOLD/BASE+T oracle runs of
    the first six tasks, and the CAND+T oracle runs where 1.0.0 had reached them. For
    example, Nexus-new#1821 took 3.6 s under 1.0.1.
  - This does not change any outcome, because 1.0.1 changed only how the P2P(b)
    selector is loaded, not how a pytest invocation is run or parsed. The P2P(b) targets
    were empty under 1.0.0, so all P2P(b) runs were executed fresh under 1.0.1.
    Self-check (e) used a fresh work directory, and its env and tests really were rebuilt
    and rerun.
  - Scorer 1.1.0 adds the scorer version and the run's role to the cache key.
  - The spec did not change.

## Limitations

- **Small sample.** n = 14, and the CI is wide. 16 tasks are still pending
  ground truth.
- **Over-specification.** The oracle is the human fix's tests, so it can
  over-specify the Issue. PARTIAL and the F2P counts expose this.
- **Environment.** The env is built from BASE's lock (Python 3.12, uv). Tests
  that need network, secrets or the CI donor locator fail on BASE or GOLD, so
  they drop out of F2P/P2P.
- **Leakage.** Agent-side exposure is known only from the pre-declared flag list
  (#1858, #1896: human fix branches were present in the agent's shadow clone).
- **Silent selector failure.** `p2p_selector_failed` has no label effect under v1.
  It is false for every Nexus-new task in this run.

## Self-check (a) detail

Gold-as-candidate gave 14/14 RESOLVED. Under scorer 1.0.1 this check could not fail.

- With candidate := GOLD, the CAND+T tree id equals the GOLD tree id.
- The 1.0.1 result cache was keyed by tree id, so every CAND+T oracle run was a
  cache hit of GOLD's run 0, which had passed all F2P nodes by construction.

So (a) shows only that the gold diff survives the candidate path (export as a binary
diff, `git apply` onto BASE, test-file overwrite) and reproduces the GOLD tree. It does
not show that the oracle re-passes on a fresh run, or that the scorer's labelling is
correct. The other checks hold: (b)–(e) pass, and (c) and (e) executed real runs.
Still, "all §11 checks pass" is weaker evidence than the spec intended. The headline
above should be read with that in mind.

Scorer 1.1.0 keys CAND+T runs separately from GOLD runs, so self-check (a) now
executes the oracle modules on CAND+T. A future (a) therefore also shows that F2P
re-passes on an independent run. It still cannot catch a scorer error that affects
GOLD and CAND+T alike. The V11 self-check (a) was not rerun.

- In 3 tasks, a few P2P nodes that pass on BASE+T fail on GOLD itself. These
  tests are broken by the human change, so they are dropped as `gold_also_fails`:
  - Nexus-new#1904: 3 nodes;
  - nexus-runtime#162: 1 node;
  - nexus-runtime#176: 1 node.
- Nexus-new#1904 also has 22 flaky nodes dropped.
- Receipts are in `selfcheck-a-gold/`.

## Post-merge review follow-ups (scorer 1.1.0, 2026-10-14)

An independent review of #1951 led to scorer 1.1.0, recorded in
`docs/research/REAL_OUTCOME_SCORER_SPEC.amendments.md`. The V11 receipts were not
rescored. Below is each change and what it means for V11, worked out from the code and
from the read-only receipts and pytest cache:

- **Merge-SHA validation and `--` before git positionals.** All V11 merge-commit SHAs
  and base SHAs are 40-hex, so no label changes.
- **Write containment (symlinks anywhere in the tree, or untracked files, that escape
  it → APPLY_FAILED; `.git` components refused).** No V11 diff contains a symlink (mode
  `120000`). Nexus-new tracks three symlinks in BASE, two of them absolute; these are
  exempt because they are unchanged. No untracked path is absolute, contains `..` or
  has a `.git` component. No label changes.
- **Shape checks (untracked `size`, ground-truth `details`/`merged_prs`).** Every V11
  size is an integer, and every ground-truth file has the expected shape. No refusal
  changes.
- **`by_raw_status` with a `None` status.** Every V11 valid-oracle task has a string
  raw status, so the breakdown above is unchanged.
- **P2P run diagnostic (`p2p_baseline_failures[]`).** This field is diagnostic only,
  and scoring stays v1. As it happens, every P2P(b/c) run in the cache for the 11 tasks
  with P2P targets exited with 0 or 1, with no timeout. That covers BASE+T runs 0–2,
  the GOLD runs and the CAND+T runs, in both `receipts/` and `selfcheck-a-gold/`. So
  the field would be empty for every V11 task.
- **Malformed payloads → seal refusal.** All V11 payloads decode under strict base64
  and gzip, so no refusal changes.
- **Memory-check unknown handling and the cache keys.** These have no label effect.

**Net: no V11 label, count or headline number changes.**
