# 離線全域 Context 快取指引 (Global Context Blueprint)

**建立日期**: 2026-06-05

為了避免新進 Agent 或開發者重複花費大量時間與 API Token 去掃描巨型 Codebase，本專案已建立靜態全域快取，請優先利用以下資源進行上下文載入。

## 📦 核心上下文快取

### 1. 全量程式碼打包 (The Universal Code Dump)
*   **路徑**: `docs/perplexity/repomix/repomix-output.txt`
*   **大小**: 約 196MB (11,658 files)
*   **用途**: 若你需要「一次性」分析跨目錄、跨模組的底層實作，請直接讀取此檔，而不是用 `ls` 與 `cat` 逐層爬梳。此檔由 Repomix 生成，具備 XML 標籤與明確的檔案邊界。

### 2. 專案 AST 結構樹 (Skeleton Tree)
*   **路徑**: `docs/perplexity/contextplus/tree.md`
*   **大小**: 約 343KB
*   **用途**: 當你只需要了解專案的「目錄長相」與「核心類別/函數分佈」，而不需要細節代碼時，請閱讀此 AST Tree。

### 3. 全局知識圖譜 (Knowledge Graph)
*   **路徑**: `docs/perplexity/graphify/GRAPH_REPORT.md`
*   **用途**: 了解模組間的高階依賴關係與「圖譜社區 (Communities)」。若要修改核心基礎設施 (如 Memory 或 Governance)，請先查看此報告確認 Blast Radius (影響半徑)。

## ⚠️ Agent 守則
**請勿**在未查看上述靜態快取前，發起全域的 `grep` 或高頻繁的 `read_file` 迴圈掃描。請優先利用已整理好的快取，提升上下文擷取效率。