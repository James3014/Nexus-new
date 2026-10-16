# X0: Existing Capability Binding Audit

## Phase Summary

| Field | Value |
|-------|-------|
| Phase | X0 |
| Status | X0_EXISTING_CAPABILITY_BINDING_AUDIT_READY |
| Capabilities Audited | 14 |
| Can Reuse Directly | 14 |
| Needs Adapter | 2 |
| New Modules Needed | 0 |

## Key Finding

**All 14 existing Nexus capabilities can be reused directly for small-model codebase reasoning. No new modules are needed.**

## Capability Binding Matrix

| Capability | Phase | Authority | Reuse | Adapter |
|------------|-------|-----------|-------|---------|
| CodeIntel | context_discovery | MODEL_INPUT_PROVIDER | ✅ | No |
| Research/Learn/Ask | context_discovery | MODEL_INPUT_PROVIDER | ✅ | No |
| Memory/LanceDB | context_discovery | MODEL_INPUT_PROVIDER | ✅ | No |
| Hyper/Sprint | candidate_generation | ROUTER_AUTHORITY | ✅ | Yes |
| Nightshift | deferred_recovery | ROUTER_AUTHORITY | ✅ | No |
| Autoreason | review | MODEL_ADVISORY_ONLY | ✅ | No |
| DDTree | route_decision | ROUTER_AUTHORITY | ✅ | No |
| Belief | route_decision | ROUTER_AUTHORITY | ✅ | No |
| MemPalace/Policy/Capability Gate | preflight | GOVERNANCE_AUTHORITY | ✅ | No |
| Pregate/Plan Quality/Forecast Gate | preflight | GOVERNANCE_AUTHORITY | ✅ | No |
| Sandbox/Replay | validation | VERIFIER_AUTHORITY | ✅ | Yes |
| Artifact/Claim/Delivery/Acceptance Gate | delivery | DELIVERY_AUTHORITY | ✅ | No |
| Benchmark/Meta-Opt/Learning Closure | meta | GOVERNANCE_AUTHORITY | ✅ | No |
| Autonomic Router | route_decision | ROUTER_AUTHORITY | ✅ | No |

## Route Phases

1. **Preflight**: Pregate → Plan Quality → Capability Gate
2. **Context Discovery**: CodeIntel → Research/Learn/Memory
3. **Route Decision**: Autonomic Router → Belief → DDTree
4. **Candidate Generation**: Hyper/Sprint or G1-compatible pipeline
5. **Validation**: Sandbox/Replay → Verifier → Compliance
6. **Review and Delivery**: Autoreason (advisory) → Ultra Review → Claim/Delivery/Acceptance Gate

## Authority Classification

- **MODEL_INPUT_PROVIDER**: CodeIntel, Research/Learn, Memory — provide context to models
- **MODEL_ADVISORY_ONLY**: Autoreason — advisory review only, cannot override verifier
- **ROUTER_AUTHORITY**: Hyper/Sprint, Nightshift, DDTree, Belief, Autonomic Router — route decisions
- **GOVERNANCE_AUTHORITY**: MemPalace/Policy/Capability Gate, Pregate/Plan Quality, Benchmark/Meta-Opt
- **VERIFIER_AUTHORITY**: Sandbox/Replay — final verification
- **DELIVERY_AUTHORITY**: Artifact/Claim/Delivery/Acceptance Gate — final acceptance

## Conclusion

X-track should NOT build new repo-explorer/context/routing modules. Instead, it should bind small-model reasoning to existing Nexus capabilities through:

1. **Structured evidence packets** from CodeIntel/Research/Memory
2. **Router-mediated model execution** via Autonomic Router
3. **Governance gates** for model role boundaries
4. **Verifier-backed evidence** for success claims

This approach is safer, faster, and leverages proven Nexus infrastructure.
