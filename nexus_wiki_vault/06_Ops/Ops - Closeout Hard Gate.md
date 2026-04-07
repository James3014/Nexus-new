---
title: Ops - Closeout Hard Gate
aliases: [Closeout Gate, Done Contract Gate]
type: ops
status: active
version_scope: [v22, v23]
source_of_truth: repo-root
related_pages:
  - "[System Overview](../00_Home/System Overview.md)"
  - "[[Ops - CI/CD Promotion Gate]]"
  - "[Ops - Governance Changelog](Ops - Governance Changelog.md)"
tags: [ops, closeout, governance, gate]
last_compiled: 2026-04-07
confidence: high
owner: agent
---
# Ops - Closeout Hard Gate

## One-sentence summary
定義任務完成前的最終阻斷閘門，未通過 `nexus:closeout` 禁止宣告 PASS。 [Source: scripts/ops/closeout_guard.py]

## Role / responsibility
- **完成宣告阻斷**: 要求任務在回報完成前提供可驗證 `done_contract`。 [Source: AGENT_PROTOCOL_v2.md]
- **契約校驗**: 驗證 `linter_exit_code`、`ci_gate_exit_code`、`required_tests_passed`、`commit_sha`、`changed_files`。 [Source: scripts/ops/closeout_guard.py]

## Upstream
- **實作完成階段**: 任務完成後產生 `.nexus/reports/done_contract.json`。 [Source: scripts/engine/nexus_cli.py]
- **協議約束**: `AGENT_PROTOCOL_v2.md` 定義未過 closeout 禁止結案。 [Source: AGENT_PROTOCOL_v2.md]

## Downstream
- **[[Ops - CI/CD Promotion Gate]]**: Closeout 作為 release 前的人機協作最終門檻之一。 [Source: scripts/ops/ci_gate.py]
- **[Ops - Governance Changelog](Ops - Governance Changelog.md)**: 記錄 closeout 規則變動與升級。 [Source: nexus_wiki_vault/06_Ops/Ops - Governance Changelog.md]

## Related modules / files
- `scripts/ops/closeout_guard.py`: done contract 驗證器。
- `scripts/engine/nexus_cli.py`: `nexus:closeout` 指令入口。
- `tests/ops/test_closeout_guard.py`: closeout guard 單元測試。
- `tests/tests/test_cli_commands.py`: `nexus:closeout` CLI 測試。

## Source notes
- 建議標準流程：先完成測試與 CI gate，再執行 `nexus:closeout`。 [Source: docs/ops/closeout_enforcement.md]
- 任何缺失欄位或非零 exit code 均應阻斷完成回報。 [Source: scripts/ops/closeout_guard.py]

## Open questions / conflicts
- [ ] 是否應在 `ci_gate.py` 增加可選 `--require-closeout-contract` 模式以統一入口阻斷。
- [ ] 是否需要將 done contract schema 提升為 JSON Schema 並加入 CI 檢查。
