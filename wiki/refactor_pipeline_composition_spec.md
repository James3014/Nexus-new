# 深化建議：NexusPipeline 從 Mixins 轉向組合模式重構規格 (v25.5)

## 1. 目標
將 `NexusPipeline` 重構為基於插件（Plugin）的組合架構，以實現文檔要求的強邊界隔離與動態治理。

## 2. 重構要點

### 2.1 定義 PhaseExecutor 介面
建立抽象類別 `PhaseExecutor`，規範所有階段必須實作的方法：
*   `can_execute(ctx: PipelineContext) -> bool`
*   `run(ctx: PipelineContext) -> PhaseResult`

### 2.2 職責拆分 (Decoupling)
將目前的 Mixins 拆分為獨立的執行器對象：
*   `PlannerPhase` (原 PipelineStagesMixin)
*   `ResearchPhase` (原 PipelineResearchMixin)
*   `DiagnosePhase` (原 PipelineRepairMixin 部分)
*   `CrystallizePhase` (原 PipelineCrystalMixin)

### 2.3 動態註冊與調度
`NexusPipeline` 不再繼承具體邏輯，而是作為一個「外殼」：
```python
class NexusPipeline:
    def __init__(self, engine):
        self.phases: List[PhaseExecutor] = [
            StartPhase(), PlanPhase(), ResearchPhase(), ...
        ]
    
    def run(self, ctx: PipelineContext):
        for phase in self.phases:
            if phase.can_execute(ctx):
                phase.run(ctx)
```

## 3. 預期效益
*   **強大邊界**：每個階段的 Input/Output 被嚴格限制在 `run` 方法中。
*   **可觀察性**：`OneBitGate` 可以在各 Executor 之間進行顯式的攔截與審核。
*   **Locality**：修復單一階段的 Bug 不再需要查閱多個 Mixin 檔案。

---
*存檔日期：2026-05-04*
*執行代理：Gemini Nexus Engineer*
