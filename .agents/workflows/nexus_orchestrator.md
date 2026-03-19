---
description: How to operate Nexus as an Orchestrator (Nexus-First Protocol)
---

# Nexus Orchestrator Workflow

This workflow defines the mandatory operational behavior for any Agent interacting with the Nexus project.

## 1. Initialization
- Always read `docs/INDEX.md` and `docs/INDEX_GOVERNANCE.md` first.
- Re-sync with the current focus in `docs/EXEC_LIVE_STATUS.md`.

## 2. Task Delegation (Nexus-First)
- **Constraint**: DO NOT implement code changes manually unless they are system-level bootstrapping fixes.
- **Action**: Add implementation tasks to `task_manifest.yaml` and delegate execution to Nexus using:
  ```bash
  uv run scripts/nexus_cli.py nexus:runner --task <TASK_ID> --with-deps
  ```

## 3. Voice Notification Policy
- **Constraint**: Respect `NEXUS_SILENT` for noisy technical logs.
- **Exception**: Always ensure "Important" events (Startup, Completion, Critical Alerts) use `urgency="critical"` to bypass silence.

## 4. Learning Loop
- Ensure every executed task is recorded in the `MemoryService` (LanceDB/JSONL) to improve the system's future autonomy.
