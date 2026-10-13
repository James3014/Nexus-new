# Deletion guard

CI check "Deletion guard" (`.github/workflows/deletion-guard.yml`, script `scripts/ops/deletion_guard.py`).

- It lists the files of a PR through the GitHub REST API. If any file is `removed` or `renamed`, the check fails and prints the paths.
- It passes when there are no deletions/renames, or when the PR carries the label `owner-approved-deletion`.
- It fails closed on API errors, a missing token, or a PR with 3000+ files (the API cap).
- It runs on `pull_request_target` and only checks out the default branch; it never runs PR code.

## Owner chat-OK rule

A PR that deletes or renames tracked files must not merge until the Owner OKs it in chat. After that OK, the agent adds the label. No signatures or markers are needed.

```
gh pr edit N --add-label owner-approved-deletion
```

The label is created once with `gh label create owner-approved-deletion --color B60205 -R James3014/Nexus-new`. Removing the label re-arms the check.
