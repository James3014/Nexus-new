# Real-outcome replay of #1216 V11 (2026-10-13)

Post-hoc scoring of the sealed V11 (`automatic-v11-primary`) candidates with
the pre-registered real-outcome scorer (Issue #1950, PR #1951).

- **Spec:** `docs/research/REAL_OUTCOME_SCORER_SPEC.md` v1, sha256
  `315d95de21ea7ec82c97bf80165feaa052cb8a36fe99f3a1072d45ff74bb2bda`.
  It was pre-registered before any replay result existed and has not changed.
- **Scorer:** `nexus/research/real_outcome_scorer.py` 1.0.1.
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
| a | candidate := GOLD | all 14 valid-oracle tasks | see the follow-up section below |
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
  - All tasks were then rescored from scratch. No receipt from 1.0.0 is used.
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

## Self-check (a) follow-up

Status: running at the time of this commit (gold-as-candidate, one task at a
time). Results will be appended in a follow-up commit. Until (a) passes, the
headline above is provisional under spec §11.
