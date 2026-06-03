# ADR 0001: Selection 與 Search Context 的物理拆分

## 狀態
已接受 (Accepted)

## 背景
在 Nexus v26 之前的版本，`CommitteeController` 同時負責候選者的產生 (Sampling) 與最終獲勝者的選優 (Selection)。隨著題庫規模擴大 (v60)，這種「巨石編排器」導致了棄權邏輯與重試策略互相耦合，難以針對 `coverage_low` 或 `selection_low_confidence` 進行定向修復。

## 決策
將 `Search` 與 `Selection` 拆分為獨立的 Bounded Contexts：
1. **Search Context**: 專注於生成、攪拌 (Shuffling) 與多樣性量測。
2. **Selection Context**: 專注於分數聚合、棄權政策與置信度校準。
3. **Orchestration**: `CommitteeController` 僅作為純淨的編排層，透過標準 DTO 驅動上述兩大 Context。

## 後果
- **優點**: 
  - 可單獨針對 `DiversityMeter` 進行演算法升級。
  - `AbstainPolicy` 可在不影響採樣策略的前提下進行校準。
  - 架構測試 (Architecture Tests) 可物理封鎖 Context 間的非法滲透。
- **缺點**: 
  - 增加了一定數量的 DTO (contracts.py)。
