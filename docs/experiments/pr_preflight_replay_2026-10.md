# nexus-pr-preflight replay on historical failing PRs (2026-10)

Issue: #1916. Tool: `scripts/ops/nexus-pr-preflight` (`scripts/ops/pr_preflight.py`).

## Result

The tool flagged the CI failure cause on **10 of 10** historical failing PRs. The
acceptance target was at least 8 of 10.

## Method

- Sample: the 90-PR sample #1701–#1893 from #1916. Failed-job logs were
  classified by the exact error line, ignoring echoed script text.
- Selection: ten PRs, chosen before running the tool so that every failure
  class preflight covers appears at least once:
  - missing `NEXUS_CORE_ISSUE` ×2
  - Issue evidence marker
  - Issue not open
  - executor Git identity ×2
  - dependency-contract drift
  - silent Trusted-controller (lane gate) failure
  - Ruff regression
  - Pyright regression
- State replayed, all read-only:
  - Head: the failing job's `head_sha`, from the Actions jobs API.
  - Base:
    - Trusted-controller jobs: the `workflow_sha` fetched in the job log.
    - Runs that report a PR base: `pull_requests[].base.sha`.
    - Otherwise: the first-parent `main` commit before the job started. This is an
      approximation.
  - PR body: the GraphQL `userContentEdits` version current at job start.
  - Issue body and state: the same, plus the close/reopen timeline.
- Run:
  - Repository: a blobless scratch clone with `origin/main` set to the replayed
    base and a detached worktree at the head.
  - Command: `nexus-pr-preflight --no-fetch --body-file … --issue-json …
    --pr-number N --json`.
  - Issue marker: `nexus-certify markers` from the local nexus-core checkout.
  - Static gates: this branch's `uv sync --frozen --all-groups --all-extras`
    venv (Python 3.12).
- Scoring: "flagged" means the check that maps to the failing CI job returned
  FAIL with the matching cause.

## Replay table

| PR | Failing CI job | CI cause | Head | Base (source) | Preflight check | Preflight result | Flagged | All preflight FAILs |
|---|---|---|---|---|---|---|---|---|
| 1712 | Nexus Core issue run | PR body has no `NEXUS_CORE_ISSUE` | 584d8f6a1182 | d565535fb99e (main at job start) | bindings | FAIL PR_MISSING_CORE_ISSUE_BINDING | yes | bindings, merge_lane (missing), freshness, git_identity |
| 1808 | Nexus Core issue run | PR body has no `NEXUS_CORE_ISSUE` | f77f4d747af3 | 4dbac7875071 (run PR base) | bindings | FAIL PR_MISSING_CORE_ISSUE_BINDING | yes | bindings, merge_lane (missing), freshness, dependency_contract, git_identity, static_ruff |
| 1745 | Nexus Core issue run | Issue lacks evidence marker | a663c3f2a4a9 | 2e5c58546e56 (main at job start) | issue | FAIL ISSUE_MISSING_EVIDENCE_UNIVERSE | yes | issue |
| 1718 | Nexus Core issue run | ISSUE_NOT_OPEN (#1362) | 1422cd5543dc | f4d23548ec19 (main at job start) | issue | FAIL ISSUE_NOT_OPEN | yes | issue, static_ruff |
| 1716 | Unprivileged executor | Git identity mismatch | 16a8a35b6a49 | 7a408fd4718d (main at job start) | git_identity | FAIL EXECUTOR_GIT_IDENTITY_MISMATCH | yes | freshness, git_identity |
| 1834 | Unprivileged executor | Git identity mismatch | 6f79cdce8df0 | 0444f823071c (main at job start) | git_identity | FAIL EXECUTOR_GIT_IDENTITY_MISMATCH | yes | freshness, git_identity |
| 1730 | Trusted controller | Dependency contract drift | 9b3573e27345 | cf27a0367032 (log workflow_sha) | dependency_contract | FAIL DEPENDENCY_CONTRACT_DRIFT | yes | bindings, merge_lane (missing), dependency_contract |
| 1722 | Trusted controller | Silent exit 1 (no diagnostic) | 98b36a91b1a6 | 9281d6e8e5a0 (log workflow_sha) | merge_lane | FAIL REJECTED_CLOSING_KEYWORD_FOR_KEEP_OPEN | yes | bindings, merge_lane |
| 1774 | Exact-base Ruff | Opaque `exit 1` | 5641a12a438d | db0597dc6ce9 (main at job start) | static_ruff | FAIL NEW_REGRESSION | yes | issue, static_ruff |
| 1838 | Exact-base Pyright | Opaque `exit 1` | 68338c7d9d0f | 1d80602f07d2 (main at job start) | static_pyright | FAIL NEW_REGRESSION | yes | static_pyright |

### Findings that CI did not print

- **#1722:** the CI log ends at `exit code 1`. Preflight names the reason:
  `REJECTED_CLOSING_KEYWORD_FOR_KEEP_OPEN`. The prose contained `close #1384`,
  and #1384 was declared `KEEP_OPEN`.
- **#1774:** the new Ruff finding is
  `scripts/ops/hybrid_replication_activation.py:195` "File would be reformatted".
- **#1838:** the new Pyright finding is
  `scripts/ops/check_golden_finding_owners.py:178` `reportOptionalMemberAccess`
  (`"splitlines" is not a known attribute of "None"`).
- **#1718:** the new Ruff finding is `tests/services/test_agy_dispatch.py:5680`
  "File would be reformatted". The same head also failed the Ruff gate in CI.

### Extra FAILs, cross-checked against CI at the same head

Most extra FAILs match a CI job that also failed at that head. #1712, for
example, also failed the executor and the Trusted controller.

Two extra FAILs on #1808 had no matching CI failure:

- `git_identity`
- `static_ruff` (13 findings)

At the replayed base, #1808's head was 36 commits behind main. The CI runs that
passed these jobs had used an older base, so the difference comes from the
base approximation. The tool now marks a static FAIL on a head that is behind its
base with "merge origin/main first".

## What preflight cannot cover

- **Lane authority:** preflight reports whether a `NEXUS_MERGE_LANE_V1` block is
  present and whether it passes the trusted lane gate. It never creates a
  binding or hash. A GOVERNED-to-DIRECT rebind needs the Owner as the event
  sender, so that path is reported as SKIP.
- **Impact gate:**
  - The pytest impact gate ("untrustworthy exact-base comparison" or new test
    failures) is not replayed.
  - The repo-wide published-ref secret audit is not covered.
  - Timeouts are not covered.
- **Core issue-gate verdict:** preflight checks only the Issue preconditions
  (open, evidence marker) and ancestry. It does not check
  `REPOSITORY_VERIFICATION_NOT_VERIFIED` or receipt binding; run
  `scripts/ops/nexus-core-issue-check-local` for those.
- **Tool versions:** static results use the local venv's tools. These match CI
  only when `uv.lock` matches.
- **Base approximation:** for Core-gate and static jobs on `pull_request_target`
  runs, the replayed base is approximated from the job start time.
