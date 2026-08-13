# Task Card: standing coordinator authority

- status: SUPERSEDED_BY_OWNER_MERGE_QUEUE_AUTHORITY
- base_sha: 0b97df90bbebbd90d0811d46ba73c47e46fe1878
- authority: direct Owner request, 2026-08-11
- AUTO_CHAIN: false

## Standing Grant Receipt

- grant_id: OWNER_STANDING_COORDINATOR_20260811_NEXUS_READY_ISSUES
- owner_identity: James3014 / James Chen
- coordinator_audience: primary Codex coordinator in source thread
- source_thread: 019fe60d-686d-7bd3-83b2-260ae501f6d5
- repository: James3014/Nexus-new
- issued_at: 2026-08-11T21:06:05+07:00
- goal_id: NEXUS_ALL_ISSUES_COMPLETION_20260811
- goal_scope: finish every effective Ready Issue and open PR required for verified repository closure, using bounded parallel workers and coordinator integration
- issue_eligibility: effective Issue contract is Ready with frozen exact scope and claim ceiling
- allowed_actions: create/commit bounded card; update issue branch; test; push; open PR; prepare MERGE_INTENT; non-authorizing readback/reconciliation only after a separately slot-authorized merge
- expires_when: Owner revokes or narrows the grant, or the active Goal is verified terminal
- revocation_rule: any later Owner instruction that revokes or narrows scope takes immediate precedence
- superseded_merge_authority: Owner decision recorded in Issue #163; protected merge now requires fresh exact PR/head/base-bound MERGE_SLOT_GRANTED
- exclusions: Issue #143 and its mutation files; direct main push; force-push; ref deletion; worker self-approval/merge; local runtime/lifecycle approval; release; production/public claims

## Objective

Historical objective, narrowed by the later Issue #163 Owner decision: the
standing grant remains sufficient for bounded pre-merge work, while every
protected merge requires a fresh exact PR/head/base-bound Owner slot.

## Allowed Files

1. `AGENTS.md`
2. `docs/agents/TASK_EXECUTION_CONTRACT.md`
3. This campaign's `INDEX.md` and active card

## Forbidden Scope

- direct push, force-push, or deletion of protected `main`
- delegated-worker self-approval or self-merge
- ruleset/check bypass
- route, Workforce, lifecycle, runtime, release, or production authority
- weakening exact-head, independent-review, scope, deletion, or readback gates

## Verification

1. `git diff --check`
2. Search both authority documents for contradictory per-action approval text
3. Confirm standing authority applies only to the primary coordinator
4. Confirm delegated workers remain unable to approve/merge their own Candidate
5. Confirm protected merges require fresh Owner MERGE_SLOT_GRANTED, current base, exact-head CAS, independent review, and terminal required checks
6. Confirm Task Card creation is limited to already Ready Issues with frozen scope and `AUTO_CHAIN=false`

## Exit Criteria

- The four-file governance diff is committed and pushed on `codex/standing-owner-autonomy`.
- Required CI and an independent review pass before protected merge.
- No runtime/lifecycle approval or production claim is implied.

## Maximum Supportable Claim

The primary coordinator has documented standing collaboration authorization
for bounded pre-merge Ready-Issue execution. Protected PR merge is excluded and
requires a fresh Owner MERGE_SLOT_GRANTED decision. Delegated workers remain
non-approving Candidate producers.
