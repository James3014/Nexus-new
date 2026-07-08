---
name: last-word
description: |
  清空 context 前的收尾歸檔工具 — 保存學習成果，讓下次 session 無痛接續。
  觸發詞：「last-word」「收尾」「整理一下 context」「session 結束前」。
  何時用：context 即將壓縮（~40%）或 session 即將結束時，主動觸發此 skill 做結構化收尾。
  何時不用：一次性簡單任務、context 充裕時。
  成功輸出：歸檔完畢 + starter prompt（若有未完成工作）+ 確認可 /clear。
---

# /last-word — Session 收尾歸檔

Structured session wrap-up before clearing context. Follow each step, report results as you go.

## Step 1: Review

Scan the conversation. Identify: blockers, wins, CLAUDE.md gaps. Brief summary.

## Step 2: Classify & Archive

For each learning, decide where it goes:
- **Universal rule** → `~/.claude/CLAUDE.md`
- **Project rule** → `{project_root}/CLAUDE.md`
- **Temp state** → Memory (project-scoped)
- **Design decision** → Design doc or memory
- **Already tracked** → Do not save

Before writing, check for duplicates — update existing entries instead.

## Step 3: Remaining Work

If unfinished work exists:
1. Save progress to memory (what's done, what remains, branches, issues)
2. Generate a starter prompt for next session in a code block

If all complete, say so and skip.

## Step 4: Sync Issues

If `gh` CLI is available, run `gh issue list`. Verify status matches progress. Suggest closing resolved issues.

## Step 5: Clean Stale Content

Scan memory and CLAUDE.md. Remove: completed tasks, outdated entries, duplicates. Report changes.

## Step 6: Uncommitted Changes

Run `git status` and `git diff --stat`. Warn if uncommitted changes exist.

## Step 7: Summary

```
=== Session Wrap-Up Complete ===
Archived: [what was saved and where]
Cleaned: [what was removed]
Starter Prompt: [saved / not needed]
Uncommitted: [none / list files]
Ready to /clear: [Yes / No — reason]
```

Wait for user confirmation before /clear.
