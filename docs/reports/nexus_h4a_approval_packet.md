# H4-A: Stronger Model Fallback Approval Packet + C1/C2

## H4-A: Approval Packet

### Options

| Option | Description | Classification |
|--------|-------------|----------------|
| APPROVE_H4B_CLOUD_SEMANTIC_FALLBACK | Cloud API for C_13453 | cloud_success |
| APPROVE_H4B_REMOTE_LOCAL_LARGER_MODEL | Larger local/remote model | remote_local_success |
| APPROVE_C1_CAPABILITY_CURVE_ONLY | Run easier tasks with local models | local_success |
| DEFER_H4 | Defer both | deferred |

### Evidence Summary

| Phase | Result |
|-------|--------|
| M6 | No native binding, 12B semantic fail |
| B2 | Native binding improved behavior, 0→2 patch applied |
| B3 | Deep evidence explained bug, 12B still wrong mechanism |

### Risk Matrix

| Risk | Cloud | Remote Local | Capability Curve |
|------|-------|--------------|------------------|
| Privacy | Code to cloud | Local/remote | None |
| Cost | Variable | Hardware | Local only |
| Classification | cloud_success | remote_local | local_success |

## C1: Task Selection

| Bucket | Tasks | Difficulty |
|--------|-------|------------|
| Easy localized | 2 fixtures | easy |
| Medium semantic | 2 fixtures | medium |
| Constructor | C_12481 | hard |
| Hard semantic | C_13453 | hard |

## C2: Protocol

- 3B advisory → 7B generate → 12B fallback
- One model at a time, unload after call
- Same parser/verifier/compliance gates
- Record metrics per task per model

## Status

- H4A: H4A_APPROVAL_PACKET_READY
- C1: C1_CAPABILITY_CURVE_TASKS_SELECTED
- C2: C2_PROTOCOL_READY

## Owner Decision Required

Choose one:
1. APPROVE_H4B_CLOUD_SEMANTIC_FALLBACK_C13453
2. APPROVE_H4B_REMOTE_LOCAL_LARGER_MODEL_C13453
3. APPROVE_C1_CAPABILITY_CURVE_ONLY
4. DEFER_H4
