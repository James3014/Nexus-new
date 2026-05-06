# ADR-2026-05-06: S2T Contract and Export Seam

## Status

Accepted

## Context

S2T had a useful partial implementation, but export/redaction lived in `s2t_trace.py`. That made the trace contract too broad and left the Agent Lightning export seam implicit.

## Decision

1. Keep `S2TTraceEvent` and `S2TTraceWriter` in `s2t_trace.py`.
2. Move training/export concerns into `s2t_export.py`.
3. Keep wrapper functions in `s2t_trace.py` for backward compatibility.
4. Add a dedicated redaction test so training export safety is independently gated.

## Lessons

1. Trace contracts and training export are separate seams. Mixing them makes Phase 0 look complete while export safety remains hard to audit.
2. The repository can hit `.git/index.lock` permission errors under sandboxed git operations. Retry staging through the approved git path rather than changing unrelated files or deleting locks.

## Evidence

- `tests/contracts/test_s2t_contracts.py`: PASS.
- `tests/contracts/test_s2t_redaction.py`: PASS.
- `tests/ops/test_export_s2t_agent_lightning.py`: PASS.
- `tests/ops/test_s2t_adoption_gate.py`: PASS.
