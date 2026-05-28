# Nexus 至高主循環規範 (Supreme Master Loop Spec)
[PROTOCOL: P-X-D-R-A-C v3.0 ADVANCED]

## 🔄 核心循環流程
Nexus 的執行必須嚴格遵守以下由 v3.0 增強的七階段循環：

1. **[S] Sense**: 物理環境預檢與指紋收集。
2. **[P] Plan**: 由 \`CapabilityPlanner\` 產出中心化路由決策。
3. **[X] Execute**: 透過 \`LeaseWorktree\` 在隔離區執行任務。
   - **NEW: Rescue Stage**: 若本地 Reflex 解析失敗，自動觸發 \`rescue_with_model_fallback\`。
4. **[D] Deliver**: 產出初步執行證據。
5. **[R] Report**: 生成正式的技術收據。
6. **[A] Audit**: 透過 \`HallucinationGuard\` 進行語意一致性查核。
7. **[C] Closure**: 將教訓寫回 \`Learning Closure Matrix\`，完成閉環。

## 🛡️ 實體合約
- **Hybrid Winner**: 當發生 Rescue 成功時，系統必須記錄混合成本證據，以修正 Token 效率計量。
