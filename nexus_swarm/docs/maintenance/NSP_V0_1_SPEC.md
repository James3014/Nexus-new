# NSP_V0_1_SPEC (Nexus Sensing Protocol)

## 用途
NSP 是 Swarm Manager 與 Node 之間進行標準通訊的核心協定，基於 gRPC-Ready 的語意設計。

## 核心通訊契約
- **SensingRequest**:
  - `task_id`: 任務唯一識別碼。
  - `path`: 目標檔案路徑。
  - `traceparent`: W3C TraceContext Header。
- **DiagnosticReport**:
  - `status`: 健康狀態 (HEALTHY/FAILED/SECURITY_VIO)。
  - `summary`: 任務摘要日誌。
  - `metrics`: 階段執行耗時 (ms)。

## Trace Context 規範
所有實現 NSP 的節點必須正確傳遞與解析 `traceparent`。
範例：`00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01`

## 向後相容規則
- 不得移除未經 Deprecation 程序的現有欄位。
- 新增欄位必須設定為可選。
