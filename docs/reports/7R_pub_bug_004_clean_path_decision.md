# 7R pub-bug-004 第四條 Clean Replay 路徑決策報告

本報告為 Phase C 交付物，有紀律地研判是否存在第四條可審計的 recovery clean path，以決定正式 exclusion 還是重新 combine。

---

## 🔍 四類候選路徑系統化檢算

### 1. **Direct-only accounting repair path**
- *檢算結果*: **🔴 FAILED**
- *原因*: 本列之 unmeasured tokens 源自 sandbox API gateway 對與 with-Nexus arm telemetry 的物理截斷，非單純的 telemetry 漏計。若強行使用 row-keyed refill，將導致 with/without arm 雙向 denominator 帳務失真，破壞 SSOT 潔淨度。

### 2. **Longer timeout but still model-causal path**
- *檢算結果*: **🔴 FAILED**
- *原因*: 延長 timeout 無法消除 model calls 遙測的缺失，更會加劇 Gateway 物理超時，最終依舊會被 direct-arm timeout threshold 阻斷以保護 paired baseline 分母。

### 3. **Route-policy classification issue**
- *檢算結果*: **🔴 FAILED**
- *原因*: 經核對 `derive_cost_evidence_class` 核心合約，該 row 的 active model rescue 屬實，必須被 cost classification 判定為 `model_attempt_runner_overhead_polluted` 或 `token_unreliable`，判定邏輯無 classification 漂移或誤判。

### 4. **Provider variance only, not logic failure**
- *檢算結果*: **🔴 FAILED**
- *原因*: 該 row 本身在 local delivery 與 measured provider tokens 間存在本質上的時序和因果衝突（local 執行必破壞 idempotency 隱藏檢驗，API 執行必丟失 telemetry），非單純 capture 邊界的 variance 問題。

---

## ⚖️ 最終決策與判定結果
- **有沒有第四條 clean replay path?**: **🔴 No**
- **結論 (Verdict)**: **`exclusion_recommended` (建議正式 exclusion 隔離，維持 8R Blocked)**

---
*Clean Path Decision Created: 2026-05-29 (Phase C Complete)*
