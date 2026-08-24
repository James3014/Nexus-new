# TASK-FAST-START-V2-G9-G11

Status: ACTIVE
AUTO_CHAIN=false

## Objective
Implement and prove Fast Start v2 G9-G11 without changing Nexus product/runtime authority:
1. G9: deterministic read-only simulator for typed inputs, impact mapping, reconcile action/frontier classification, and blocked zero-retrieval accounting.
2. G10: shadow-only GitHub Actions canary that runs the simulator/tests and emits non-authoritative evidence; it must not update Issue #549 or execute untrusted PR code.
3. G11: after exact-head independent acceptance and merge gates, cut over the existing ChatGPT Fast Start Cache Sweep/Guard configuration so v2 becomes the primary refresh policy while preserving v1 rollback.

## Authority
Current Owner request in this conversation authorizes this bounded governed milestone. This card grants implementation on the issue branch only; it grants no self-approval, merge without fresh exact-head gates, runtime, release, production, route, Workforce, claim, or autonomous worker-dispatch authority.

## Allowed repository files
- `scripts/ops/fast_start_v2.py`
- `tests/ops/test_fast_start_v2.py`
- `.github/workflows/fast-start-v2-shadow.yml`
- `tasks/github-fast-start-v2-g9-g11-20260824/00-fast-start-v2-g9-g11.md`
- `tasks/github-fast-start-v2-g9-g11-20260824/INDEX.md`

Maximum repository changed files: 5.

## Forbidden scope
- No product source changes.
- No Nexus route/Planner/Workforce/lifecycle/claim/approval/integration authority changes.
- No changes to Issue #549 during G9/G10.
- No workflow may checkout or execute untrusted pull-request head code under elevated permissions.
- No secrets.
- No direct push to `main`; no force push; no branch deletion.

## G9 verification
- Deterministic reference cases for #129/#92/#419/#526/#398.
- Synthetic event cases: irrelevant main path, blocker head movement, blocker terminal without unlock witness, contract change while blocked, host-fact unavailable, duplicate impact edges, registry self-event suppression.
- BLOCKED/HOST cases must report source-body reads = 0 and test-body reads = 0.
- Malformed/unknown input fails closed.

## G10 verification
- Shadow workflow has read-only repository permissions.
- It runs only trusted default-branch/PR-candidate simulator and tests; no canonical registry mutation.
- Exact PR-head workflow run must be green before G11.
- Shadow result must not produce a false READY for current blocked/host entries.

## G11 cutover
Only after independent exact-head review and terminal required checks:
- merge by exact-head/CAS bounded path;
- read back `main` and merged revision;
- preserve #549 as sole advisory registry;
- update existing Fast Start Cache Sweep prompt to consume v2 typed/impact/fingerprint/frontier semantics and remain the sole canonical body writer;
- update Daily Guard to observer/anti-entropy only with no direct #549 repair;
- keep hourly scheduled sweep as fallback latency ceiling; do not claim native instant GitHub issue-event delivery unless separately proven;
- capture rollback text for restoring v1 broad sweep/guard.

## Exit criteria
G9 simulator/tests proven; G10 shadow run proven on exact candidate; G11 merged/cutover/readback proven. If exact workflow execution cannot be observed, stop at G10 and do not claim G11 complete.
