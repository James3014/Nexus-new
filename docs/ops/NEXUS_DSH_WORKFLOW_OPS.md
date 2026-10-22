# DSH standalone source

`prepare-standalone` checks the selected source checkout, its common Git directory, and its linked worktrees. DSH grants host temp areas writable to every session, so a source family with a checkout under `/private/tmp` is rejected. The blocked receipt lists the exposed paths.

When unrelated sessions keep linked worktrees there, make a dedicated independent source clone outside the temp grant. Use `git clone --no-local` so its object store and worktree list are separate. Confirm that its `origin` identifies the requested repository and that it contains the exact base commit. Do not use the temp directory for either the dedicated source or DSH target.

```sh
git clone --no-local <trusted-source> <dedicated-source-outside-temp>
git -C <dedicated-source-outside-temp> remote set-url origin <trusted-origin-url>
scripts/ops/nexus-dsh-workflow prepare-standalone \
  --repository <owner/name> \
  --source-repo <dedicated-source-outside-temp> \
  --base-revision <full-commit-sha> \
  --target <standalone-target-outside-temp>
```

`--source-repo-root` remains supported. The standalone receipt grants no copy-back or publication authority.
