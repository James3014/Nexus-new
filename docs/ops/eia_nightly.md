# EIA nightly scheduler (M4)

`scripts/ops/eia_nightly.py` runs External Intelligence Automation (EIA) unattended overnight on
the M4 host. The ChatGPT web transport is cleanest in the early morning. The scheduler never
merges anything. Card PRs and candidate PRs both go to the merge-queue session through
`coord`, and that session reviews and merges them under its normal rules.

## Queue an Issue

1. Add the label `eia:queue`.
2. Put exactly one fenced JSON block in the Issue body:

````
```eia-task
{
  "difficulty": "easy",
  "allowed_files": ["nexus/foo/bar.py", "tests/foo/test_bar.py"],
  "verification": ["python -m pytest -q tests/foo/test_bar.py"],
  "capability_ids": ["nexus_core_domain_runtime"],
  "summary": "One line that the Task Card objective quotes."
}
```
````

The block's fields:

- `difficulty`: `easy`, `medium` or `hard`. Hard Issues are not scheduled.
- `allowed_files`: literal repo paths. Globs are not allowed, and neither are `tasks/` or `.github/`.
- `verification`: commands that start with `python` or `python3`. The scheduler rewrites the
  interpreter to the EIA daemon's venv python (`<daemon checkout>/.venv/bin/python`), because
  the daemon's PATH resolves `python3` to Homebrew python, which has no Nexus dependencies.
  Closure runs verifiers in a clean candidate checkout, with `$NEXUS_BASE_SHA` and
  `$NEXUS_CANDIDATE_SHA` set.
- `capability_ids`: ids from `docs/agents/CAPABILITY_DISCOVERY_INDEX.v1.json`.
- `capability_disposition` (optional): defaults to `EXTEND_EXISTING`.

An Issue that is malformed or hard gets one comment and the `eia:needs-template` label. Fix
the block, then remove that label.

## Nightly flow

| When | Command | What it does |
| --- | --- | --- |
| 16:00, re-checked at 20:00 | `prepare` | Takes up to 4 queued Issues. It renders `tasks/eia-nightly/<night>/issue-<N>.md` and validates each card with the daemon's own validators (`parse_issue_contract`, `_task_card`, `_validate_task_card_authority`, Core lane and capability checks). It opens one card PR, using the KEEP_OPEN tracking Issue "EIA nightly task cards", and sends READY to merge-queue. Later runs record the merge sha and each card's blob id. |
| 23:30 | `start` | If the card PR has not merged, it skips the night and tells coordinator. Otherwise it starts a bounded `caffeinate -dimsu`, opens Chrome and the `ibase` profile window when the Browser Bridge is not connected, bootstraps or kickstarts `com.nexus.external-intelligence`, and runs `eia-healthcheck`. |
| every 5 min | `dispatch` | Arms one Issue at a time before 06:00: it appends the contract to the body (the original text is kept), reads it back, and adds `nexus:external-intelligence` last. It then follows the daemon state file for that exact identity. |
| 07:30, safety net at 09:05 | `stop` | Arms nothing new. A running Issue may finish until 09:00. Then it runs `launchctl bootout` on the daemon (which stays off during the day), kills caffeinate, writes `<night>-report.md`, sends the report to coordinator and posts a macOS notification. |
| any time | `status` | Prints the night state. |

The state lives in `~/Workspace/nexus-self-hosted-state/eia-nightly/`: one `<YYYYMMDD>.json`
per night (a night runs from noon to noon), a `.lock`, and an optional `PAUSE` file. While
`PAUSE` exists, `prepare`, `start` and `dispatch` do nothing; `stop` still runs.

## Outcomes

The daemon writes its result to
`<state_root>/automation/James3014_Nexus-new/issue-<N>-<identity>.json`. The identity is
recomputed with `IssueWorkItem.identity_hash` from the contract that was armed. The scheduler
acts on that result as follows:

- **COMPLETE** (after the daemon's own publication comment, or a 15 min grace): the scheduler
  re-checks the receipt. It requires `WHOLE_TASK_PASS`, a matching task id, and an acceptance
  packet that sits under the EIA state root and matches its sha256 and the candidate. The
  commit must exist in the daemon checkout, descend from the contract's `main_sha`, and change
  only allowed files, with no deletions. The scheduler then pushes that exact commit as
  `eia/<N>-<revision>` with the bot credential, opens a PR (`Closes #N`, Core marker, CLOSE
  intent, receipt summary) and sends READY to merge-queue. Labels become `eia:candidate-pr`;
  `eia:queue` and `nexus:external-intelligence` are removed. A GitHub error is retried on the
  next tick, and a receipt that fails these checks is escalated.
- **Infra failure:** a reconcile-only state, an `OPENCLI_*`, transport or `OUTCOME_UNKNOWN`
  error, an exception raised before anything was dispatched, or more than 150 min in flight.
  The scheduler removes the label and re-arms the Issue with a new revision and unit id, at
  most 2 retries and only before 06:00. After that it adds `eia:escalate`.
- **Model failure and anything unrecognised:** `*_REPAIR_REQUIRED`, `REPAIR_BUDGET_EXHAUSTED`,
  `SCOPE_DELTA_REQUIRED`, worker blocked, verification or closure failure, or an unknown
  state. The scheduler adds `eia:escalate`, posts one comment with the reason, and removes
  `nexus:external-intelligence`.

`RECONCILIATION_REQUIRED` with prior state `INTELLIGENCE_DISPATCHING` or `FANOUT_DISPATCHING`
is left alone, because the daemon resumes it by itself.

## Install (operator only)

Fill in the four templates `scripts/ops/com.nexus.eia-nightly-{prepare,start,dispatch,stop}.plist.template`
and load them with `launchctl bootstrap gui/$(id -u) <plist>`. The daemon checkout must contain
this script. GitHub writes use the bot wrapper `~/.config/nexus-agent-bot/bin/gh`, and pushes use
`nexus-agent-git-credential`. The scheduler never falls back to the owner's identity.
