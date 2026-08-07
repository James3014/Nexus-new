# Task Card: OPENWIKI-INTEGRATION-PILOT-01

artifact_authority: current
task_id: `OPENWIKI-INTEGRATION-PILOT-01`
owner: James Chen
status: ACTIVE
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Create the first governed OpenWiki canonical-integration pilot scaffold without integrating generated documentation. Add only: (1) .openwikiignore with Nexus-specific read-boundary exclusions including nexus_wiki_vault/, root/file symlink aliases and runtime/generated noise; (2) openwiki/INSTRUCTIONS.md with the V3 five-axis classification contract separating implementation_status, wiring_status, runtime_surfaces, authority_roles, and evidence_basis/claim_ceiling, preserving derived_non_authoritative authority and CapabilityPlanner/HybridRouteDecision route authority; (3) .github/workflows/openwiki-update.yml as a manual-only workflow_dispatch pilot pinned to openwiki@0.3.1, telemetry disabled, Gemini AI Studio via the repository's existing GEMINI_API_KEY secret convention, no schedule, no repository write permission, no commit/push/PR, and no generated Wiki integration. The workflow may generate OpenWiki output only as an ephemeral artifact, must restore AGENTS.md, CLAUDE.md, and its own workflow file to HEAD after generation, must fail closed if any repository path outside openwiki/ changes, and must never modify nexus_wiki_vault/. Do not run OpenWiki against canonical during implementation. Do not commit generated Wiki pages. AUTO_CHAIN=false. No approval, integration, push, cleanup, production/public claim, or successor task execution.

## Allowed files

- `.openwikiignore`
- `openwiki/INSTRUCTIONS.md`
- `.github/workflows/openwiki-update.yml`

## Verification commands

```bash
git diff --check
python3 -c "from pathlib import Path; p=Path('.github/workflows/openwiki-update.yml').read_text(); required=['workflow_dispatch:','openwiki@0.3.1','OPENWIKI_TELEMETRY_DISABLED','GEMINI_API_KEY','AGENTS.md','CLAUDE.md']; assert all(x in p for x in required); assert 'schedule:' not in p; assert 'pull-requests: write' not in p; assert 'contents: write' not in p"
python3 -c "from pathlib import Path; p=Path('openwiki/INSTRUCTIONS.md').read_text(); required=['implementation_status','wiring_status','runtime_surfaces','authority_roles','evidence_basis','claim_ceiling','derived_non_authoritative','CapabilityPlanner','HybridRouteDecision']; assert all(x in p for x in required)"
python3 -c "from pathlib import Path; p=Path('.openwikiignore').read_text(); required=['nexus_wiki_vault/','nexus-evolve','MUSE_PROTO.md','.antigravitycli/','.pyre/','docs/incidents/LATEST_RCA.md']; assert all(x in p for x in required)"
```

## Exit criteria

Owner review of the exact scoped commit.

## Block classification

Unverifiable or out-of-scope mutation is a HARD_BLOCK.
