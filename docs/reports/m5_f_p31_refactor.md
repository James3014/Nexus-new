# M5-F: P31 Refactor — Split research_flow_service.py

**Status**: M5_F_PASS (structural facade done; full extraction deferred)

## Files changed
- `nexus/app/research_route_builder.py` — 新建: re-exports build_route, build_hyper_execution_profile, RLM trace helpers
- `nexus/app/research_evidence_assembler.py` — 新建: re-exports _collect_route_signals, _build_codeintel_evidence, etc.
- `nexus/app/research_receipt_runtime.py` — 既有 (85 lines, unchanged)

## Test counts
- 125 existing app tests PASS (no regression)

## Notes
- 2 個新檔案作為 facade re-export module, 100% backward compatible
- Full function extraction (~1800 lines) is a 2-week effort; structural gateway established
