# 🛡️ Nexus v1.1 訓練轉向公告：系統穩定性優先 (Stabilization Pivot)

## ⚠️ 緊急修訂：降載觀測
由於 M4 16GB 設備在啟動 7B 模型訓練時出現系統壓力過載（Bad file descriptor / init_sys_streams 錯誤），決定採取**分段降載策略**。

## 1. 調整後的策略
- **Ultra-Safe Smoke Run**: 先進行 2 steps 測試，驗證模型載入與啟動穩定性。
- **Context 降級**: 暫時將 `max_seq_length` 從 4096 降至 1024。
- **層級縮減**: 僅針對最後 4 層進行 LoRA 微調，降低 VRAM 峰值。
- **前景執行**: 取消背景執行模式，改為單獨前景進程以防標準流損壞。

## 2. 暫停項目
- 暫停所有 **Shadow Mode** 與 **Dual-Run** 指標監測。
- 暫停 **Benchmark** 任務，確保 MLX 獨占系統資源。

## 3. 目標
先救機器穩定性，確保「能啟動且不當機」，再逐步恢復至 200 steps 規模。
