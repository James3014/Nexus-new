# B1-E: C_13453 Native Binding Dry Run

## Status: B1E_PARTIAL_BINDING_PROVEN

## Results

| Phase | Capability | Invoked | Evidence |
|-------|-----------|---------|----------|
| 1. Route Request | NativeRouteAdapter | ✅ | route_request.json |
| 2. Route Decision | NativeRouteAdapter | ✅ | route_decision.json |
| 3. Evidence Packet | NativeEvidencePacketBuilder | ✅ | 8 codeintel + 2 memory items |
| 4. Prompt Builder | NativePromptBuilder | ✅ | 7273 chars, includes native evidence |
| 5. Model Generation | 7B (qwen2.5-coder:7b) | ✅ | 3/3 ABSTAIN |
| 6. Validation Receipt | NativeValidationBridge | ✅ | PATCH_APPLY_FAILED |
| 7. Authority Trace | All phases | ✅ | authority_trace.json |

## Key Findings

1. **Native capabilities ARE invoked**: Route decision, evidence packet, prompt builder, validation receipt all executed.

2. **Model prompt DOES include native evidence**:
   - Contains "CODEINTEL EVIDENCE" section
   - Contains "PRIOR LESSONS" section
   - Contains "OUTPUT CONTRACT" section

3. **Model did NOT directly call tools**: Prompt is structured, no raw CLI instructions.

4. **7B still abstains**: With better context, 7B still recognizes task difficulty and abstains.

5. **RBP comparison**:
   - Before B1: local_heal bypassed native capabilities
   - After B1: native capabilities are invoked, evidence enters prompt

## What Changed

| Metric | RBP Baseline | B1-E Result |
|--------|-------------|-------------|
| Route decision | Not invoked | Invoked |
| CodeIntel evidence | Not in prompt | 8 items in prompt |
| Memory evidence | Not in prompt | 2 items in prompt |
| Prompt builder | Ad-hoc markdown | NativeEvidencePacket-based |
| Validation receipt | receipt.json only | authority_trace recorded |
| Model tool calling | N/A | No direct tool calls |

## Conclusion

**B1E_PARTIAL_BINDING_PROVEN**

Native Nexus capabilities are now connected to the local_heal model repair path. The binding proves that:
- Route decision is made before model execution
- Evidence packet is built from existing capabilities
- Prompt includes bounded native evidence
- Validation receipt records authority trace

7B still abstains, which is the correct behavior for a difficult task. The binding is proven; the semantic bottleneck remains.

## Next Step

If owner wants to test whether native evidence improves 7B/12B performance, run a full model rerun with B1 binding. Otherwise, the binding proof is complete.
