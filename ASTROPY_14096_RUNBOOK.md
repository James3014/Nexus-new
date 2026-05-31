# 🛡️ LocalHeal: astropy-14096 環境除噪 Runbook

## 1. 診斷結論 (Diagnostic Summary)
`astropy-14096` 在當前 Workspace 下重現失敗的原因是 **Runtime Parity Gap**。
- **倉庫源碼**: 版本約為 v5.x，含有大量已在現代 Python (3.14) 或 Numpy (2.x) 中移除的 API（如 `np.product`, `np.trapz`）。
- **缺失產物**: 倉庫為「破碎安裝」狀態，缺失 C 擴展模組（如 `_compiler`, `_parse_times`），導致導入時觸發 `ImportError`，遮蔽了真正的 `AttributeError` Bug。
- **工作環境**: Workspace 已安裝的 `astropy v7.2.0` 已經修復了此 Bug。

## 2. 環境除噪作業程序 (De-noising Procedures)

### A. 解決導入噪音 (Import-Level De-noising)
若必須使用 `scratch/tmp_astropy_14096` 進行修復，執行以下「外科手術」以規避安裝檢查：
```bash
# 1. 建立虛擬編譯器標記
echo "compiler = 'unknown'; version = 'unknown'" > astropy/utils/_compiler.py

# 2. 修正過時的 Numpy API (針對 Numpy 2.x)
sed -i '' 's/np.product/np.prod/g' astropy/units/quantity_helper/function_helpers.py
sed -i '' 's/np.trapz/np.trapezoid/g' astropy/units/quantity_helper/function_helpers.py
```

### B. 依賴對齊 (Dependency Alignment)
使用 `uv` 強制對齊舊版所需的基礎庫：
```bash
uv pip install "numpy<2.0" "setuptools<70" pyerfa packaging extension-helpers cython
```

### C. 執行預檢 (Reproduction Pre-flight)
在啟動 LocalHeal 前，執行 `verify_bug_14096.py`：
- **紅燈 (BUG REPRODUCED)**: 看到 `AttributeError: 'custom_coord' object has no attribute 'prop'`，此為進入修復階段的必要條件。
- **綠燈 (FIXED)**: 看到 `... no attribute 'random_attr'`，代表環境已對齊或 Bug 已解。

## 3. 重跑成功條件 (Success Criteria)
1. **Phase 1 Evidence**: `repro_evidence` 必須包含 `Captured AttributeError: ... no attribute 'prop'`。
2. **Anti-Drift Proof**: `llm_trace.log` 中不應再出現 `TypeError` 的漂移回饋。
3. **Receipt Integrity**: 最終產出必須包含 `telemetries` 中的 `resolved_span` 與 `is_auto_corrected` 紀錄。

## 4. 特殊備註：代數推理與 TSP 管線建議
由於此題涉及 `__getattr__` 攔截鏈的陰影效應 (Shadowing Effect)，建議模型使用 `ALGEBRAIC` 模式，並在 `NexusDiagnosis` 中定義不變量：`Invariant: Accessing undefined attribute X inside a property should always propagate AttributeError(X).`

**[v2.9 更新] 物理牆與 TSP 路由策略：**
在實戰中觀測到，若將整份 `attributes.py` (約 1.8 萬字元) 餵給 14b 模型，將觸發本地推論的 Timeout 物理牆。
- **最佳解法 (TSP 管線)**: 應強制使用 7b 執行 `Search/Localize` 階段，將上下文精煉至目標函式 (約 7000 字元內)；再由 14b 在窄上下文中執行 `Patch Synthesis`。
- **Syntax Gate 護欄**: 7b 模型在窄上下文中容易出現指令跟隨退化（如遺漏 `SEARCH/REPLACE` 或產生 `Falsedef` 的拼接錯誤）。修補階段必須啟動 Syntax Gate 並強制要求 `CANONICAL REWRITE` (完整函式重寫)，以確保修補精度。
