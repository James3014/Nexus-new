---
id: developer_prompt_v2
type: doc
status: active
created: 2026-04-07T07:29:39Z
updated: 2026-04-07T07:29:39Z
owner: nexus-core
tags: [nexus, governance]
governance: Trident 3.0
ci_hash: pend-audit
soul_alignment: harmonized
priority: P2
version: v1.0.0
visibility: internal
landscape: structural
path: nexus_wiki_vault/06_Ops/Reference/scripts/Templates/developer_prompt_v2.md
---
Waiver: 00_Home/[[System Overview]].md
[source: 00_Home/[[System Overview]].md]
## One-sentence summary
- Pending detailed [[documentation]].

## Role / responsibility
- Pending detailed [[documentation]].

## Upstream
- Pending detailed [[documentation]].

## Downstream
- Pending detailed [[documentation]].

## Related modules / files
- Pending detailed [[documentation]].

## Source notes
- Pending detailed [[documentation]].

## Open questions / conflicts
- Pending detailed [[documentation]].

---
你是一位頂尖的資深軟體工程師與架構師。請審核以下程式碼變更（diff）。
你的任務是識別潛在的 Bug、架構壞味道、靈魂協議違規（Soul Protocols）以及安全性風險。

[CRITICAL REQUIREMENT]
請嚴格遵守以下格式規範，必須且只能輸出單一、有效的 JSON 物件。
絕對禁止在 JSON 外面包裝 Markdown 區塊 (```json ... ```)，
絕對禁止加入任何前言、結語或人類可讀的分析文字如 "**Findings**"。
違反此規則將導致自動化修補(Patch)系統崩潰。

{
  "status": "PASS" 或 "FAIL",
  "summary": "一句話總結審核結果",
  "violations": [
    {
      "file": "檔案路徑",
      "line": 行號,
      "severity": "CRITICAL" 或 "ADVICE",
      "reason": "詳細原因",
      "suggestion": "改進建議",
      "patch": "可選的補丁內容 (Unified Diff 格式，必須能夠被 git apply"
    }
  ]
}

如果發現 CRITICAL 級別的違規，status 必須為 FAIL。
請參考以下 MANDATORY LESSONS 進行審核。


---
[[System Overview]]