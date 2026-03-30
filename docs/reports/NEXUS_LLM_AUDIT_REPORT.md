# Nexus v16 LLM & Codex 調用審計報告 (Universal SOTA)

## 0. 執行摘要 (Executive Summary)
本報告針對 `James3014/Nexus` 程式碼庫進行「100% 物理語法掃描」，以確認 LLM (OpenAI/Gemini) 以及 Codex 工具的所有調用點。
目前 Nexus 引擎已初步實現「單一出口 (Single Exit)」治理，但 `scripts/` 目錄中仍存在 **3 個影子調用 (Shadow Callers)**。

---

## 1. 核心治理出口 (Primary LLM Client)
所有受控的 LLM 調用均集中於以下路徑：
- **實體檔案**: [`nexus/services/llm.py`](file:///Users/jameschen/Workspace/nexus/nexus/services/llm.py)
- **類別**: `LLMClient`
- **調用方式**: 
  - **SDK 模式**: 使用 `openai` SDK 呼叫 `chat.completions.create`。
  - **CLI 模式 (OAuth Fallback)**: 使用 `subprocess.run(["gemini", ...])` 或 `subprocess.run(["codex", ...])`。

> [!IMPORTANT]
> `nexus/executors/gemini.py` 現已進入 **被動解析模式 (Passive Parser)**，僅負責解析 `/tmp/nexus_agent_output.txt` 中的標籤，本身不具備主動呼叫能力。

---

## 2. 發現：影子調用點 (Shadow / Bypass Callers)
以下腳本 **繞過** 了 `LLMClient` 進行實體二進制呼叫，存在 Token 監控與 Auth 治理漏洞：

### 🚨 [Bypass] 結晶化引擎
- **檔案**: [`scripts/crystallize_via_gws_v3.py`](file:///Users/jameschen/Workspace/nexus/scripts/crystallize_via_gws_v3.py#L113)
- **語法**: `subprocess.run(["gemini", "-p", "CRM 結晶化："], ...)`
- **風險**: 繞過 `LLMClient` 的 Retries、Token 計數以及 Auth Fallback 邏輯。

### 🚨 [Bypass] 潛意識守護進程
- **檔案**: [`scripts/subconscious_daemon.py`](file:///Users/jameschen/Workspace/nexus/scripts/subconscious_daemon.py#L147)
- **語法**: `gemini_bin = shutil.which("gemini")` (及其後續調用)

### 🚨 [Bypass] TG/PTY 橋接器
- **檔案**: [`scripts/tg_pty_bridge.py`](file:///Users/jameschen/Workspace/nexus/scripts/tg_pty_bridge.py#L53)
- **語法**: `subprocess.run(["gemini", "-m", ...])`

---

## 3. 實體工具溯源 (Binary Origin)
- **`gemini`**: 指向 `@google/gemini-cli/dist/index.js` (NPM 工具)。
- **`codex`**: 指向 `@openai/codex/bin/codex.js` (NPM 工具)。
- **使用狀態**: 核心引擎 (CodexLoopV2) 透過 `LLMClient` 介接這些工具，而影子腳本則直接呼叫。

---

## 4. 治理建議 (SOTA Remediation)
1. **歸一化**: 將 `scripts/` 中的影子調用全量重構為調用 `nexus/services/llm.py:LLMClient`。
2. **熔斷機制**: 在 `LLMClient` 中加入 `MUSE_CORE_LLM_LOCK` 全域鎖，以防止併發調用導致的配額耗盡。
3. **清除**: 物理刪除 `scripts/archive_v9/` 下的舊版 `codex_loop_brain.py.bak` 以避免開發混淆。

---
**報告人**: Nexus Orchestrator (v16 God-Mode)
**時間**: 2026-03-24 17:59 (SOTA Audit Standard)
