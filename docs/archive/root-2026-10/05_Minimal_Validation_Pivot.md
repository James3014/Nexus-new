[NEXUS v26 BOOTSTRAP-CANDIDATE]

# Nexus v1.1 Skeleton 訓練排障與最小驗證策略 (Pivot)
**Date: 2026-06-02**
**Status: PIVOTING to Minimal Validation**

## 1. 當前狀況摘要
- **Rust 感知底座**: `nexus_core` (FastMatcher) 已穩定，Shadow Mode 掃描對位成功 (`Count: 7043`)。
- **7B Skeleton 訓練**: 目標將骨架語義內化至 `Qwen2.5-Coder-7B-Instruct`。
- **核心阻礙**: 本機 M4 16GB RAM/IO 不穩，即使超保守配置也發生 `OSError [Errno 9]` 或系統流初始化失敗。
- **決策**: 停止完整 LoRA 訓練。轉向 **「訓練前執行鏈排障」**。

## 2. 三段式排障流程
1. **最小驗證 (Minimal Validation)**: 
   - 僅執行：Model Load -> Dataset Load -> Single Forward -> Schema Emit -> Exit。
   - 目標：確定執行鏈是否能在不進入 Optimizer 的情況下穩定。
2. **分段訓練 (Phased Step)**: 
   - 若最小驗證穩定，嘗試 1-10 steps 的微型訓練。
3. **離線/縮減策略 (Off-machine/Scale-down)**:
   - 若最小驗證不穩，判定本機環境不適配 7B LoRA，轉向 1B/3B 模型或雲端訓練。

## 3. 禁令與限制
- **禁止**: 完整 LoRA 訓練、高 I/O 監控 (Shadow/Benchmark 同時跑)。
- **保留**: Rust 感知層、回歸測試。

## 4. 下一步行動
- [ ] 撰寫 `scripts/ops/minimal_7b_val.py` 進行最小載入測試。
- [ ] 記錄失敗點分類 (Load/Dataset/Forward/System)。

---
[NEXUS IDENTITY: 75a897ad3 + v2.9 RUNTIME-ALIGNED]
