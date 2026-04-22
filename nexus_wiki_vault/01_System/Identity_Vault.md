# Identity Vault: Nexus v24 Agent Ecosystem
- learn_mode_agent:
  - role: Autonomous Ingest & Sync
  - boundary: [research/learn, wiki/knowledge]
  - lifecycle: Init/Active/Archive
  - forbidden: [modify:core/engine_core, invoke:manual_patching]

- codex_supervisor:
  - role: Codebase Audit & Guardrail
  - boundary: [nexus/core, nexus/delivery]
  - lifecycle: Init/Active/Archive
  - forbidden: [modify:wiki, invoke:autonomic_routing]

- gemini_router:
  - role: Intent Classifier
  - boundary: [nexus/app/entrypoint]
  - lifecycle: Init/Active/Archive
  - forbidden: [read:secret_ledger, modify:core/logic]
