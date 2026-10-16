# Real Model Solve Report (v0)

本報告彙整了本地真實 Qwen/Ollama 模型的微型解題軌道（Real Qwen/Ollama Small Task Lane）的初步執行言證與 Nexus Armor 防線適配結果。

---

## 🗣️ 實際執行言證（P36-P39 First Run Evidence）

```
lane_executed         = true
model_called          = true
selected_candidate_hash_present = true  (3339245c...)
solved                = false
route_mode            = local_only_blocked
verifier_status       = blocked
block_reason          = SEARCH_MISMATCH / target_file_mismatch / constraint_violation
```

**結論**：  
Nexus Armor 正確阻斷了 Qwen 產生的無效 diff。真實解題尚未達成。  
This is **real-model blocked evidence**, not a solve success.

---

## 🚀 測試架構設計

測試軌道： [test_real_ollama_solve_lane.py](file:///Users/jameschen/Workspace/nexus/tests/integration/test_real_ollama_solve_lane.py)

1. **題目設計 (Factorial Bug)**:
   - 建立 factorial 遞迴階乘函數，故意植入 `return n * factorial(n - 2)` 的 Bug (應為 `n - 1`)。

2. **定位引導 (Source Anchoring) & 顯式 Prompt**:
   - `locked_search = "return n * factorial(n - 2)"`。
   - `LocalHealCapabilityAdapter` 建構了 explicit patch prompt：要求以標準 ` ```diff ` block 回傳 unified diff、禁止 prose 說明、限定只修改 locked search span。

3. **Ollama Tag 修形**:
   - `is_ollama_model_available` 改為 `find_ollama_model(prefix)`，回傳完整 tag name（如 `qwen2.5-coder:7b`），修影 `/api/generate` 就 HTTP 404 的問題。

4. **防漏接斷言 (Infrastructure vs Content Blocker)**:
   - 測試雅続脾斷：只要 Ollama 在線，就斷言 `local_model_not_called 不得在 block_reason` 中。
   - 如果 `route_mode == local_only_blocked`，斷言所有 blocker 必須在 content / derived fail-closed 允許清單內，不得出現基礎設施録誤（`ollama_http_error`, `model_name_missing`, `provider_not_configured` 等）。

---

## 🛡️ Nexus Armor 對真實模型的物理防禦價值

- **越界寫入阻斷 (Locked Span Check)**：若模型因幻覺或模糊匹配而改動了指定 locked span 以外的程式碼，會被 `patch_outside_locked_span` 直接擋下。
- **Target File Constraint**：若 diff header 中的 `+++ b/<file>` 與指定目標檔不符，會被 `target_file_mismatch + SEARCH_MISMATCH` 正確阻斷。
- **Hash 校驗與憑證完整性**：實際 apply 的 hash 會經過 `git diff` 獨立抽取並重新計算，不允許模型自行捏造。

---

## 📈 下一步規劃（P40-P43 Real Qwen Diff Contract Hardening）

1. **Prompt 進一步強化**：在 prompt 裡強制 header 格式：`--- a/f.py` / `+++ b/f.py`，減少 `target_file_mismatch`。
2. **Output Repair Normalizer**：若模型用了错誤的 target path，但 hunk / locked span 可驗證，先不要直接 apply。產生 `normalized_candidate`，重新經 source anchor / hash / verifier gate。
3. **不得繞過 `target_file_mismatch`**： normalizer 必須有 receipt：`original_target_file`、`normalized_target_file`、`normalization_reason`、`normalized_by_rule`。
