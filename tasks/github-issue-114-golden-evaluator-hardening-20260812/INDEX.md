---
artifact_authority: current
owner: James Chen
status: active
purpose: Govern Issue #114 Golden evaluator evidence hardening on fresh GitHub main.
---

# Issue 114 Golden Evaluator Hardening

- Issue: `#114`
- Baseline: `bc16cbf2bf00377a4521e3eab233175112d0c963`
- AUTO_CHAIN: `false`
- Active card: `00-golden-evaluator-hardening.md`
- Worker guidance: Agy `agy_flash_medium / gemini-3.6-flash-medium` may provide bounded candidate analysis only; coordinator materializes the exact governed diff through typed workspace edits and independently verifies it.
- Claim ceiling: `GOLDEN_EVALUATOR_EVIDENCE_HARDENING_CANDIDATE`

The frozen `tests/golden_behavior/corpus.py` and `tests/golden_behavior/test_corpus.py` surfaces remain owned by #65 and are forbidden here.
