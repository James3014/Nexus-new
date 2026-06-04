# ADR 0010: v27 治理規格書與 Manifest 鎖死

## 狀態
已接受 (Accepted)

## 背景
Nexus v27 的核心目標是「治理一類系統」。若 `TaskManifest` 的准入規則不夠嚴格，新領域 (Cross-Domain) 的接入可能會繞過現有的證據鏈與晉升門檻，導致治理效力退化。

## 決策
實施 `ManifestValidator` 進行「強型別治理」：
1. **准入鎖死**: 任何接入的任務必須具備明確的 `domain_id` 與 `verifier_pack_id`。
2. **車道約束**: `lane` 僅限於 `baseline` (守成)、`challenge` (攻堅) 與 `migration` (遷移)。
3. **政策對齊**: `promotion_policy` 必須在全域策略註冊表中，嚴禁硬編碼的分支。
4. **資料完整性**: `migration` 車道任務必須具備 `extension_metadata`，以支持跨域量測。

## 後果
- **優點**: 
  - 物理封殺非法題庫入場。
  - 確保了 v27 「入場 -> 驗證 -> 晉升」的閉環完整性。
  - 系統具備了「自我診斷規格」的能力。
- **缺點**: 
  - 新增題庫的門檻提高，需要更詳盡的元數據。
