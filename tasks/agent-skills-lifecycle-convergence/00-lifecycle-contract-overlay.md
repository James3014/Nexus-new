# Task Card: agent-skills-lifecycle-contract-overlay

artifact_authority: current
owner: James Chen
status: VERIFIED_PENDING_OWNER_REVIEW
task_id: agent-skills-lifecycle-contract-overlay
commit_forbidden: true
owner_external_path_authorization_required: true
AUTO_CHAIN: false

## Objective

Update exactly seven machine-local Skills to consume the P6/P7 lifecycle
contract and hand off one bounded next action without widening runtime or Git
authority.

## Allowed external files

- `/Users/jameschen/.agents/skills/nexus-current-state-audit/SKILL.md`
- `/Users/jameschen/.agents/skills/nexus-mcp-access-audit/SKILL.md`
- `/Users/jameschen/.agents/skills/nexus-mcp-task-executor/SKILL.md`
- `/Users/jameschen/.agents/skills/nexus-candidate-acceptance-audit/SKILL.md`
- `/Users/jameschen/.agents/skills/nexus-model-task-compiler/SKILL.md`
- `/Users/jameschen/.agents/skills/nexus-model-onboarding-calibration/SKILL.md`
- `/Users/jameschen/.agents/skills/nexus-handoff/SKILL.md`

## Allowed repository verifier

- `scripts/ops/verify_agent_skill_lifecycle_overlay.py`

## Forbidden scope

- Nexus runtime, MCP server, public tool manifest, provider policy, Git refs,
  protected branches, credentials, or any other `.agents/skills` file.
- Adding a `nexus-lifecycle-controller` Skill or second router.
- Claiming live GPT connector or Cline provider closure.

## Required overlay

Each Skill must preserve its existing purpose and add the same concise rules:

1. bind work to `task_id`, `attempt_id`, `action_id`, and
   `idempotency_key`;
2. freeze `tool_manifest_hash`, `full_tool_schema_hash`,
   `permission_policy_hash`, `lifecycle_revision`, and server instance before
   mutation or acceptance;
3. use typed public Gateway tools and the minimum profile (`OBSERVE`,
   `VERIFY`, `MUTATE_BOUNDED`, `CANDIDATE`, or `INTEGRATE`);
4. after timeout/disconnect/restart, reconcile durable state before retry;
5. preserve `UNKNOWN_REQUIRES_RECONCILE` and `uncertain_mutation` fail-closed;
6. emit exactly one valid `next_action`/`recommended_tool` and never invent a
   tool name;
7. keep approval, integration, push, cleanup, and production claims outside
   worker/implementer authority.

## Verification

```bash
python3 scripts/ops/verify_agent_skill_lifecycle_overlay.py
git status --short --branch
git diff --check
```

## Exit receipt

Record the seven external paths, bytes before/after, overlay marker, and
`repository_mutation: false`. The next gate is Campaign C memory/learning
lineage or the live `nexus01` P7 smoke, whichever the Owner selects.

## Verification receipt

- verifier: `scripts/ops/verify_agent_skill_lifecycle_overlay.py`
- result: `gate_passed: true`
- overlay markers: exactly one in each of the seven allowed Skills
- external paths changed: exactly the seven listed above
- repository mutation from Skill edits: `false`
- repository verifier mutation: `false`
- observed external byte counts: 7879, 5806, 7292, 5747, 8546, 12402, 4868
- forbidden second router token: absent
- claim ceiling: machine-local lifecycle contract overlay only; no live GPT
  connector, Cline provider, approval, integration, push, cleanup, or
  production closure is claimed
