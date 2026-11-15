# Review routing

由 `scripts/ops/review_record_check.py` 的 `REVIEW_ROUTES` 產生，勿手改。

| Risk | Round | Required reviewer records |
| --- | --- | --- |
| low | 1 | claude |
| high | 1 | claude + cross_model |
| low | 2+ | claude or gemini + codex |
| high | 2+ | claude + cross_model or gemini + codex |
