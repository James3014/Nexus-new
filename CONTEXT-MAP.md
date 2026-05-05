# Context Map

This repository uses a multi-context domain model. Each context has its own `CONTEXT.md` defining its ubiquitous language and `docs/adr/` for local architectural decisions.

| Context | Path | Description |
|---------|------|-------------|
| Core | `nexus-core/` | Nexus core logic and engine |
| Rust | `nexus-rust-v16/` | Rust implementation of core components |
| Swarm | `nexus-swarm-v22-prod/` | Swarm orchestration and production logic |
| Agents | `nexus_agent_brain_hub/` | Agent brain and orchestration hub |
| Policy | `ebpf_policy/` | eBPF based security policies |
| Docs | `docs/` | System-wide documentation and ADRs |
| Global | `./` | Root context for project-wide terms |
