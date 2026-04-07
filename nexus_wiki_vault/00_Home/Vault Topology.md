---
aliases:
- Topology
- Vault Map
- Knowledge Map
description: Visual map of the Nexus Knowledge Graph structure and information flow.
governance: Trident 3.0
id: vault-topology
owner: Nexus Core
status: current
tags:
- nexus
- topology
- map
type:
- - System Overview|home
---



# Nexus 知識庫拓撲地圖 (Vault Topology)

## One-sentence summary
本文件展示了 Nexus 知識庫內部的導航路徑與層級結構，協助 Agent 快速定位核心規格與歷史背景。

## Role / responsibility
- **地圖導航**: 提供全景視圖，標註 Tier 0 至 Tier 3 的流向。
- **版本關聯**: 明確標註 v9, v152, v23 之間的演進關係。

## Upstream
- [System Overview](System Overview.md): 作為全局進入點。

## Downstream
- [[01_Core]]: 所有核心技術規格。

## Related modules / files
- `scripts/ops/wiki_linter.py`
- `scripts/ops/v23_semantic_linker.py`

## Source notes
- [Source: 00_Home/System Overview.md]

## Open questions / conflicts
- [ ] 目標文檔數是否應自動從 linter 輸出同步。

> [!NOTE]
> 本文件展示了 `nexus_wiki_vault` 內部的知識流動路徑，重點在於 Core 規範與 Legacy 遺傳文檔之間的連結。

## 核心架構流圖
```mermaid
graph TD
    [Home](System Overview.md)["[System Overview](System Overview.md)"] --> Core["[[01_Core]]"]
    [Home](System Overview.md) --> Ops["[[06_Ops]]"]
    [Home](System Overview.md) --> Incidents["[[08_Incidents]]"]
    
    subgraph "Trident 3.0 Core"
        Core --> Specs["核心規格 (High-Level)"]
        Specs --> V23["[[NEXUS_v23_WISDOM_EDITION_SPEC]]"]
        Specs --> V17["[[MUSE_ENGINE_SPEC_V17.1_HARDENED]]"]
    end
    
    subgraph "Legacy Integration (Connectivity Layer)"
        V17 -.-> V152["[[INDEX|Muse-Nexus v152]]"]
        V152 -.-> V9["[[INDEX|Nexus V9 Legacy]]"]
        V9 -.-> Origin["歷史代碼存檔"]
    end
    
    Ops --> Reference["[[06_Ops/Reference/README|Ops Reference]]"]
```

## 知識連結統計
- **總文檔數**：309
- **強連結文檔 (含 [[)]**：309 (100%)
- **主要導覽樞紐**：
    - [System Overview](System Overview.md) (根節點)
    - [[01_Core/Specs/Legacy_V9/INDEX|Legacy V9 Index]] (歷史橋樑)
    - [[01_Core/Specs/Muse-Nexus-v152-upgrade/INDEX|v152 Upgrade Index]] (版本橋樑)

## 導覽路徑建議
1. 從 [System Overview](System Overview.md) 開始。
2. 進入 [[01_Core]] 查看當前規格。
3. 透過內嵌的「語義連結」直接跳轉至相關的歷史背景 (Legacy Docs)。

---
[返回主頁面 [System Overview](System Overview.md)]


---
[System Overview](System Overview.md)

---
[[System Overview]]