# Campaign Index: ASTRA-P6C-COMPAT-FIX-20260908

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Repair four baseline-existing test-fixture model drift failures needed by the approved P5/P6 source compatibility verifier. Exact frozen source8f2baa4cd7711818321263dd3f8f923482d131f8. In only the listed test file derive valid request/receipt expected model and worker identity from the actual test admission binding, replacing outdated hardcoded gemini-3.6-flash-high fixture values. Preserve tampered-model rejection, provider/preflight call-count assertions and card-drift/fallback denial intent; do not weaken production admission or convert failing tests to skipped. No production source/policy/model routing edits. Tests use existing mocks only; no actual Agy/Gemini/provider/API-key/SDK/native/network calls. No live-state/deployment/config/main/push/merge/approval/integration. Worker may scoped source commit after successful checks; independent controller acceptance required. Full P6C compatibility tests must rerun with durable JUnit and exactrevision.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `astra-p6c-compat-fix-20260908` | `00-astra-p6c-compat-fix-20260908.md` | ACTIVE | Owner confirmation |
