# P3 Implementation Plan

## 總目標

P3 完成後，Nexus 要有一條新的主線：

```
task
  -> difficulty classify
  -> easy: local_only
  -> medium/hard: cloud_with_local_assist
       Stage 1: local diagnosis + compact prompt
       Stage 2: cloud candidate seam
       Stage 3: local cheap verifier
       Stage 4: local retry fallback
       Stage 5: escalate_to_hard_case_stub only
  -> P2 apply/hash/anchor/claim gate
  -> receipt
```

## P3 不做

- P4: committee as routed tool
- P5: diversity selection engine
- P6: quota-aware state machine
- production cloud rollout
- solve-rate claim

## 交付順序

| 包 | 名稱 | 說明 |
|----|------|------|
| I1 | Shadow routing contract | 讓 topology `cloud_with_local_assist` 進系統，不接 cloud |
| I2 | Difficulty router minimal policy | task difficulty 決定 route |
| I3 | Stage 1: Local diagnosis + compact prompt | 本地診斷 + 壓縮 prompt |
| I4 | Stage 2: Cloud candidate seam | fake/disabled cloud provider contract |
| I5 | Stage 3: Local cheap verifier | pre-verifier |
| I6 | Stage 4: Local retry after cloud fail | cloud fail fallback |
| I7 | Stage 5: Hard-case escalation stub | P3↔P4 邊界 |
| I8 | E2E route receipt + contract tests | 收斂測試 |

## 全域限制

- 不接真 cloud endpoint
- 不做 P4/P5/P6
- 不放寬 P2 claim gate
- 不宣稱 production ready / solve rate / local armor ready
- 每包最多改 5 個 code/test 檔
- 每包都要有 tests + receipt evidence + docs report
