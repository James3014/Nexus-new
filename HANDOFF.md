# HANDOFF

更新：2026-10-11 · by Claude · HEAD `450cad9e9`
<!-- 規則見 docs/agents/HANDOFF_PROTOCOL.md。上限 150 行；過期內容移到 docs/archive/HANDOFF-YYYY-MM.md。 -->

## ▶ 下一步（只放一件，必須帶 #Issue）
#1773 讓 PR #1774（activation push 以 `gh variable delete` 套用空值、readback 視缺席為 `""`）通過檢查並落地——依據：V11 host run 停在 runbook step 3（manifest push exit 3），直接阻塞 #1216 的 activation；Owner 已核准 option b，今天建立。

## 進行中
- #1773 / PR #1774：修正已提出；目前 Trusted verifier、Nexus Core issue completion/run、Exact-base Ruff 四項檢查紅燈，mergeable_state=blocked。
- #1216：V11（`AGY_GEMINI_3_8_FLASH_MEDIUM_V11`）step 0–2 通過、凍結 SHA `895e5388`，等 #1773 修好後從 step 3 續跑。
- #1580 / PR #1775：guard-delta job 首次實跑沒有產出 artifact（`GITHUB_REPOSITORY_ID` 被覆寫成數字 id）；PR 改用 `RI_REPOSITORY`，檢查進行中。
- #1579：RIE knowledge manifest 與 producer CLI 已併入（#1772），issue 仍開著，待確認後續消費端。
- #1757、#1758、#1760 等 invariant gap / PR #1768：2026-10-11 invariant 覆蓋稽核的修正與稽核證據，檢查進行中，blocked。
- #1733 / PR #1767：能力接線收尾（#1734、#1735、#1737、#1738、#1739、#1741 與 #1763 第 1–5 項），Owner 授權走 DIRECT_CANONICAL，檢查進行中，blocked。

## 待確認（沒有 Issue 號）
- 10/05–10/08 有一批舊 open PR 長期無活動（如 #1437、#1447、#1583 與 #1584 head 是同一個 SHA），是否關閉或重做待 Owner 決定。
- PR #1768 之外，invariant gap issue #1749–#1761 仍帶 `needs-triage`，尚未分 lane。

## 卡住 / 注意
- 共 124 張 open issue，大量為 `needs-triage`；#1763 列的 fail-open 閘門、replay 不重跑等項目需要 governed lane 或 Owner 決策。
- #1216 是研究觀察（`RESEARCH_OBSERVATION_ONLY`），不授予工程權限；凍結 runtime 綁定 `895e5388`，operator 工具要從目前的 `main` 執行。
- 本 repo 是 Legacy Integration Lab / Compatibility Host，Core、Learning、Open SWE 的 canonical 實作已移到各自的 repo。
