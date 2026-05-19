# Nexus SF Skill Finalization V21 - 2026-05-19

## Status

- Skill pairing: FINALIZED
- Runtime overlay: FINALIZED
- Runtime update allowed: true for approved replacement only
- Public benchmark: HOLD

## Decisions

| Capability | Before | After / Kept | Token delta | Wall delta sec | Verdict |
|---|---|---|---:|---:|---|
| `registry_skills_sync` | `sf2-registry_skills_sync-route-fit-spec` | `github3-openai-skill-creator-safe-registry-sync` | -1338 | -12.3289 | `APPROVE_RUNTIME_REPLACEMENT` |
| `ultra_review` | `acceptance-evidence-failclosed` | `acceptance-evidence-failclosed` | 2287 | 3.9968 | `KEEP_CURRENT_SKILL` |

## Boundary

`ultra_review` challenger passed delivery but regressed mounted runtime cost, so current skill remains. Public benchmark remains separate.
