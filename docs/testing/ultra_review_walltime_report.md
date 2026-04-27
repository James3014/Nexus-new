# Ultra Review Wall-Time Report

Date: 2026-04-28

## Scope

This report compares the Ultra Review sandbox mirror setup cost after P5:

- Old path: filtered `shutil.copytree` mirror.
- New path: `git worktree add --detach` plus diff apply and bounded untracked overlay.

The measurement used the same local Nexus repository and `/tmp` sandboxes. It did not run Gemini or benchmark tasks.

## Result

| Strategy | Trials | Average setup time |
| :--- | :---: | ---: |
| copytree mirror | 3 | 2.26s |
| git worktree mirror | 3 | 1.56s |

Measured improvement: 30.9% faster mirror setup.

## Raw Data

```json
{
  "copytree_sec": [2.6176, 2.0964, 2.0591],
  "worktree_sec": [1.8115, 1.4447, 1.4231],
  "copytree_avg_sec": 2.2577,
  "worktree_avg_sec": 1.5598,
  "speedup_pct": 30.9141
}
```

## Interpretation

The current repository snapshot only shows a roughly 0.70s absolute improvement because the filtered copytree path is already small. The relative improvement is still meaningful, and the worktree path should scale better as ignored caches, reports, and generated files grow.

## Follow-Up

Keep the copytree fallback for systems where `git worktree` is unavailable or diff application fails. Use the `sandbox_mirror.strategy` field in Ultra Review reports to confirm which path was used.
