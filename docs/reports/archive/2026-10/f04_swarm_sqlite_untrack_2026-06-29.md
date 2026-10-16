# F-04A Swarm SQLite DB Untrack

**Status:** `F04A_SWARM_SQLITE_UNTRACKED`

**Date:** 2026-06-29

## Summary

Untracked 49 swarm SQLite DB files from git while preserving local files.

## Files Changed

| File | Change |
|---|---|
| `.gitignore` | Added `nexus_swarm/*.db`, `*.db`, `*.sqlite`, `*.sqlite3` |
| 49 DB files | Removed from git index via `git rm --cached` |

## Before/After

| Metric | Before | After |
|---|---|---|
| Tracked DB files | 49 | 0 |
| Physical DB files | 49 | 49 (preserved) |

## Commands Run

```bash
git ls-files '*.db' '*.sqlite' '*.sqlite3'
git rm --cached .nexus-swarm-*/swarmtasks.db nexus_swarm/swarm_tasks.db
find . -type f \( -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' \) -print | head
```

## Scope Statement

- Only git index modified
- No physical files deleted
- `.gitignore` updated to prevent re-adding
