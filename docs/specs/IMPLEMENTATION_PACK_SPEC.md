# 📜 Nexus vNext: Implementation Pack Specification (v1.0)

## 1. 概述
本規範定義了 Nexus 編譯器從 Phase P (Plan) 產出的硬性實作包格式。其核心目標是消除 Agent 在實作階段的「腦補」行為，確保 100% 的可施工性。

## 2. 核心工件 (Core Artifacts)
每個任務必須產出以下位於 `.nexus/runs/{task_id}/implementation/` 的檔案：

### 2.1 implementation_pack.json
定義施工範圍與責任。
```json
{
  "task_id": "UUID",
  "goal": "精準目標敘述",
  "task_type": "ui|backend|fullstack",
  "data_models": [],
  "ui_blocks": [],
  "deliverables": [],
  "acceptance_targets": []
}
```

### 2.2 source_of_truth_map.json
定義哪些數據欄位是「真值」，哪些是「衍生值」。
- **Rank 1**: audit_result.json (實體測試結果)
- **Rank 2**: acceptance_check.json (門禁判定)

### 2.3 decision_formula.json
定義系統判定的邏輯公式，如 `can_publish = acceptancePassed && auditPassed`。

## 3. 稽核門禁 (Readability Gate)
所有實作包必須通過 3 秒判讀稽核：
- **Score > 90**: 准予動工。
- **Score > 95 & Jargon=0**: 自動執行 `git tag spec-vX.Y` 封版。

## 4. 異常處理 (Fallback)
若編譯失敗，系統必須退回 Phase P 進行 Interview，不得強行進入實作。
