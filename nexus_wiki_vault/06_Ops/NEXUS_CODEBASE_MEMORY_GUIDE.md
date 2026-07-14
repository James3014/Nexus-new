# Nexus Codebase Intelligence Guide

## Overview

Nexus has a pre-indexed knowledge graph via `codebase-memory-mcp`. Use the `bash` tool to query it.

**Binary**: `./codebase-memory-mcp` (in nexus root)
**Project name**: `Users-jameschen-Workspace-nexus`
**Stats**: 121,776 nodes / 458,349 edges / 8,714 files

## Quick Reference

### Architecture Overview
```bash
./codebase-memory-mcp cli get_architecture '{"repo_path": "/Users/jameschen/Workspace/nexus", "project": "Users-jameschen-Workspace-nexus", "aspects": ["all"]}'
```

### Search by Name (class/function/method)
```bash
./codebase-memory-mcp cli search_graph '{"repo_path": "/Users/jameschen/Workspace/nexus", "project": "Users-jameschen-Workspace-nexus", "name_pattern": ".*KEYWORD.*", "labels": ["Class"]}'
```
Labels: `Class`, `Function`, `Method`, `Variable`, `File`, `Module`

### Trace Call Chain
```bash
# Who calls this?
./codebase-memory-mcp cli trace_path '{"repo_path": "/Users/jameschen/Workspace/nexus", "project": "Users-jameschen-Workspace-nexus", "function_name": "TARGET", "direction": "inbound", "max_depth": 3}'

# What does this call?
./codebase-memory-mcp cli trace_path '{"repo_path": "/Users/jameschen/Workspace/nexus", "project": "Users-jameschen-Workspace-nexus", "function_name": "TARGET", "direction": "outbound", "max_depth": 3}'
```

### Search Code Content (grep-style)
```bash
./codebase-memory-mcp cli search_code '{"repo_path": "/Users/jameschen/Workspace/nexus", "project": "Users-jameschen-Workspace-nexus", "pattern": "PATTERN", "max_results": 10}'
```

### Detect Git Diff Impact
```bash
./codebase-memory-mcp cli detect_changes '{"repo_path": "/Users/jameschen/Workspace/nexus", "project": "Users-jameschen-Workspace-nexus"}'
```

### List Indexed Projects
```bash
./codebase-memory-mcp cli list_projects '{}'
```

## Key Architectural Hubs

| Component | in_degree | Role |
|-----------|-----------|------|
| NexusState | 388 | Global state contracts |
| HealContext | 102 | LocalHeal main context |
| CapabilityPlanner | 97 | Route authority |
| CapabilityReceipt | 78 | Execution receipts |
| RouteMode | 70 | Route mode enum |
| SolidSearchReplaceProtocol | 69 | Patch protocol |
| LearnModeService | 68 | Learning service |
| HealPipeline | 65 | LocalHeal pipeline |
| CandidateEnvelope | 56 | Committee candidates |
| FlowState | 56 | Pipeline flow state |

## Directory Structure

```
nexus/
├── contracts/        # Route contracts (HybridRouteDecision, RouteMode, Authority)
├── engine/           # CapabilityPlanner, Pipeline, Coordinator
├── core/             # State contracts, ContextHub, SkillsRouter
├── services/
│   ├── local_heal/   # HealPipeline, Orchestrator, Protocol, Patcher
│   ├── mem_palace.py # Governance constraints
│   ├── memory.py     # Memory service
│   └── gateway.py    # BattlesuitGateway
├── research/         # LearnMode, FindingsMemory, SprintService
├── learning/         # Skill registry, SkillFit ablation
├── verifiers/        # Verifier contracts
├── governance/       # Hallucination guard
└── delivery/         # Delivery gate
```

## Common Queries

### "What calls CapabilityPlanner?"
```bash
./codebase-memory-mcp cli trace_path '{"repo_path": "/Users/jameschen/Workspace/nexus", "project": "Users-jameschen-Workspace-nexus", "function_name": "CapabilityPlanner", "direction": "inbound", "max_depth": 3}'
```

### "Find all classes in local_heal"
```bash
./codebase-memory-mcp cli search_graph '{"repo_path": "/Users/jameschen/Workspace/nexus", "project": "Users-jameschen-Workspace-nexus", "name_pattern": ".*", "labels": ["Class"], "file_pattern": "nexus/services/local_heal/", "max_results": 50}'
```

### "What does HealPipeline depend on?"
```bash
./codebase-memory-mcp cli trace_path '{"repo_path": "/Users/jameschen/Workspace/nexus", "project": "Users-jameschen-Workspace-nexus", "function_name": "HealPipeline", "direction": "outbound", "max_depth": 2}'
```

### "Find HybridRouteDecision usage"
```bash
./codebase-memory-mcp cli search_code '{"repo_path": "/Users/jameschen/Workspace/nexus", "project": "Users-jameschen-Workspace-nexus", "pattern": "HybridRouteDecision", "max_results": 15}'
```

### "What files changed in git?"
```bash
./codebase-memory-mcp cli detect_changes '{"repo_path": "/Users/jameschen/Workspace/nexus", "project": "Users-jameschen-Workspace-nexus"}'
```

## Notes

- All queries are read-only, safe to run anytime
- Results are JSON; key fields: `name`, `file_path`, `in_degree`, `out_degree`, `label`
- `in_degree` = how many things depend on this (higher = more central)
- `out_degree` = how many things this depends on
- Filter out `.tmp_build/` results (test artifacts, not real code)
