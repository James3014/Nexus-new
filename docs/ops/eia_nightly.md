# EIA nightly scheduler (M4)

`scripts/ops/eia_nightly.py` runs External Intelligence Automation (EIA) unattended overnight on
the M4 host. The ChatGPT web transport is cleanest in the early morning. The scheduler never
merges anything. Card PRs and candidate PRs both go to the merge-queue session through
`coord`, and that session reviews and merges them under its normal rules.

## Queue an Issue

1. Add the label `eia:queue`. The repository is public, so the scheduler only acts when the
   Issue author, the latest `eia:queue` label event, and every title or body edit after that
   event all belong to a trusted actor. The default trusted actors are `James3014` and
   `james3014-nexus-agent[bot]`; override them with `--trusted-actors`.
   - Timeline (REST) logins are compared exactly.
   - A GraphQL actor counts as the bot only when `__typename == "Bot"`.
   - An incomplete edit history (`totalCount` larger than the nodes returned) is refused.

   An Issue that fails any of these checks is left completely untouched.
2. Put exactly one fenced JSON block in the Issue body:

````
```eia-task
{
  "difficulty": "easy",
  "allowed_files": ["nexus/foo/bar.py", "tests/foo/test_bar.py"],
  "verification": ["python3 -m pytest -q tests/foo/test_bar.py"],
  "capability_ids": ["nexus_core_domain_runtime"],
  "summary": "One line that the Task Card objective quotes."
}
```
````

The block's fields:

- `difficulty`: `easy`, `medium` or `hard`. Hard Issues are not scheduled.
- `allowed_files`: at most 10 literal, normalised, repo-relative paths. Globs, absolute paths,
  and any path component that starts with `.` are rejected. At `origin/main`, each path must be a regular file
  or a new file in an existing directory, with no symlink anywhere on the path. Protected paths
  are refused: `.github/`, `.nexus-core/`, `.gitmodules`, `docs/governance/`, `docs/agents/`,
  `docs/testing/test_impact_map.md`, `tasks/`, `pyproject.toml`, `uv.lock`, bootstrap files
  (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `MUSE_PROTO.md`), `nexus/services/external_intelligence*`,
  `scripts/ops/external_intelligence*`, `scripts/ops/trusted_*`, `pytest.ini`, `setup.cfg`,
  `tox.ini`, `policy/`, `Makefile`, and this scheduler with its templates and tests. Also
  refused anywhere in the tree: `conftest.py`, `sitecustomize.py`,
  `governance_baseline_manifest*.json`, `Taskfile*` and `.pre-commit-config*`. All of these
  comparisons ignore case. Paths are checked again against the `main` that each attempt binds.
- `verification`: only two forms are accepted. Any other option, shell form or path is
  rejected.
  - `python3 -m pytest [-q] [-p no:cacheprovider] tests/<file>.py[::test] ...`, where each
    target must exist at main or be an allowed file (`python` becomes `python3`).
  - The exact diff check `sh -c 'git diff --check "$NEXUS_BASE_SHA" "$NEXUS_CANDIDATE_SHA"'`.

  Closure runs these in a clean candidate checkout. The scheduler itself never runs them and
  never uses a shell.
- `capability_ids` (required): ids from `docs/agents/CAPABILITY_DISCOVERY_INDEX.v1.json`.
  The Core validator requires donor ids for the mutating dispositions, and
  `NEW_CAPABILITY_JUSTIFIED` would be a false claim, so there is no safe default. The template
  comment lists the valid ids.
- `capability_disposition` (optional): defaults to `EXTEND_EXISTING`.

An Issue that is malformed or hard gets one comment and the `eia:needs-template` label. Fix
the block, then remove that label. After 3 attempted nights without a candidate PR (counted
in `issues.json`), an Issue gets `eia:escalate` and is no longer scheduled.

## Deployment prerequisite: `python3` under the daemon PATH

Cards use plain `python3`. Closure runs verifiers with the daemon's environment, so the
operator must put the Nexus venv `bin` first on `PATH` in
`~/Library/LaunchAgents/com.nexus.external-intelligence.plist`. `start` checks this by running
`env -i PATH=<plist PATH> python3 -c 'import nexus, pytest'` in the daemon checkout. If the
check fails, the night is `START_FAILED` and nothing is armed.

## Nightly flow

