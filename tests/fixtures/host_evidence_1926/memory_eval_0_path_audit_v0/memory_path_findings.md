# Memory Path Findings

## 1. Is core memory lane connected? YES

The core memory lane is connected:
- MemoryRetrievalAdapter retrieves from LearningClosure JSONL + FindingsMemory + optional LanceDB
- native_evidence_packet consumes memory and adds to evidence
- prompt_builder injects memory into prompt
- receipt records memory_influence
- LearningClosureBridge writes back lessons

## 2. Is full Nexus memory connected? NO

Not connected:
- MemoryService / MemoryCoordinator
- MemPalace
- Learn Scheduler / SLO / KPI

## 3. Does memory enter evidence packet? YES

native_evidence_packet.py calls MemoryRetrievalAdapter and includes memory_evidence in the packet.

## 4. Does memory enter prompt? YES

prompt_builder.py injects memory section into the prompt (lines 121-136).

## 5. Does receipt record memory influence? YES

receipt.py:_extract_memory_trace() reads ctx._memory_influence_trace and writes to receipt.memory_influence.

## 6. Does learning closure write back usable memory? YES

LearningClosureBridge.write_lesson() writes to learning_closure.jsonl and FindingsCard.

## 7. Can one repair attempt correlate memory/evidence/prompt/verifier/receipt by identity? YES

All paths use instance_id:
- EvidenceHarness: instance_id (line 528)
- Receipt: instance_id via ctx.op.instance_id
- LearningClosure: instance_id via ctx.op.instance_id
- MemoryTrace: attached to ctx.op._memory_influence_trace

## 8. What is the smallest blocker before executable eval?

The EvidenceHarness task_id propagation uses instance_id (which is correct), but the actual runtime artifact showed task_id="unknown" because the hook was tested in isolation, not with a real OperationalContext. This is a test coverage gap, not a production bug.

---

## Conclusion

**MEMORY_EVAL_0_READY_FOR_SMALL_EXECUTABLE_EVAL**

The memory path is connected and traceable. The smallest blocker is test coverage to prove identity correlation works with real OperationalContext instances.
