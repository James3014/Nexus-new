# P180 Learning Closure

## Failure 1: CLI Import Boundary
- Symptom: `python3 scripts/ops/hallucination_guard_drift.py` failed with `ModuleNotFoundError: No module named 'nexus'`.
- Root cause: script imported repository packages before inserting repo root into `sys.path`.
- Lesson: every standalone ops CLI must bootstrap `REPO_ROOT` before importing `nexus.*`.
- Closure: fixed in `scripts/ops/hallucination_guard_drift.py`; covered by direct CLI execution evidence.

## Failure 2: TypedDict Misused As Runtime Type
- Symptom: StateContract test used `isinstance(state.metadata, PipelineMetadata)` and failed because TypedDict is static-only.
- Root cause: test confused static schema with runtime object type.
- Lesson: contract tests should assert runtime behavior and retained keys, not TypedDict instance checks.
- Closure: test now asserts dict behavior and conversation retention.

## Failure 3: Conversation Metadata Dropped During Validation
- Symptom: legacy `metadata.conversation` disappeared after `NexusState.model_validate`.
- Root cause: `PipelineMetadata` did not declare `conversation`, so Pydantic discarded the key.
- Lesson: every runtime metadata key used by StateContract helpers must be present in the PipelineMetadata SSOT.
- Closure: added `conversation` to `nexus/core/pipeline_metadata.py`; covered by `tests/core/test_state_contracts.py`.
