# ADR 0005: 兩段式校準與棄權管線

## 狀態
已接受 (Accepted)

## 背景
校準 (TS/ECE) 是純數學行為，而棄權是基於風險偏好 (Risk Budget) 的決策行為。原本兩者混在 `selection/` 中，導致門檻微調困難。

## 決策
將管線分為兩段：
1. **Calibration Context**: 提供 `TemperatureScaler` 產出 calibrated confidence。
2. **Abstention Context**: 根據校準信心、Selection Gap 與衝突狀態執行放行判定。

## 後果
- **優點**: 
  - 棄權門檻可依據 Risk Profile 動態調整。
  - 符合 selective recalibration 的學術趨勢。
- **缺點**: 
  - 增加了對 DTO 資料傳遞的依賴。
