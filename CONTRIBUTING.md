# Contributing to Nexus v9 Autonomic 🚀

Welcome! To ensure the highest quality in autonomous code evolution, please follow the Nexus **P-D-R-A-C** autonomic protocol.

## 🧬 P-D-R-A-C Protocol

1.  **P (Plan)**: Define your task. Use specialized planners (`nexus-planner-expert`).
2.  **D (Diagnose)**: Identify failure modes. Use `nexus-debug-expert` for deep RCA.
3.  **R (Repair/Refine)**: Apply patches using the autonomic fallback chain to ensure reliability.
4.  **A (Audit/Analyze)**: Run `nexus:test --full-chain` and `FlashJudge 8.0` validation.
5.  **C (Crystallize/Commit)**: Use `nexus:crystal` to integrate the experience back into the brain.

## 🛡️ Guidelines

- **Autonomic Awareness**: Every execution generates a trace in `tracelog.jsonl`. Ensure your changes are traceable.
- **Skill Modularity**: New features should be implemented as "Skills" registered in `skills_inventory.json`.
- **Isolation**: Always use isolated environments for task execution to prevent side effects.
- **Resilience**: Design for failure. Always provide backup logic for mission-critical paths.

## 🧪 How to Verify Your Contribution

Run the full autonomic verification chain:
```bash
python3 scripts/nexus_cli.py nexus:test --full-chain "Your implemented feature"
```

Happy Evolving! 🛡️💎🚀✨🚩
