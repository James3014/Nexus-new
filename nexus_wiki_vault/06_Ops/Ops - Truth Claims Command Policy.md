---
title: Ops - Truth Claims Command Policy
type: ops
status: active
tags: [security, policy, truth-claims, sandbox]
last_compiled: 2026-04-06
owner: agent
---

# Ops - Truth Claims Command Policy

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
- v22 Hardened Security:「凡治理層內執行之操作，必受沙箱邏輯之規範」。 [Source: Spec v22]

## Open questions / conflicts
- [ ] **Dynamic Whitelist**: 未來是否支持由 `owner` 手動為特定 Claims 申請臨時豁免。
- [ ] **Shell Escaping**: 針對複雜指令的精確正則過濾邏輯優化。
            
[NEXUS IDENTITY: a670624 + CI-GUARDED]
