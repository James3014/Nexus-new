# ADR 0014: 物理收據規範 (Rollback-Safe Promotion Receipt)

## 狀態
草案 (Draft)

## 背景
晉升判定不能只存在於記憶體中，必須物理化以支持回退與重播審計。

## 決策
定義標準化 `PromotionReceipt` 與 `RejectionReceipt`：
1. **收據完整性**: 必須包含 `input_manifest_hash`、`candidate_id`、`governance_verdict`、`evidence_seals`。
2. **重播合約 (Replay Contract)**: 收據必須包含足夠的元數據，讓 `ReceiptReplayer` 在脫機環境下能得出與當初相同的晉升決策。
3. **原子回退**: 若 `SealedEvidence` 寫入持久層失敗，利用收據鎖定狀態，防止 Manifest 進入不對稱狀態。

## 後果
- **優點**: 提供物理級別的可審計性。
- **缺點**: 增加資料存儲量。
