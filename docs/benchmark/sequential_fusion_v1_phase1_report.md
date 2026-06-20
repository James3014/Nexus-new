# Sequential Fusion Trial v1 — Phase 1 Report

**[階段]** Sequential Fusion Trial v1 — Phase 1 (Unsolved-First Gate)

**[總體判定]** 🔴 RED

**[一句話結論]** 兩組 sidecar 零 lift，故障分佈完全一致，DeepSeek-R1 sidecar 從未觸發。不批准進 Phase 2。

---

## 結果表

| Task | A (baseline) | B (Gemma 🔗) | C (R1) |
|------|:---:|:---:|:---:|
| astropy__astropy-12907 | ❌ 594s | ❌ 812s | ❌ 853s |
| astropy__astropy-13236 | ❌ 325s | ❌ 406s | ❌ 440s |
| astropy__astropy-13579 | ❌ 715s | ❌ 875s | ❌ 853s |
| sympy__sympy-12481 | -- timeout | -- timeout | -- timeout |
| sympy__sympy-13372 | ✅ 253s | ✅ 328s | ✅ 369s |
| astropy__astropy-14182 | ❌ 363s | ❌ 608s | ❌ 526s |
| **Solve rate** | **1/6** | **1/6** | **1/6** |

## Sidecar lift

| 組別 | lift vs A | 觸發 | 貢獻 | 說明 |
|------|:---------:|:----:|:----:|------|
| B (Gemma) | +0 | 5/6 | 5/6 | 觸發但零影響 patch 結果 |
| C (R1) | +0 | 0/6 | 0/6 | sidecar call 全部失敗/超時 |

## Failure taxonomy

| failure_class | A | B | C |
|:---:|:---:|:---:|:---:|
| patch_mismatch | 4 | 4 | 4 |
| verification (solved) | 1 | 1 | 1 |
| timeout | 1 | 1 | 1 |

## Stop-layer

| stop_layer | A | B | C |
|:---:|:---:|:---:|:---:|
| patcher | 4 | 4 | 4 |
| verification | 1 | 1 | 1 |

## 判定

**❌ 不批准進 Phase 2。**

- Gemma sidecar：移除。觸發無效，每題多花 100-250s
- DeepSeek-R1 sidecar：移除。從未成功執行
- 根因：5/6 題失敗都是 patch_mismatch，問題在 patch synthesis code matching，不在 planning/diagnosis