| When | Command | What it does |
| --- | --- | --- |
| 16:00, re-checked at 20:00 | `prepare` | Takes up to 4 queued Issues. It renders `tasks/eia-nightly/<night>/issue-<N>.md` and validates each card with the daemon's own validators (`parse_issue_contract`, `_task_card`, `_validate_task_card_authority`, Core lane and capability checks). It opens one card PR, using the KEEP_OPEN tracking Issue "EIA nightly task cards", and sends READY to merge-queue. Later runs record the merge sha and each card's blob id. |
| 23:30 | `start` | If the card PR has not merged, it skips the night and tells coordinator. Otherwise it starts a bounded `caffeinate -dimsu`, opens Chrome and the `ibase` profile window when the Browser Bridge is not connected, bootstraps or kickstarts `com.nexus.external-intelligence`, and runs `eia-healthcheck`. |
| every 5 min | `dispatch` | Arms one Issue at a time before 06:00. It re-checks trust, appends the contract to the body (the original text is kept), confirms a byte-identical read-back, and adds `nexus:external-intelligence` last. It then follows the daemon state file for that exact identity. On every tick it re-reads the Issue, and disarms and escalates if the body changed or `eia:queue` was removed. |
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
  commit must be exactly one commit whose only parent is the contract's `main_sha`, and its
  tree must match. `git diff --raw` may show only added or modified regular files (modes
  100644/100755) that are in `allowed_files`: no deletions, type changes, symlinks or
  gitlinks. The whole-task verification record must sit under the state root. Its
  content-derived `verification_id` is recomputed with the closure's own
  `_sha256(_canonical_json(...))` and must equal both the record's own id and the packet's
  `whole_task_verification_id`. The closure's own gate (`_integrity_passed`) must hold:
  the complete `INTEGRITY_CHECK_IDS` set is present and passed, `integrity_status` is PASS,
  and `failed_integrity_check_ids` is empty. Records written before the integrity checks
  existed are refused. Every declared verifier must also pass for that commit. `candidate_tree` must be 40 hex characters. Gate, claim ceiling and
  closure run id must match `^[A-Za-z0-9_.:-]{1,120}$`. Worker provider and model may contain
  one `/` (the real value is `opencli_chatgpt/advanced`). Only these validated
  values ever reach the PR body or coord messages. A branch lookup only considers PRs
  that are not cross-repository and whose head owner is `James3014`; such a PR is reused only
  if it is OPEN, based on `main`, and at that exact head. A newly created PR is read back the
  same way before READY is sent. If the new PR is not visible yet, the tick is retried, and
  the next tick finds the PR by branch. A different PR, base or head is refused. The PR number is saved before labels change. A failed or
  partial label edit leaves the Issue `CANDIDATE_PR` with labels pending (never `WITHDRAWN`),
  and every tick retries the labels. The scheduler writes no local refs: a raw ref writer
  would be a second candidate-integration primitive (see
  `tests/architecture/test_effect_owner_uniqueness.py`). Both commits are pushed the same
  night, well inside git's two-week prune window. If a commit is gone anyway before its
  push succeeded, the scheduler recovers as follows. An unpushed card commit is rebuilt
  deterministically from the recorded base and card inputs (fixed commit dates); if the base
  is gone too, that night's `prepare` starts over. A missing candidate commit is an infra
  failure, so the normal retry or escalation applies, and no other SHA is ever substituted. The scheduler then pushes that exact commit as
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

A BLOCKED identity whose failure came before any dispatch (`semantic_dispatched: false`) is
re-run by the daemon on every poll. The re-run does not resend to ChatGPT: the sidecar keys
attempts by `request_sha256` and raises `INTELLIGENCE_REPLAY_FORBIDDEN` for a FAILED attempt,
or reconciles an `OUTCOME_UNKNOWN` one. The request hash covers the Issue title and body,
which is why the scheduler disarms on any body change. The hash also covers the worker binding
chosen by the canonical planner, so a re-run that binds a different worker would be a new
request. To keep that window short, `dispatch` watches the local state file every 20 s for up
to 270 s per invocation (it makes no GitHub calls while watching). It disarms within seconds
of a terminal result.

Each Issue is isolated: consecutive errors, including JSON and file errors, are counted
per Issue and per step, and a success resets only that step's count, and the Issue escalates after 3 errors
without stalling the others. `stop` writes a `STOP_REQUESTED` file before it takes
the lock. A watching `dispatch` sees the file and releases the lock. `stop` then waits up to
about 5.5 minutes for the lock and exits with 75 if it still cannot get it; the 09:05 run
retries. If `launchctl bootout` fails, the night is not finalised: it is reported once, and
`dispatch`, the 09:05 `stop`, and the next `prepare` or `start` all retry it.

`RECONCILIATION_REQUIRED` with prior state `INTELLIGENCE_DISPATCHING` or `FANOUT_DISPATCHING`
is left alone, because the daemon resumes it by itself.

Every launchd call goes through `external_intelligence_service`. Each call
is bounded by that module's 20 s timeout; a timeout or OS error becomes exit 124, and the
next tick retries. `start` records `BOOTSTRAP_FAILED` or `KICKSTART_FAILED`, depending on
which step failed. On a failed or timed-out bootout, `stop` still disarms in-flight Issues,
records `BOOTOUT_FAILED`, and retries. An in-flight Issue stays `HARD_STOPPING`
(`disarm_pending`) until removal of `nexus:external-intelligence` is confirmed. Every tick
retries it, and the night is never `FINISHED` while any disarm is pending. A candidate-PR
Issue whose label swap is still pending counts as a pending disarm too. The next
`prepare` or `start` finishes a previous night left in that state.

## Install (operator only)

Fill in the four templates `scripts/ops/com.nexus.eia-nightly-{prepare,start,dispatch,stop}.plist.template`.
Before loading them, run `mkdir -p ~/Workspace/nexus-self-hosted-state/eia-nightly` (launchd does not
create log directories), and load them with `launchctl bootstrap gui/$(id -u) <plist>`. The daemon checkout must contain
this script. GitHub writes use the bot wrapper `~/.config/nexus-agent-bot/bin/gh`, and pushes use
`nexus-agent-git-credential`. The scheduler never falls back to the owner's identity.
