# 🧪 Integrated Testing Gauntlet (L1-L7)
**[PHYSICAL_STATUS: REGRESSION_AWARE | COVERAGE_MONITORED]**

## 1. 測試矩陣與回歸防護
Nexus 使用橫跨 L1 (Unit) 到 L7 (E2E) 的「測試手套 (Gauntlet)」進行全方位核驗。

## ⚙️ 實體化測試規約
- **失敗模擬 (Monkeypatching)**: 廣泛使用 Monkeypatch 模擬服務宕機、配額耗盡等異常。
- **回歸探針**: 每個 Bug 修復後，必須建立同名的「墓碑測試」，防止死灰復燃。
- **覆蓋率監視**: 整合 `pytest-cov`，由 `ci_gate.py` 自動解析 coverage 報告，實施物理覆蓋率門檻。
- **測試空間**: 採用 `tests/unit`, `tests/integration`, `tests/e2e` 標準命名空間。

## 2. 核心指標
- **Mutation Coverage**: 確保測試用例能有效攔截錯誤修改。
- **Fail-Fast**: 任何單一測試失敗，全管線立即進入 BURSTING 狀態。

---
**[Source: New Dimension Audit Batch D - 2026-04-20]**
