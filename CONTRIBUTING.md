# Contributing to Nexus-AutoResearch 🚀

Welcome! To ensure the highest quality in autonomous code evolution, please follow the Nexus P-D-X-R-A-C protocol.

## 🧬 P-D-X-R-A-C Protocol
1.  **P (Plan)**: Define your task in `program.md`. Keep it atomic.
2.  **D (Diagnose)**: Capture clear failure signatures in `diagnosis.json`.
3.  **X (eXecute Research)**: Use RAG to pull external best practices.
4.  **R (Repair)**: Apply minimal, focused patches to the target file.
5.  **A (Audit)**: Run FlashJudge scores. 
6.  **C (Commit/Rollback)**: Automated by `nightshift.py` based on Audit performance.

## 🛡️ Guidelines
- **Isolation**: Always use `WorkspaceManager` (Git worktree) for developments.
- **Budget**: Respect the 300s/round time limit.
- **Rules**: Never bypass `program.md` constraints.

## 🚀 How to Start a Swarm
If you are deploying multiple agents, use:
```bash
nexusnightshift --task "refactor train loop" --swarm --workers 5
```

Happy Evolving! 🧠🦾
