# P4 Implementation Plan: Committee as Routed Tool

## 總目標

P4 完成後，committee 從「legacy default topology」降級成「P3 hard-case path 後的 routed tool」。

```
P3 Stage 5: escalation stub
  ↓  (stage5_escalation_recommended=true)
P4 activation gate
  ↓  (allowed)
P4 committee routed tool
  ↓  candidates → CanonicalPatchCandidate → winner → re-apply → verifier → P2 claim gate
  ↓  receipt
```

P4 不做 P5 diversity / P6 quota / production cloud / P2 relaxation。

## 交付順序

| 包 | 名稱 | 說明 |
|----|------|------|
| I1 | Committee routed-tool contract | Request/Result 介面 + fail-closed 條件 |
| I2 | Activation/suppression gate | 8 條 enable + 7 條 disable 條件 |
| I3 | Candidate adapter to CanonicalPatchCandidate | 所有 candidate 走 P1 |
| I4 | Committee execution inside P3 hard-case path | 接上 Stage5 |
| I5 | Winner re-apply + verifier + P2 claim gate | 完整 P2 pipeline |
| I6 | Zero-winner fail-closed | 9 種 fail-closed 情境 |
| I7 | E2E route receipt + regression closure | 5 條 E2E 管線 |

## 全域限制

- 不做 P5 diversity
- 不做 P6 quota
- 不放寬 P2 claim gate
- 不讓 committee 變回 default topology
- 不讓 judge vote 直接 solved
- 不宣稱 production ready / solve rate / local armor ready
- 每包最多改 5 個 code/test 檔
- 每包必須有 tests + receipt evidence
- artifact / pycache / scratch 不得進 commit
