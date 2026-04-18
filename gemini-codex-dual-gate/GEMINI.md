# 🛡️ gemini-codex-dual-gate Extension Guidelines

## 核心流程
1. `/plan-with-codex`: 生成計劃並由 Codex 審核。
2. `/implement-from-plan`: 根據已核准計劃進行實作。
3. `/gemini-self-review`: 第一閘，呼叫官方 code-review。預設使用 `gemini-3.1-pro-preview` 模型（可透過 `GEMINI_MODEL` 覆蓋）。
4. `/codex-final-audit`: 第二閘，High-Bar Acceptance Gate。預設使用 `gpt-5.4` 模型（可透過 `CODEX_MODEL` 覆蓋）。
   - **AC 強制編號**：`.ai/acceptance.md` 必須有 AC-1..AC-N 編號，否則直接 BLOCKED。
   - **測試證據**：`.ai/test-results.md` 必須含可重跑命令與結果，否則直接 REVISE。
   - **門檻門戶**：有 CRITICAL/重大計劃偏離 => BLOCKED；有 HIGH/AC=FAIL/證據弱 => REVISE；僅 MED/LOW 且 AC 全 PASS => PASS。

## 強制規則
- 無 `PLAN_APPROVED` 不可實作。
- `PLAN_DRIFT=true` 必回 plan 階段。
- 無 `test-results.md` 禁 final audit。
- 不得自行宣告 merge-ready。
- 凡 `REVISE/BLOCKED` 都要追加 `.ai/lessons.md`。
