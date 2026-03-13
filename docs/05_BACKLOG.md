# Muse-Nexus Backlog

## Now

- [ ] 確認 `scripts/` 中哪些檔案是現役、哪些是歷史殘留
- [ ] 定義 `.muse_state` 最小 schema
- [ ] 決定 Commander v1 的 CLI 入口
- [ ] 決定 Context Hub 第一版只支援哪些 context source
- [ ] 決定 `diagnosis.json` 最小必要欄位
- [ ] 決定 `repair_final.json` 最小必要欄位
- [ ] 決定 `audit_result.json` 最小必要欄位

## Next

- [ ] 抽離 `codex_loop_brain.py` 內的 context assembly
- [ ] 建立 `trace_log.jsonl` 事件格式
- [ ] 將 `super_plan_v2.py` 升級成可輸出 `plan.json`
- [ ] 將 `drclaw_diagnosis.py` 升級成穩定 contract 輸出
- [ ] 將分散 audit 腳本整理成單一 Audit engine

## Later

- [ ] 導入 `research_pack.json`
- [ ] 導入 external research gating
- [ ] 導入 `skills_router.py`
- [ ] 導入 reflection memory round schema
- [ ] 導入 crystal lesson 與任務結果的對齊流程

## Repo Hygiene

- [ ] 決定是否保留 `scripts/_migrated_from_obsidian/`
- [ ] 決定是否保留 duplicated `scripts/core/` 與 root-level scripts
- [ ] 決定 pycache / local env / local trees 的忽略策略
- [ ] 建立最小開發手冊與執行入口文件

## Management Notes

- 文件先行，避免藍圖只留在對話中
- 每完成一個 phase，都要同步更新文件
- 如果未來由不同人實作，先以 contract 與 docs 對齊，不先爭論實作細節
