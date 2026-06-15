# Nexus Team Update: 3B Shadow Advisor Reaches Review Stage

**Date**: 2026-06-15
**Status**: `READY_FOR_REVIEW` (Limited Mount Review)

團隊好，

針對 `qwen2.5-s2t-advisor:3b` 模型的評估與治理硬化已達成重要 Milestone。目前該模型與治理合約的組合已正式發起 Limited Mount Review PR。

為了確保透明度與防止 Overclaim，以下是本次更新的已驗證事實與明確的掛載邊界聲明：

## 📊 1. 已驗證事實 (Verified Facts)
在最近一輪的 Shadow Evaluation 與 Runtime Contract 驗證中，我們取得了以下實體數據：
- **Eligible Shadow Rows**: 40 筆 (涵蓋 Harder Tasks 與 Abstention 邊界樣本)。
- **Trust Mismatch**: **0** (成功透過 Fail-closed 安全閘消除了 Student-Induced 幻覺)。
- **Override Verified Lift**: 5.0% (相較於 Rule Baseline)。
- **Abstain 行為**: 在證據不足與超預算樣本中正常觸發 `abstain_reason`。
- **Runtime Contract**: `NEXUS_SHADOW_ADVISOR_ENABLED` Feature Flag、$\le 500$ ms 平滑退避機制 (Fallback) 與 27 條 Policy 的 Rollback Drill 皆已 100% 驗證通過。

## 🛡️ 2. 審查邊界與掛載範圍 (Governance & Boundaries)
本次送審的目標僅限於 **Shadow/Advisor Limited Mount**，並非申請進入 Runtime Default。

### ✅ Allowed First Mount (核准的實驗性掛載點)
- **Strict-gated repair nodes** (作為修復節點的限權顧問)
- **Route-review nodes** (作為路由審查的輔助觀測)

### 🚫 NOT Allowed (絕對禁止越權的領域)
為了維持主路徑 (Main Path) 的權威性，3B 模型在當前階段 **絕對不允許** 進行以下操作：
- **Router Replacement** (不可取代分流決策)
- **Verifier Replacement** (不可取代證據驗證器)
- **Public Claim Gate Replacement** (不可取代對外聲明放行閘)
- **Automatic Policy Mutation** (不可自動修改治理策略)
- **Runtime Default Change** (Python Route 與 Verifier 仍保有絕對 Authority)

本次推進證明了「模型能力 + 嚴格治理合約」的結合可達到安全水位，但距離完全取代既有邏輯仍有明確邊界。完整的測試證據與 Redaction 報告請參閱 PR 中的 Approval Dossier。
