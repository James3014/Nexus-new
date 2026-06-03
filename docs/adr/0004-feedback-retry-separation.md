# ADR 0004: Feedback 與 Retry Policy 的解耦

## 狀態
已接受 (Accepted)

## 背景
在 v26.6 中，`FeedbackRouter` 同時負責識別失敗模式與決定重試策略。這種耦合使得針對特定領域 (如 Django) 的策略調整會污染通用的回饋邏輯。

## 決策
將回饋管線拆分為二：
1. **Feedback Context**: 只負責將 `VerifierVerdict` 映射為 `FailurePattern` (例如: 缺失 Import)。
2. **Retry Policy Context**: 根據 `FeedbackDirective` 決定最終行動 (例如: 啟動 EXPLORE 模式)。

## 後果
- **優點**: 
  - 資料流更直，特殊情況更易消弭。
  - 策略與模式分離，符合「Good Taste」原則。
- **缺點**: 
  - 多了一層指令傳遞 (FeedbackDirective)。
