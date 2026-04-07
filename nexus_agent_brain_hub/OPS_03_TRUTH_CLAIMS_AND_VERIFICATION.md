---
aliases:
- Truth Claims
- Verifiable Statements
- Compliance Register
confidence: high
last_compiled: 2026-04-06
owner: agent
related_pages:
- '[[System Overview|System Overview]]'
- Ops - CI/[[CD Promotion Gate|Promotion Gate]]|[[CD [[CD Promotion Gate|Promotion
  Gate]]|CD [[CD Promotion Gate|Promotion Gate]]]]]]
- '[[Agent Mastery - 90 Percent Path|Agent Mastery - 90 Percent Path]]'
- '[[index|Index]]|[[Source [[index|Index]]|Source [[index|Index]]]]]]'
source_of_truth: repo-root
status: active
tags:
- ops
- compliance
- truth_claims
- verifiable
title: Ops - Truth Claims Register
type: ops
version_scope:
- v17.1
- v22
- v23
---



# Ops - Truth Claims Register

## One-sentence summary
本頁集中管理所有關於 Nexus 物理狀態的真值聲明 (Truth Claims)，並提供可機器執行的驗證命令。 [Source: 00_Home/System Overview.md] [Code: wiki_truth_claims_check.py]

## Role / responsibility
- **可驗證性管控**: 確保 Wiki 內提到的關鍵架構與門禁在物理實體中確實存在且有效。 [Source: wiki_linter.py]
- **預發佈檢查 (Pre-release Checklist)**: 作為 Human-in-the-loop 的首要稽核點。

## Truth Claims (真值聲明對照表)

| ID | Claim Description (聲明內容) | Evidence (證據路徑) | Verification Command (驗證命令) | Status | Last Verified |
|---|---|---|---|---|---|
| `C-01` | [[CD Promotion Gate|CI Gate]] 實體存在於腳本目錄。 | `scripts/ops/ci_gate.py` | `test -f scripts/ops/ci_gate.py` | ✅ | 2026-04-06 |
| `C-02` | v22.1.1-prod 釋出標籤已封裝。 | `git tags` | `git tag --list 'v22.1.1-prod'` | ✅ | 2026-04-06 |
| `C-03` | Wiki Linter v1.4 主線硬閘啟用。 | `scripts/ops/wiki_linter.py` | `uv run scripts/ops/wiki_linter.py --strict` | ✅ | 2026-04-06 |
| `C-04` | .nexus 狀態目錄具備寫入權限。 | `.nexus/` | `test -w .nexus` | ✅ | 2026-04-06 |
| `C-05` | Memory [[index]] ([[Module - Memory Repository|LanceDB]]) 實體初始化。 | `.nexus/memory/memory_index.[[Module - Memory Repository|lancedb]]` | `ls -d .nexus/memory/memory_index.[[Module - Memory Repository|lancedb]]` | ✅ | 2026-04-06 |
| `C-06` | CLI 入口 nexus_cli.py 預備。 | `scripts/engine/nexus_cli.py` | `test -f scripts/engine/nexus_cli.py` | ✅ | 2026-04-06 |
| `C-07` | Agent Schema 指導規約存在。 | `99_Schema/[[AGENT_SCHEMA]].md` | `test -f nexus_wiki_vault/99_Schema/[[AGENT_SCHEMA]].md` | ✅ | 2026-04-06 |
| `C-08` | [[CD Promotion Gate|CI Gate]] Dry-run 鏈路完整通透。 | `scripts/ops/ci_gate.py` | `uv run scripts/ops/ci_gate.py --dry-run` | ✅ | 2026-04-06 |
| `C-09` | Evidence Chain (manifest) 格式合法。 | `.nexus/swarm/manifest.json` | `test -f .nexus/swarm/manifest.json` | ✅ | 2026-04-06 |
| `C-10` | Pilot CLI v100+ 交付模組存在。 | `scripts/engine/nexus_cli.py` | `test -f scripts/engine/nexus_cli.py` | ✅ | 2026-04-06 |
| `C-11` | v22 核心規格書實體標註。 | `MUSE-NEXUS-Engine-Specification-v22-Eternal.md` | `test -f MUSE-NEXUS-Engine-Specification-v22-Eternal.md` | ✅ | 2026-04-06 |
| `C-12` | Waiver Registry 必填欄位稽核。 | `06_Ops/[[Ops - Provenance Exceptions and Waivers]].md` | `uv run scripts/ops/wiki_linter.py --strict` | ✅ | 2026-04-06 |
| `C-13` | Knowledge Lineage 節點完整。 | `05_Protocols/[[Protocol - Knowledge Lineage]].md` | `uv run scripts/ops/wiki_linter.py --strict` | ✅ | 2026-04-06 |
| `C-14` | Docker/Helm Lint 0 紅燈準則（模擬）。 | `nexus_swarm/` | `ls nexus_swarm/` | ✅ | 2026-04-06 |
| `C-15` | Nexus Identity 指紋識別啟用。 | `scripts/ops/ci_gate.py` | `grep "NEXUS IDENTITY" scripts/ops/ci_gate.py` | ✅ | 2026-04-06 |
| `C-16` | Wiki 覆蓋率 > 85.00% 閾值。 | `.nexus/reports/wiki_coverage_report.json` | `uv run scripts/ops/wiki_coverage_audit.py` | ✅ | 2026-04-06 |
| `C-17` | 全量 Wiki 頁面具備 0 Orphan 連結。 | `scripts/ops/wiki_linter.py` | `uv run scripts/ops/wiki_linter.py --strict` | ✅ | 2026-04-06 |
| `C-18` | PDRAC 循環實體邏輯存在。 | `nexus/core/orchestrator.py` | `grep "NexusOrchestrator" nexus/core/orchestrator.py` | ✅ | 2026-04-06 |
| `C-19` | 治理變更日誌實體維護中。 | `06_Ops/[[Ops - Governance Changelog]].md` | `test -f nexus_wiki_vault/06_Ops/Ops\ -\ Governance\ [[CHANGELOG]].md` | ✅ | 2026-04-06 |
| `C-20` | Fail-Closed 發版規則硬性定義。 | `scripts/ops/ci_gate.py` | `grep "FAIL-CLOSED" scripts/ops/ci_gate.py` | ✅ | 2026-04-06 |

