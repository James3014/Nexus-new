# Nexus Nightly Patrol Report

**Date**: 2026-06-25
**Scope**: Full repository scan (nexus v28.3.0, 1,056 Python source files, 122K LOC, 6,232 test functions)
**Mode**: Read-only analysis. No files modified.

---

## 1. Summary

巡檢涵蓋：專案結構、CI 設定、測試覆蓋、安全性、依賴、程式碼品質、倉庫衛生。

**最重要的發現：**
- 2.6MB 編譯产物 `nexus_core.so` 被 commit 進 git（HIGH）
- CI 完全缺少 type checking 和 security scanning（MEDIUM-HIGH）
- 48 個 `.nexus-swarm-*/swarmtasks.db` 雖在 .gitignore 但仍被追蹤（MEDIUM）
- 164 個散落檔案堆在 repo root，含 47 個生成的 CSV/JSONL（HIGH 衛生問題）
- 1 個 Dockerfile 以 root 執行（Dockerfile.swe + 4 個 swarm Dockerfiles）（MEDIUM）

---

## 2. Findings

### F-01: 編譯产物 `nexus_core.so` 在版本控制中
- **問題**: 2.6MB 的 `.so` 共享庫被 git 追蹤
- **影響程度**: HIGH
- **可能原因**: Rust build 產物未加入 .gitignore 就被 commit
- **建議處理方向**: `git rm --cached nexus_core.so`，加入 .gitignore `*.so`
- **驗證方式**: `git ls-files '*.so'` 應返回空

### F-02: CI 缺少 Type Checking
- **問題**: 全專案無 mypy/pyright 配置，CI 無 type check 步驟。Pyre 配置為 strict=false 且排除了 security/、learning/、gateway/ 等關鍵路徑
- **影響程度**: MEDIUM-HIGH
- **可能原因**: 專案快速迭代中跳過了型別檢查
- **建議處理方向**: 加入 mypy 或 pyright，先從 nexus/core/ 開啟 strict mode，逐步擴展
- **驗證方式**: `mypy nexus/core/` 零 error

### F-03: CI 缺少 Security Scanning
- **問題**: 無 bandit、safety、Snyk、Trivy、CodeQL 等安全掃描。tests/security/ 只有 2 個測試檔
- **影響程度**: MEDIUM-HIGH
- **可能原因**: 安全掃描未納入 CI 流程
- **建議處理方向**: 加入 `bandit -r nexus/` 和 `pip-audit` 到 CI；考慮 CodeQL GitHub Action
- **驗證方式**: CI workflow 中新增 security-scan job

### F-04: 48 個 `.nexus-swarm-*/swarmtasks.db` 仍被追蹤
- **問題**: .gitignore 已有 `.nexus-swarm-*/` 規則，但 48 個 SQLite DB 在規則加入前已被 commit，仍被追蹤
- **影響程度**: MEDIUM
- **可能原因**: gitignore 規則在 files 已被追蹤後才加入
- **建議處理方向**: `git rm --cached .nexus-swarm-*/swarmtasks.db`（或 `git rm -r --cached .nexus-swarm-*/`）
- **驗證方式**: `git ls-files '.nexus-swarm-*'` 應返回空

### F-05: Repo Root 散落 164 個檔案
- **問題**: 164 個非目錄檔案在 root，含 11 個 `optimization_curve_*.csv`、11 個 `results_*.jsonl`、52 個 `.md` 報告
- **影響程度**: HIGH（衛生）
- **可能原因**: 開發過程中直接在 root 生成報告和數據，未整理
- **建議處理方向**: 移動生成檔案到 `reports/`、`data/`、`docs/`；加入 `*.csv`、`*.jsonl` 到 .gitignore（root 層）
- **驗證方式**: `ls -1 *.* | wc -l` 在 root 應低於 30

### F-06: .gitignore 含自動生成的錯誤模式
- **問題**: `.gitignore` 第 52-53 行含 `<MagicMock name='mock.run_dir.__truediv__()' id='*'>` 和 `str(REPO_ROOT)/`——明顯是 bug 產物被加入 gitignore
- **影響程度**: LOW（但反映流程問題）
- **可能原因**: 某個腳本將 MagicMock repr 寫入了路徑，被手動加入 gitignore
- **建議處理方向**: 移除這兩行，追蹤並修復產生這些路徑的源頭
- **驗證方式**: 搜尋 repo 中是否有程式碼生成這些路徑

### F-07: Dockerfile.swe 及 4 個 Swarm Dockerfiles 以 Root 執行
- **問題**: `Dockerfile.swe`、`nexus_swarm/manager/Dockerfile`、`nexus_swarm/node/Dockerfile` 及其 v22-prod 副本均無 `USER` 指令
- **影響程度**: MEDIUM（容器安全性）
- **可能原因**: 開發用 Dockerfile 未套用 production best practice
- **建議處理方向**: 加入 `RUN adduser` + `USER nexus` 到 Dockerfile.swe；swarm Dockerfiles 加入非 root user
- **驗證方式**: `docker run --rm <image> whoami` 返回非 root

### F-08: 23+ Python 依賴無上界
- **問題**: `pyproject.toml` 中 `pydantic>=2.0`、`lancedb>=0.4.0`、`pandas>=2.0.0`、`aiohttp>=3.8.0`、`httpx>=0.24.0` 等均無 upper bound
- **影響程度**: MEDIUM（供應鏈脆弱性）
- **可能原因**: 快速開發中未鎖定版本
- **建議處理方向**: 對 `lancedb`、`aiohttp`、`httpx` 加入上界（如 `<1.0`、`<4.0`、`<1.0`）；用 lockfile 鎖定
- **驗證方式**: `uv lock` 後 diff 確認無 major version 跳躍

