# 📊 Performance Benchmarks & Datasets

## 1. 性能基準測試 (Evaluation Protocol)
為了客觀衡量架構優化（如 MSA），Nexus 建立了一套標準化的 A/B 測試框架。

## 2. 基準數據集 (Benchmark Dataset)
- **組成**: 包含 `IN_SCOPE` (核心問題) 與 `OUT_OF_SCOPE` (邊界探測) 的 30 條固定題庫。
- **欄位**: `id`, `query`, `expected_mode` (ANSWERED/UNKNOWN), `expected_domain`。

## 3. 核心指標 (KPIs)
- **Precision**: 檢索出的內容與問題的相關度。
- **Unknown Correct Rate**: 對「超出能力範圍」問題的精準拒絕率（目標 >= 0.95）。
- **Cost per Success**: 完成單次任務所需的 Token 成本。
- **Regression Rate**: 新版本導致舊功能失效的比率。

## 4. A/B Runner (benchmark_runner.py)
- **功能**: 自動跑兩組測試（Baseline vs Candidate），並生成機器可讀的 JSON 報表。
- **Kill Switch**: 若指標出現退化，自動觸發實驗中斷。

---
**[Source: nexus_wiki_vault/06_Ops/Ops - Performance Benchmarks.md]**
