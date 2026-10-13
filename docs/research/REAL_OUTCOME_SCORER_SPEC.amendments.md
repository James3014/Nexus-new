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
| `1.1.0` | post-merge review follow-ups (#1951 review): input validation, write containment, P2P baseline failures recorded, summary fix, cache keys | v1, unchanged; A2–A4 below are clarifications |

Current scorer: `SCORER_VERSION = "1.1.0"`. Receipts record the version that wrote them.

## 2026-10-14: A2, P2P(b/c) runs with an unknown result (clarification)

v1 §6.3 defines the P2P(b/c) base set as the nodes that pass on `BASE+T`, and §8
says a timed-out invocation yields no junit. v1 does not say what happens when the
`BASE+T` run of a target (or a `BASE+T` rerun, or the `GOLD` run for suspects) times out
or exits with a code other than 0, 1 or 5. Exit code 5 means nothing was collected.
Treating that result as an empty, clean baseline would claim "no regression" for nodes
that were never observed.

Scorer 1.1.0 handles this case as follows:

- Each such run is recorded in the receipt as `p2p_baseline_failures[]`, with tree,
  target, run, exit code and `timed_out`.
- A confirmed P2P new failure (§6.4) still gives `BROKE_EXISTING`.
- Otherwise the task is `NOT_SCORABLE_ORACLE_INVALID` with sub-reason
  `P2P_BASELINE_FAILED`, so it leaves the valid-oracle set.
- For `NOT_RUNNABLE/SEALED_WHILE_PROVIDER_RUNNING`, the label stays `NOT_RUNNABLE`
  and `shadow_label` is left unset.

## 2026-10-14: A3, input validation and write containment (clarification)

- Every merge-commit SHA in `ground_truth.json` must be a lowercase 40-hex SHA
  (§1: commits are addressed by full SHA only). A non-SHA value is a seal refusal
  (`ground_truth_merge_commit_sha_invalid`). The scorer refuses before any git call.
- A malformed base64 or gzip candidate payload is a seal refusal
  (`payload_malformed:*`, §3.4).
- A candidate diff that creates a symlink resolving outside the tree, or an untracked
  file whose resolved target escapes the tree or already exists (including a dangling
  symlink), is `NOT_RUNNABLE/APPLY_FAILED` (§7 row 6, "escapes the tree").

## 2026-10-14: A4, memory check and caches (clarification)

- §8 memory check: if `memory_pressure` returns nothing usable, free memory is treated
  as low. The runner waits with a bounded backoff (60, 120, 240, 300, 300 s). If no
  reading arrives, it stops the batch (exit 5) and does not score without the check.
- The env key (§8) also covers the resolved interpreter path and version, the extra
  import roots and the scorer version.
- The test-result cache key covers the same items. It also covers the run's role, so
  `CAND+T` runs are never replayed from a `GOLD` run with the same tree id
  (self-check (a)).
