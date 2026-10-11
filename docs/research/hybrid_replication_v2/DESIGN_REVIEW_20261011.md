# #1216 design review — why the prospective cohort has not produced a result

Date: 2026-10-11. Scope: James3014/Nexus-new#1216 (Hybrid Deployment Replication,
fresh mixed cohort). Authority: review only. No contract delta is made here; every
change below is a proposal for an Owner decision.

## 1. Where the experiment actually stands

| Generation | Opened (T_auto) | Ended | Lifetime | Why it ended | Primary tasks kept |
|---|---|---|---|---|---|
| GEN-001 | 2026-09-29 23:43Z (T0) | 2026-09-30 | ~1 day | intake continuity not preserved (5 post-T0 issues missed) | 0 |
| GEN-002 | 2026-09-30 23:08Z | 2026-10-02 | ~1 day | manual era superseded by automation (Wave 1/2) | 0 |
| V1/V2 | 2026-10-02 02:36Z | ~2026-10-04 | ~2 days | transport change #1373 moved the execution identity | 0 (44 captured, protocol-only) |
| V3/V4/V5 | 2026-10-05 03:00Z | 2026-10-06 | ~1.5 days | binding-loader / transport identity defects, readiness false-greens | 0 (47 captured, protocol-only) |
| V6-r3 | 2026-10-07 05:39Z | 2026-10-07 10:35Z | 5 hours | one task (#1553) closed before provider start; generation fail-closed | 0 (9 captured, protocol-only) |
| V7 | label only | — | — | dispatcher hash rebind (#1411) | 0 |
| V10 | never activated | 2026-10-10 | — | dispatcher changed again on main (#1714) before activation; voided | 0 |
| V11 | proposed | — | — | waiting on #1718 merge, then 7-step readiness | 0 |

After 11 days: 100 natural tasks captured, 0 tasks in a valid primary cohort, 44
Issue comments, ~38 PRs and 23 commits on the pipeline source. In addition, the
keyword gate found on 2026-10-08 (comment 6071272894) means that none of the
100 captured tasks ever exercised the stack under test, so even the protocol-only
evidence says nothing about D2/DM1.

The question asked was whether this is a design problem. It is. The repeated
failures are not independent bugs; they are the predictable consequences of five
design choices. Fixing symptoms one wave at a time has not changed the failure
rate because the causes are upstream of the code.

## 2. Root causes (design, not implementation)

### 2.1 The frozen runtime is bound to a `main` that moves 30 times a day

The execution identity is defined as the exact sha256 of `scripts/ops/nexus-agy-dispatch`
plus the merge commit of `main`, and the identity preflight refuses to run when
they differ (`hybrid_replication_live.py`, `_load_binding`). But the dispatcher is
shared production code that other campaigns (#1362, #1411, #1714, DSH) edit daily:

- merges to `main`: 33 on 10-07, 30 on 10-09;
- `nexus-agy-dispatch` changed 5 times on 2026-10-10 alone;
- consequence: V6 -> V7 -> V10 (void) -> V11 within 72 hours, each rebind
  restarting the 7-step readiness gate from scratch.

The experiment therefore cannot outlive the repository's own churn. The Issue
contract lists what actually matters for identity (Jev alias/resolved model,
strong-Online model, CLI version, acquisition policy revision, repository base
revision). A file hash of a shared dispatcher is a stricter proxy than the
contract requires, and it couples the experiment clock to unrelated engineering.

Comment 6094518130 already asks the Owner to rule on this ("hold dispatcher
changes on main once readiness starts, or each change forces a new generation").
Neither option works: holding `main` blocks every other campaign for weeks, and
"new generation per change" is what has been happening.

Proposal: freeze the runtime as an immutable artifact outside `main` (a tagged
detached worktree plus a pinned dispatcher copy inside the experiment root, or an
OCI digest). The generation identity is the artifact digest plus the model/CLI
identities the contract names. Later changes to `main` do not touch it. The
experiment only rebinds when the Owner explicitly opens a new generation.

### 2.2 Fail-close is applied at generation granularity

One task missing its prospective window (#1553, created 10:27:48Z, closed
10:28:14Z) voided the whole V6-r3 generation and discarded 8 other admitted tasks
and a valid T_auto. The code already has a per-task disposition for exactly this
case (`PROTOCOL_EVIDENCE_ONLY_DO_NOT_COUNT`, `prospective_protocol_loss.json`),
and the Issue contract already says "keep old observations" across generations
and allows quality pooling when the evaluation contract is unchanged.

Proposal: a protocol loss on task X excludes task X. A generation is reset only
for (a) execution-identity drift, or (b) a systematic defect that affected every
task (the keyword gate was one). Record the rule in the contract so a future
reconciliation does not re-void a healthy cohort.

### 2.3 The experiment is measuring its own repair work (reflexivity)

Issues created in the 8 candidate repositories since T0 (all authored by the
Owner's agents):

| | count |
|---|---|
| issues, all 8 repos | 446 |
| issues, Nexus-new | 223 |
| Nexus-new issues whose title is about the experiment itself (1216 / hybrid / replication / readiness / wave / cohort / generation / reconcile / control) | 88 (39.5%) |
| other 7 repos, same test | 5–8% each |

Forty percent of the Nexus-new "natural workload" is the #1216 engineering loop.
Every protocol break creates repair Issues and PRs, which move `main`, which
drifts the identity, which forces a new generation, which produces more repair
Issues. The capture workflow only excludes `#1216` itself
(`EXPERIMENT_CONTROL_ISSUE`), not the campaign.

Proposal: exclude from the primary denominator any issue that references #1216
or #1196, carries a hybrid-replication marker, or touches the hybrid-replication
paths; or run the primary cohort on the other 7 repositories only (223 of 446
issues are elsewhere). Either way, freeze engineering on the hybrid-replication
source paths while a generation is collecting.

### 2.4 Readiness proves "something ran", not "the stack under test ran"

The readiness control is an Owner-created template Issue routed to C. It passed
on V6-r3 while every natural task was being routed to C by a keyword probe that
never called D0, D2, or Jev. The amendment removed the gate, but the readiness
design is unchanged: it still cannot distinguish "D2/DM1 reachable" from "C
fallback always". The same blind spot will pass V11.

Proposal: readiness requires one natural-shaped control that must reach the DM1
intercept (a sealed `dm1` decision in raw, accepted or escalated), in addition to
the current C-shaped control and the daemon-absent negative control.

### 2.5 Activation state has three sources of truth, all outside the repository

- 8 repositories x 5 GitHub Actions variables (`NEXUS_HYBRID_REPLICATION_*`),
  flipped by hand; nothing in the repo reads them except the capture workflow,
  which is copied eight times (#1727);
- `LIVE_BINDING.json` on one Mac mini (read by the stack);
- `ACTIVE_GENERATION.json` on the same Mac (read by wrappers), which still said
  `AUTOMATIC_CAPTURE_READY` on 2026-10-10 while the variables said `NOT_READY`;
- a launchd plist and a separate "controller" automation that was found disabled
  (comment 6033390983).

`AUTOMATION_CONTRACT.json` in the repo has `activation_state`, `t_auto`,
`frozen_stack_command`, `ground_truth_command` and `launchd_or_scheduler` all
`null`, and there is no runbook or script that performs activation. The last two
days were spent on a denied `mkdir` and a stale JSON file.

Proposal: one activation manifest, versioned in the experiment root, that the
workflow, daemon, watcher and stack all read; one `activate`/`deactivate` script
that writes the 8 repository variables from that manifest and reads them back; a
single capture workflow published once and reused by the 7 other repos. The
manifest, not a human packet, is the source of truth for T_auto.

## 3. A sizing problem that will surface after the pipeline is fixed

- Of the 100 captured tasks, 18 reached `CLOSED_WITH_MERGED_PR` with a non-empty
  changed-file list (comment 6071272894). The quality and localization gates
  are only meaningful on those.
- Arrival rate is ~40 issues/day across the 8 repos, so the 100-task natural-mix
  stop is reached in roughly 3 days of collection.
- Issue lifetimes (closed issues, all repos): median 107 min, 25th percentile 19
  min, 32% closed within 30 min, 26% of all issues still open. A short-lived
  issue competes with a 25–72 s D0 run and an 1800 s strong-Online budget for
  the "provider start before terminal" window; the 1 s watcher narrows but does
  not remove that race.

At 18% useful-ground-truth yield, "56 scored tasks" and "24 DM1-applicable
tasks" need on the order of 300 admitted tasks, but the stop triggers at 100.
The contract as written will most likely terminate in
`INSUFFICIENT_NATURAL_STRATUM_COVERAGE` even with a perfect pipeline.

Proposal: define the primary denominator as tasks with merged-PR ground truth,
express the stop in that unit (or lengthen the natural-mix window), and state
the expected confidence interval at the chosen N up front.

## 4. Recommended order of decisions

1. Rule on 2.1 (immutable runtime artifact, decoupled from `main`). This alone
   removes the V6/V7/V10/V11 restart loop. Without it nothing else helps.
2. Rule on 2.2 (per-task fail-close) and write it into the contract.
3. Rule on 2.3 (exclude campaign meta-work from the denominator).
4. Collapse activation state to one manifest and one script (2.5), publish the
   capture workflow once.
5. Add the DM1-reaching readiness control (2.4).
6. Re-size the cohort target against observed yield (section 3).

Only then open V11. The readiness run for V11 under the current design would
likely pass and then be voided again by the next dispatcher commit.

## 5. Evidence index

- Issue #1216 body and comments 5901254036 … 6094518130 (44 comments).
- Generation timeline: comments 5921338283, 5944577912, 5985023370, 6031838345,
  6036136679, 6094518130.
- Keyword-gate defect and D0 dry-run: comment 6071272894.
- Activation/readiness code: `.github/workflows/hybrid-replication-capture.yml`
  (gate at the `AUTOMATIC_CAPTURE_READY + T_auto` check),
  `scripts/ops/hybrid_replication_daemon.py` (`_evaluate_automatic_capture_readiness`),
  `nexus/research/hybrid_replication_live.py` (`_load_binding`, generation constant),
  `docs/research/hybrid_replication_v2/AUTOMATION_CONTRACT.json`.
- Main churn: `git log origin/main --merges --since=2026-09-29`, and
  `git log -- scripts/ops/nexus-agy-dispatch` (5 commits on 2026-10-10).
- Workload statistics: GitHub issues API, 8 repositories, created_at >= T0,
  446 issues, computed 2026-10-11.