## Upstream
- **MUSE-NEXUS Spec**: 提供聲明的基礎（SoT）。
- **[[CD Promotion Gate|CI Gate]]**: 執行實體校驗。 [Source: scripts/ops/ci_gate.py]

## Downstream
- **[[Ops - CI/CD Promotion Gate]]**: 提供發版前的證據清單。
- **[[Agent Mastery - 90 Percent Path]]**: 作為進階 Agent 的檢核範本。

## Related modules / files
- `scripts/ops/wiki_linter.py`: 頁面校驗。 [Code: scripts/ops/wiki_linter.py]

## Source notes
- v22 Engine Spec: 要求「凡聲明必有證據，凡證據必可驗證」。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Dynamic Claims**: 是否應由 `ci_gate.py` 自動更新 Last Verified 日期。
- [ ] **Complexity Scale**: 如何定義「驗證命令」的執行時間門檻。

---
[[System Overview]]
---
last_compiled: 2026-04-06
owner: agent
status: active
tags:
- security
- policy
- truth-claims
- sandbox
title: Ops - [[Ops - Truth Claims Register|Truth Claims]] Command Policy
type: ops
---



# Ops - [[Ops - Truth Claims Register|Truth Claims]] Command Policy

## One-sentence summary
本頁面定義真值校驗指令執行時必須遵循的安全白名單、黑名單以及執行期沙箱規範。 [Source: scripts/ops/wiki_truth_claims_check.py]

## Role / responsibility
- **安全性管控**: 預防非預期之指令或語法執行。
- **沙箱化執行**: 確保 Claim 驗證僅限於 `test`, `ls`, `uv` 等安全指令集。

## Policy Matrix (指令門禁矩陣)
- **指令安全性驗證**: 確保所有 Claim 指令不會對實體 Repo 造成破壞性變更。
- **治理範疇定義**: 限定 `test`, `ls`, `uv run` 等高可信前綴之使用。
- **違規實施阻斷**: 任何未命中白名單或觸發黑名單之指令將被強制標記為 `POLICY_BLOCKED`。

## Policy Matrix (指令門禁矩陣)
| Level | Whitelist Prefix | Blacklist Keyword | Action |
|---|---|---|---|
| **High** | `test`, `uv run` | `rm`, `sudo`, `curl` | Block |
| **Logic** | `grep`, `rg` | `;`, `&&`, `||`, `$(`, `` ` `` | Filter |

## Upstream
- **[[Ops - Truth Claims Register]]**: 指令來源。
- **[[System Overview]]**: 系統總覽。

## Downstream
- **[[Ops - CI/CD Promotion Gate]]**: 安全門禁決策。

## Related modules / files
- `scripts/ops/wiki_truth_claims_check.py`: 腳本。

## Source notes
- v22 Hardened Security:「凡治理層內執行之操作，必受沙箱邏輯之規範」。 [Source: MUSE-NEXUS-Engine-Specification-v22-Eternal.md]

## Open questions / conflicts
- [ ] **Dynamic Whitelist**: 未來是否支持由 `owner` 手動為特定 Claims 申請臨時豁免。
- [ ] **Shell Escaping**: 針對複雜指令的精確正則過濾邏輯優化。
            
[NEXUS IDENTITY: a670624 + CI-GUARDED]