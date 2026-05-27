# Graph Report - packages  (2026-05-27)

## Corpus Check
- 8 files · ~6,396 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 215 nodes · 254 edges · 19 communities (5 shown, 14 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 3 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `b07f0eb6`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]

## God Nodes (most connected - your core abstractions)
1. `file_nexus_proto_rawDescGZIP()` - 17 edges
2. `PolicyRequest` - 11 edges
3. `PolicyDecision` - 11 edges
4. `PhaseOutcome` - 11 edges
5. `WorktreeLease` - 10 edges
6. `MetricEvent` - 10 edges
7. `ActionResponse` - 10 edges
8. `LeaseRequest` - 9 edges
9. `PhaseRequest` - 9 edges
10. `HarvestRequest` - 8 edges

## Surprising Connections (you probably didn't know these)
- `main()` --calls--> `NewNexusCoreClient()`  [INFERRED]
  swarm/cmd/main.go → swarm/nexus/nexus_grpc.pb.go
- `main()` --calls--> `RegisterNexusSwarmServer()`  [INFERRED]
  swarm/cmd/main.go → swarm/nexus/nexus_grpc.pb.go
- `main()` --calls--> `NewNexusSwarmClient()`  [INFERRED]
  swarm/cmd/smoke_client/main.go → swarm/nexus/nexus_grpc.pb.go

## Communities (19 total, 14 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.07
Nodes (8): HealthCheckResponse, HealthCheckResponse_ServingStatus, file_nexus_proto_init(), file_nexus_proto_rawDescGZIP(), init(), PhaseID, PhaseOutcome_Status, PolicyDecision_SentinelIntents

### Community 1 - "Community 1"
Cohesion: 0.08
Nodes (18): NewNexusSwarmClient(), _NexusCore_CancelLease_Handler(), _NexusCore_EvaluatePolicy_Handler(), _NexusCore_HarvestWorktree_Handler(), _NexusCore_HealthCheck_Handler(), _NexusCore_LeaseWorktree_Handler(), _NexusSwarm_EmitMetrics_Handler(), _NexusSwarm_RunPhase_Handler() (+10 more)

### Community 11 - "Community 11"
Cohesion: 0.36
Nodes (5): main(), PathExists(), pingUDS(), swarmServer, NewNexusCoreClient()

### Community 14 - "Community 14"
Cohesion: 0.29
Nodes (6): API, code:bash (docker run -v $(pwd):/workspace -p 50051:50051 ghcr.io/nexus), code:rust (tonic::client::Grpc<PolicyService> -> EvaluatePolicy(intent)), Features, Nexus Rust Core v2.8 - Neural Policy Gate, Quickstart

## Knowledge Gaps
- **7 isolated node(s):** `NexusCoreServer`, `UnsafeNexusCoreServer`, `NexusSwarmServer`, `UnsafeNexusSwarmServer`, `code:bash (docker run -v $(pwd):/workspace -p 50051:50051 ghcr.io/nexus)` (+2 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **14 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `file_nexus_proto_rawDescGZIP()` connect `Community 0` to `Community 2`, `Community 3`, `Community 5`, `Community 6`, `Community 8`, `Community 9`, `Community 10`, `Community 12`, `Community 13`, `Community 15`?**
  _High betweenness centrality (0.061) - this node is a cross-community bridge._
- **Why does `PolicyDecision` connect `Community 7` to `Community 0`?**
  _High betweenness centrality (0.056) - this node is a cross-community bridge._
- **Why does `PolicyRequest` connect `Community 3` to `Community 0`?**
  _High betweenness centrality (0.056) - this node is a cross-community bridge._
- **What connects `NexusCoreServer`, `UnsafeNexusCoreServer`, `NexusSwarmServer` to the rest of the system?**
  _7 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.06794871794871794 - nodes in this community are weakly interconnected._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.07765151515151515 - nodes in this community are weakly interconnected._