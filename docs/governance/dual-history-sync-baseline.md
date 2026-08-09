# Dual-History Synchronization Baseline

## Purpose and authority

This record is the updateable baseline for the intentionally separate local
runtime repository and sanitized GitHub collaboration repository. It is an
observation record, not a permanent policy and not permission to align the
repositories by rewriting history.

## Recorded observation — 2026-08-09

| Field | Value |
| --- | --- |
| Local runtime commit | `660ebb5f384fa688d5aa2b475599966dd1a73f42` |
| Sanitized GitHub collaboration commit | `4f6b959cc1564a75de3e1e706f2065ee30abb68` |
| Observation/sync date | 2026-08-09 |
| Repository pair | `/Users/jameschen/Workspace/nexus` and `James3014/Nexus-new` |
| Status | Updateable historical content/semantic baseline; histories intentionally remain separate |

## Verification basis

The local commit was read from the canonical checkout at task start using
`git rev-parse HEAD`. The sanitized commit was independently read from the
GitHub `main` ref using `git ls-remote` and matched the PR #3 base SHA. The pair
is retained as a dated reviewed content/semantic baseline for collaboration;
the SHA difference is expected and is not, by itself, evidence of missing
work.

Future updates must record the newly observed pair, date, and verification
basis after reviewing the semantic delta. Do not normal-merge, rebase, or
cherry-pick local runtime history into sanitized GitHub `main` merely to make
the SHAs equal, and do not restore sanitized secrets, runtime state, or
generated artifacts.
