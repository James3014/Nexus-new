# Gemini CLI Bootstrap

1. Resolve `AGENTS.md`, `MUSE_PROTO.md`, and the active Git-tracked Task Card from the current worktree.
2. Freeze the current worktree root, branch, HEAD, and dirty state before mutation.
3. Use formal lifecycle state and receipts for recovery; do not require an external sync command or a fixed checkout path.
4. A missing or stale Task Card is a bootstrap block, not permission to guess.
