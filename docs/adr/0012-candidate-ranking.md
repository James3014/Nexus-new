# ADR 0012: 晉升候選排序規則 (Candidate Ranking)

## 狀態
草案 (Draft)

## 背景
當多個策略在 Challenge Lane 表現良好時，需要一套決定性的排序邏輯來選擇晉升對象。

## 決策
實施確定性候選排序邏輯：
1. **主排序標的**: `Evidence Quality` (驗證收據完整性 + 遙測覆蓋度)。
2. **次排序標的**: `Oracle Gap Recovery Rate` (回收率淨值)。
3. **加權項**: 
    - `Domain Diversity`: 優先晉升能解決新失敗模式 (Failure Family) 的策略。
    - `Complexity`: 在同等回收率下，優先選擇複雜度更低、依賴更純淨的策略。

## 後果
- **優點**: 晉升過程具備可預測性 (Deterministic)。
- **缺點**: 排序權重可能隨領域變化需要微調。