### F-09: 29 個已死測試被 pytest.ini --ignore 靜默抑制
- **問題**: `tests/unit/committee/`（15 tests）、`tests/test_pact.py`（9 tests）等共 29 個測試因 import 失敗被 ignore
- **影響程度**: MEDIUM（技術債務）
- **可能原因**: 重構後測試未清理
- **建議處理方向**: 刪除對應的死測試檔案，或修復 import 路徑
- **驗證方式**: 移除 pytest.ini 的 ignore 規則後 `pytest --collect-only` 確認無 import error

### F-10: 10 個 bare `except:` 靜默吞掉所有異常
- **問題**: `nexus/core/context_compactor.py:46`、`nexus/core/unified_registry.py:50` 等 10 處 bare except
- **影響程度**: MEDIUM（除錯困難）
- **可能原因**: 防禦性 coding 過度使用
- **建議處理方向**: 替換為具體 exception type，至少 `except Exception`
- **驗證方式**: `grep -rn "except:" nexus/ --include="*.py"` 應返回 0

### F-11: 28 個檔案超過 500 行
- **問題**: 最大檔案 `nexus/app/research_flow_service.py`（1,958 行）、`nexus/research/sprint_service.py`（1,862 行）
- **影響程度**: MEDIUM（可讀性/維護性）
- **可能原因**: 功能持續堆疊未重構
- **建議處理方向**: 優先拆分 top 5 大檔案；提取子模組
- **驗證方式**: 各拆分後檔案 <500 行

### F-12: `scripts/ops/` 含 `--dangerously-bypass-approvals-and-sandbox` 標誌
- **問題**: `start_codex_nexus_enforced.sh` 在 `APPROVAL_MODE=danger` 時完全禁用 Codex sandbox
- **影響程度**: MEDIUM（安全性）
- **可能原因**: 開發便利性需求
- **建議處理方向**: 加入第二重確認（如 env var + terminal prompt）；限制僅在非 production 環境使用
- **驗證方式**: 實際執行腳本確認需要明確 opt-in

### F-13: 121 個檔案含 `print()` 語句
- **問題**: 生產代碼中大量使用 `print()` 而非 `logging`
- **影響程度**: LOW-MEDIUM
- **可能原因**: 快速開發/除錯遺留
- **建議處理方向**: 逐步替換為 `logging` 模組
- **驗證方式**: `grep -rn "print(" nexus/ --include="*.py" | wc -l` 應趨近 0

---

## 3. Priority List

### HIGH
| ID | 問題 |
|----|------|
| F-01 | `nexus_core.so` 在版本控制中（2.6MB binary） |
| F-05 | Repo root 散落 164 個檔案（47 個生成數據檔） |

### MEDIUM-HIGH
| ID | 問題 |
|----|------|
| F-02 | CI 缺少 Type Checking |
| F-03 | CI 缺少 Security Scanning |

### MEDIUM
| ID | 問題 |
|----|------|
| F-04 | 48 個 swarm SQLite DB 仍被追蹤 |
| F-07 | 5 個 Dockerfiles 以 root 執行 |
| F-08 | 23+ 依賴無上界 |
| F-09 | 29 個死測試被靜默抑制 |
| F-10 | 10 個 bare except |
| F-11 | 28 個超大檔案（>500 行） |
| F-12 | 危險的 sandbox bypass 標誌 |

### LOW
| ID | 問題 |
|----|------|
| F-06 | .gitignore 含 MagicMock 殘留 |
| F-13 | 121 個檔案含 print() |

---

## 4. Risks

### 最高風險區域
1. **供應鏈** — `lancedb>=0.4.0` 等 23+ 依賴無上界，任何 major release 可能 break build
2. **容器安全** — 4/5 Dockerfiles 以 root 執行，若被攻破影響範圍大
3. **CI 盲區** — 無 type checking + 無 security scanning = 靜態分析零覆蓋

### 需人工確認
1. `nexus-core-rs/` 是否仍為活躍實驗？若否，應刪除
2. `legacy/logmemory.py` 是否已完全替代？可否刪除？
3. 29 個被 ignore 的測試對應的模組（committee、pact、retry_controller）是否仍存在於 `nexus/` 中？
4. `start_codex_nexus_enforced.sh` 的 `APPROVAL_MODE=danger` 是否僅限開發環境？
5. 根目錄 11 個 `optimization_curve_*.csv` 是否為一次性生成？可否 git rm？

---

## 5. Next Actions

1. **立即執行（低風險、高回報）**：
   - `git rm --cached nexus_core.so` 並加入 `.gitignore`
   - `git rm -r --cached .nexus-swarm-*/` 清除已追蹤的 swarm DB
   - 刪除 `legacy/logmemory.py` 和空目錄 `nexus-rust-v16/`

2. **本週完成**：
   - 清理 repo root 散落檔案（移動到適當子目錄）
   - 修復 `.gitignore` 中的 MagicMock/str(REPO_ROOT) 殘留
   - 加入 `bandit` 或 `pip-audit` 到 CI workflow

3. **下個 sprint**：
   - 引入 mypy/pyright，先對 `nexus/core/` 開啟 strict mode
   - 為 5 個 Dockerfiles 加入非 root USER
   - 清理 29 個死測試（刪除或修復 import）
   - 為關鍵依賴加上界

4. **長期改善**：
   - 重構 28 個 >500 行的超大檔案
   - 替換 10 個 bare except 為具體 exception
   - 建立 pre-commit hooks（ruff + mypy）
