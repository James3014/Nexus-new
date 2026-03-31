# Nexus 自動化與數據真相 (Automation & Truth Protocol)

## 🎯 目標
將 Nexus 治理從「文件結案」升級為「數據驅動的自動化防線」，確保所有指標可透過實測數據（Tokens, Drift, Pass/Fail）證偽。

## Track H：數據真相 (Truth Dashboard) [/]
- [/] **TRU-101 真實 Token 追蹤**: 正則表達式邏輯已通過單元測試，但集成環境測試目前仍為 0 (待進一步對標環境觸發)。
- [x] **TRU-102 數據真相儀表板**: 自動產出 `nexus_truth_dashboard.md` 並落地專案根目錄。
- [x] **Dual-Engine Phase 2: Data Loop Hardening**
    - [x] [SQLite] Enable WAL Sync + NORMAL
    - [x] [Core] Implement `dual_sink.py`
    - [x] [CLI] Add `nexus:dual-report`
    - [x] [Test] 10-task mock sink + report
- [x] **P11.1 環境清場與基建 (Infrastructure)**
    - [x] `minikube delete --all --purge`
    - [x] `brew install minikube kubectl helm`
    - [x] `minikube start --nodes 5 --cpus 2 --memory 4096 --driver=docker`
- [x] **P11.2 鏡像構建與模型密封 (Dockerfile)**
    - [x] `docker build -t nexus:v18.4-ollama .` (密封 Llama 3.1)
    - [x] `minikube image load nexus:v18.4-ollama`
- [x] **P11.3 Swarm 集群佈署 (Deployment)**
    - [x] `helm install nexus-swarm ./nexus-chart --namespace nexus --create-namespace`
    - [x] `kubectl scale deployment nexus-swarm -n nexus --replicas=10`
- [x] **P11.4 200 併發基準測試 (Benchmark)**
    - [x] `benchmark_suite.py --k8s --tasks=200 --concurrency=20 --per-pod-limit=2`
- [x] **P11.5 最終認證與回報 (Certification)**
    - [x] 提取 `p11_swarm.log` 指標
    - [x] 完成 v18.4 正式晉升對位

## Track I：自動化回歸 (CI & Pytest) [x]
- [x] **AUT-101 Pytest 規格化**: 重構 `tests/test_v9_regression_p1.py`。
- [x] **AUT-102 CI Lane 實作**: 建立 `scripts/ci_gate.py` 無捲標自動化測試流。
- [x] **AUT-103 測試補全**: 建立 `tests/test_llm_token_regex.py` 參數化驗證證據。

## Track J：案例擴展 (Case Expansion) [x]
- [x] **EXP-001 案例補齊至 10 個**: 覆蓋 Bug/Feature/DI/Fast/Audit 等情境。
- [x] **EXP-002 批量 Replay 驗證**: 確保 10 個案例全數可跑且結果一致。

---
**核准狀態：Partial Aligned (TRU-101 Pending)**
