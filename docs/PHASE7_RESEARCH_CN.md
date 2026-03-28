# Phase7 研究入口（Autoresearch + Skills Autotune）

## 目的
一鍵串接兩段研究流程：
1. `phase6`：Autoresearch / Hardening 驗證
2. `skills-autotune`：根據技能路由決策做權重調整

## 指令
```bash
python3 scripts/engine/nexus_cli.py nexus:phase7 \
  --workspace /Users/jameschen/Downloads/obsidian/01_Projects/Autoresearch \
  --rounds 100 \
  --proof-ratio-min 95 \
  --output-prefix phase7 \
  --autotune-apply
```

## 主要輸出
- `workspace/<output-prefix>_research_report_cn.json`（phase6 報告）
- `workspace/<output-prefix>_phase7_report_cn.json`（phase7 匯總）
- `.nexus/metrics/skills_autotune_report.json`（調參報告）
- `scripts/core/autonomic_weights.json`（套用時更新）

## 研究建議
先用 `--skip-autopilot` 快速驗證接線，再跑完整輪次。
