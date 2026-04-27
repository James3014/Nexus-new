# External Sources Policy

Status: local-research policy

## Decision

`docs/external/` is reserved for local external research snapshots and is ignored by git.

## Rationale

External snapshots can contain nested `.git` directories, package locks, generated assets, binary media, third-party licenses, and unrelated project history. Tracking them directly would make Nexus diffs noisy and could blur product evidence with source-material caches.

## Workflow

1. Keep raw external repos or bulky source captures under `docs/external/`.
2. Distill useful findings into tracked Nexus docs, plans, tests, or ADRs.
3. Link the source name and retrieval date in the distilled document.
4. Do not commit nested external repositories or binary media unless a specific Nexus artifact requires them and licensing is reviewed.

## Current Local Snapshots

- `docs/external/GitNexus/`
- `docs/external/RLM/`
- `docs/external/agent-sprite-forge/`
- `docs/external/user_inputs/`
