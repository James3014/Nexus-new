# Nexus v7 Quick Start Guide | 快速上手指南 ⚡

---

## 1. Installation | 安裝

**[EN]** Nexus v7 requires Python 3.9+ and valid LLM API keys.
**[ZH]** Nexus v7 需要 Python 3.9+ 以及有效的 LLM API 金鑰。

```bash
# Clone the repository | 複製儲存庫
git clone https://github.com/nexus-ai/nexus-v7.git
cd nexus-v7

# Install dependencies | 安裝依賴
pip install -r requirements.txt

# Set up environment | 設定環境變數
export JINA_API_KEY="your_jina_key"
export OPENAI_API_KEY="your_api_key"
```

---

## 2. First Bug Fix | 第一次 Bug 修復

**[EN]** Test Nexus on a real-world scenario to see the P-D-X-R-A-C loop.
**[ZH]** 在真實場景中測試 Nexus，觀察 P-D-X-R-A-C 循環。

```bash
# Run with silent mode for clean output
# 使用靜音模式以獲得乾淨的輸出
python3 scripts/nexus_cli.py --silent nexus:bug --task "fix cors error on api calls"
```

---

## 3. Advanced Features | 進階功能

**[EN]** For complex planning, use feature mode with domain adaptation.
**[ZH]** 對於複雜計畫，使用具備領域自適應的功能模式。

```bash
# Plan a migration | 規劃遷移
python3 scripts/nexus_cli.py --silent nexus:feature --task "migrate session to redis" --domain django
```

---

## 4. WarRoom Dashboard | 戰情室

**[EN]** Monitor your AI's battle stats in real-time.
**[ZH]** 即時監控您的 AI 戰意與數據。

```bash
python3 scripts/nexus_cli.py nexus:warroom
```

---

## 5. Deployment | 部署與隔離

**[EN]** Use `--output-dir` for task isolation in CI/CD.
**[ZH]** 在 CI/CD 中使用 `--output-dir` 進行任務隔離。

```bash
python3 scripts/nexus_cli.py --output-dir ./runs/task_001 nexus:bug --task "refactor logic"
```

---
**Ready to scale? | 準備好擴展了嗎？** 🫡🦾
