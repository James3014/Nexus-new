# Handoff protocol

`HANDOFF.md` at the repository root is the shared progress log for every agent (Claude, Codex, others) and every device. It records state only; it grants no authority and never overrides `AGENTS.md`, Issues, or Task Cards.

- **Read first.** At session start read `HANDOFF.md`. If its recorded HEAD is behind, run `git log <recorded-HEAD>..HEAD` and correct stale entries before acting on them.
- **Update at milestones.** Update it when a meaningful step finishes or before the session ends — not every turn. Overwrite stale state; do not append history.
- **Format.** The header line holds date, author agent, and current short HEAD. `▶ 下一步` has exactly one item. Every todo carries an Issue number (`#N`); items without one go under `待確認`. Record why, blockers, and next — not changed-file lists (git already has those).
- **Size cap: 150 lines.** Move finished or expired content to `docs/archive/HANDOFF-YYYY-MM.md`.
- **Read back.** After writing, re-read `HANDOFF.md` to confirm the change actually landed.
- **No secrets.** Never put tokens, passwords, credentials, or internal hostnames in it.
