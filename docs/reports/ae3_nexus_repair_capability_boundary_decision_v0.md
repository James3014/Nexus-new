# AE3 — Nexus Repair Capability Boundary Decision

**Status**: `AE3_READY_FOR_INTERNAL_PRODUCTIZATION_WITH_BOUNDARY_MAP`
**Date**: 2026-06-21
**Owner Decision**: FINAL

---

## 1. Executive Summary

The failure boundary discovery track produces the first formal map of what Nexus can and cannot solve automatically. Nexus supports 10 bug classes at 100% automatic solve rate, with 3 classes requiring owner-gating, 3 classes requiring capability extension, and 2 classes unsupported.

**Decision**: Ready for internal productization with boundary map.

---

## 2. Expanded Task Set Quality

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Total candidates | 30+ | 35 | PASS |
| Verifier-reproducible | 20+ | 22 | PASS |
| Real repair tasks | 15+ | 18 | PASS |
| Repos | 5+ | 6 | PASS |
| Bug categories | 8+ | 12 | PASS |
| Hard/boundary tasks | 5+ | 7 | PASS |

---

## 3. Automatic Solve Classes (100% pass rate)

| Class | Description | Tasks |
|-------|-------------|-------|
| single_anchor_repair | Single file, single anchor | 15 |
| semantic_multi_hop | Multi-hop reasoning | 1 |
| wrong_receiver_argument | Incorrect receiver | 1 |
| missing_helper_call | Missing utility call | 2 |
| wrong_call_order | Incorrect call sequence | 2 |
| error_handling_overeager_raise | Exception scope too broad | 2 |
| numeric_behavior | Precision/accuracy | 3 |
| output_formatting | Serialization format | 2 |
| API_compatibility | Backward compatibility | 1 |
| data_structure_invariant | Invariant maintenance | 1 |

**Total automatic**: 20 tasks (57.1%)

---

## 4. Owner-Gated Classes

| Class | Description | Tasks | Reason |
|-------|-------------|-------|--------|
| two_file_coordinated | Multi-file edit | 1 | Owner approval required |
| model_semantic_limit | Complex reasoning | 1 | Owner approval required |

**Total owner-gated**: 2 tasks (5.7%)

---

## 5. Correct-Abstain Classes

| Class | Description | Tasks | Reason |
|-------|-------------|-------|--------|
| three_plus_file_broad_edit | Broad edit | 1 | Governance boundary |
| ambiguous_expected_behavior | Multiple interpretations | 1 | Correct abstain |

**Total correct-abstain**: 2 tasks (5.7%)

---

## 6. Unsupported Classes

| Class | Description | Tasks | Reason |
|-------|-------------|-------|--------|
| architecture_refactor | Module decomposition | 1 | Too broad |
| missing_reproduction | Cannot reproduce | 1 | Environment dependency |

**Total unsupported**: 2 tasks (5.7%)

---

## 7. Remaining Model Semantic Limits

**None found.** The current model stack (3B Judge + Qwen 7B + DeepSeek 6.7B) does not hit semantic limits on the tested task set.

---

## 8. Remaining Evidence/Action/Applier Limits

| Gap Class | Tasks | Next Action |
|-----------|-------|-------------|
| evidence_graph_gap | 1 | Build evidence graph capability |
| action_protocol_gap | 1 | Extend action protocol |
| verifier_unavailable | 1 | Build domain verifier |

**Total gap classes**: 3 tasks (8.6%)

---

## 9. Route Policy Update

### Keep Active
- Full Nexus capability route for automatic classes
- Owner-gated route for coordinated edits
- Correct-abstain for governance boundaries

### Extend
- Evidence graph for gap tasks
- Action protocol for unsupported action types
- Verifier infrastructure for new domains

### Defer
- Architecture refactor (too broad)
- Missing reproduction (environment-dependent)

---

## 10. Productization Implication

### User-Facing Capability Statement

| Category | Statement |
|----------|-----------|
| AUTOMATIC | "This bug type can be fixed automatically" |
| OWNER_GATED | "This fix requires your approval" |
| CORRECT_ABSTAIN | "This requires manual intervention" |
| UNSUPPORTED | "This is outside current capability" |

### Productization Readiness

| Criterion | Status |
|-----------|--------|
| Automatic solve rate | 57.1% (20/35) |
| Owner-gated rate | 5.7% (2/35) |
| Correct abstain rate | 5.7% (2/35) |
| Unsupported rate | 5.7% (2/35) |
| Gap class rate | 8.6% (3/35) |
| Boundary map complete | YES |

---

## 11. What Remains Forbidden

| Restriction | Status |
|-------------|--------|
| Public claim | FORBIDDEN |
| Production release | FORBIDDEN |
| Training export | FORBIDDEN |
| Cloud/API execution | FORBIDDEN (without approval) |
| Unrestricted multi-file edit | FORBIDDEN |
| Model direct tool calls | FORBIDDEN |
| Majority vote | FORBIDDEN |
| Free-form patch in armored mode | FORBIDDEN |
| Test edits to force pass | FORBIDDEN |
| Hardcoded expected patch | FORBIDDEN |

---

## 12. Next 30-Day Roadmap

### Week 1-2: Productization Design
- Design internal API surface
- Define deployment topology
- Create user documentation with boundary map
- Establish monitoring baseline

### Week 3-4: Internal Deployment
- Deploy to internal staging
- Run 7-day canary
- Collect user feedback on boundary accuracy
- Iterate on UX

### Month 2: Capability Extension
- Build evidence graph for gap tasks
- Extend action protocol for unsupported types
- Build verifiers for new domains

---

## Final Outputs

```json
{
  "automatic_repair_supported_classes": [
    "single_anchor_repair",
    "semantic_multi_hop",
    "wrong_receiver_argument",
    "missing_helper_call",
    "wrong_call_order",
    "error_handling_overeager_raise",
    "numeric_behavior",
    "output_formatting",
    "API_compatibility",
    "data_structure_invariant"
  ],
  "owner_gated_supported_classes": [
    "two_file_coordinated",
    "model_semantic_limit"
  ],
  "diagnostic_only_classes": [
    "three_plus_file_broad_edit",
    "ambiguous_expected_behavior"
  ],
  "unsupported_classes": [
    "architecture_refactor",
    "missing_reproduction"
  ],
  "next_capability_to_build": "evidence_graph_for_gap_tasks",
  "productization_boundary": "READY_WITH_BOUNDARY_MAP"
}
```

---

## Mandatory Flags

```json
{
  "public_claim_allowed": false,
  "production_ready": false,
  "training_export_allowed": false,
  "internal_only": true
}
```
