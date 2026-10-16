# Nexus v27.1 治理歸檔索引與審計回放指南

本文件為 v27.1 版本之正式歸檔索引，提供物理證據與重播審計之對位依據。

## 1. 物理資產指紋 (Artifact Fingerprints)
*   **Version**: `v27.1`
*   **Archive Bundle**: `archives/v27.1/v27.1_archive_bundle.json`
*   **ADR Manifest**: `archives/v27.1/adr_freeze_manifest.json`
*   **Baseline Hash**: `b11e8069f796...` (與當前 CI Gate 對位)

## 2. 審計重播路徑 (Audit Replay Path)
若需驗證 v27.1 期間的任何晉升決策，請執行：
```bash
python3 -m nexus.governance.application.receipt_replayer --receipt archives/v27.1/v27.1_archive_bundle.json
```

## 3. 凍結政策 (Freeze Policy)
*   **Status**: **HARD FROZEN**
*   **Constraint**: 禁止直接修改 `archives/v27.1/` 內容。
*   **Evolution**: 任何規格變動必須由 v27.2+ 之新 ADR 承接。

## 4. 運營摘要 (Ops Summary)
*   **Pass Rate**: 100%
*   **Drift Protection**: Enabled (Active)
*   **Atomic Rollback**: Verified

---
[NEXUS ARCHIVE BOARD v27.1]
