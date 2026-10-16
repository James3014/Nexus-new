# Context Map

This repository uses a multi-context domain model. Each context has its own `CONTEXT.md` defining its ubiquitous language and `docs/adr/` for local architectural decisions.

| Context | Path | Description |
|---------|------|-------------|
| Agents | `nexus_agent_brain_hub/` | Agent brain and orchestration hub |
| Policy | `ebpf_policy/` | eBPF based security policies |
| Docs | `docs/` | System-wide documentation and ADRs |
| Global | `./` | Root context for project-wide terms |
