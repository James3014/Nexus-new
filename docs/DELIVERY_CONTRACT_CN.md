# Nexus Delivery Contract / Nexus 交付契約

## Goal / 目標

This contract defines the minimum verification evidence required before Nexus may claim work is complete, verified, or ready for delivery.

本契約定義 Nexus 在宣稱任務完成、已驗證、可交付之前，最低必須具備的驗證證據。

## Task Levels / 任務等級

| Level | Meaning | Minimum Verification | Artifacts |
|---|---|---:|---:|
| `doc` | Documentation-only or wording change | 1 command | 0 |
| `small_fix` | Small bugfix or narrow code edit | 1 command | 0 |
| `feature` | Multi-file logic change or new behavior | 2 commands | 0 |
| `delivery` | External release, handoff, or publish-ready package | 2 commands | 1 |

| 等級 | 說明 | 最少驗證命令 | 最少產物 |
|---|---|---:|---:|
| `doc` | 文件或文案修改 | 1 | 0 |
| `small_fix` | 小型 bugfix 或小範圍程式修正 | 1 | 0 |
| `feature` | 多檔案邏輯修改或新行為 | 2 | 0 |
| `delivery` | 對外交付、發布或可轉交版本 | 2 | 1 |

## Status Meanings / 狀態定義

- `implemented`: code or docs changed, but no meaningful verification passed.
- `partially_verified`: some verification passed, but the command floor or all-pass requirement was not met.
- `verified`: verification commands passed at the required level.
- `delivery_ready`: verification commands passed and required artifacts exist for delivery-level work.

- `implemented`：已有修改，但沒有足夠驗證成功。
- `partially_verified`：有部分驗證成功，但未達命令門檻或未全數通過。
- `verified`：已達到該任務等級要求的驗證。
- `delivery_ready`：已達到交付級驗證，且必要產物存在。

## Hard Rule / 鐵律

Nexus must not claim “done”, “fixed”, “ready to ship”, or equivalent completion language without a fresh completion-gate result.

Nexus 在沒有最新 completion gate 結果前，不得宣稱「完成」、「修好」、「可交付」、「可以發布」或同等語意。

## Task Runner Integration / Task Runner 整合

`scripts/ops/task_runner.py` now supports manifest-level enforcement.

`scripts/ops/task_runner.py` 現在支援在 manifest 層直接強制 completion gate。

### Defaults / 預設層

```yaml
defaults:
  require_completion_gate: true
```

If this flag is enabled, tasks without `completion_gate` config will fail before being marked done.

如果開啟這個旗標，沒有 `completion_gate` 配置的任務，在被標成 `done` 前會直接失敗。

### Interactive choice / 互動式選擇

`scripts/engine/nexus_cli.py nexus:runner` now supports:

`scripts/engine/nexus_cli.py nexus:runner` 現在支援：

```bash
uv run scripts/engine/nexus_cli.py nexus:bug --task "fix login" --delivery-mode ask --verify "/bin/echo smoke"
uv run scripts/engine/nexus_cli.py nexus:feature --task "add SSO" --delivery-mode ask --verify "/bin/echo smoke"
uv run scripts/engine/nexus_cli.py nexus:runner --delivery-mode ask
uv run scripts/engine/nexus_cli.py nexus:runner --delivery-mode standard
uv run scripts/engine/nexus_cli.py nexus:runner --delivery-mode high
```

- `ask`: prompt the user whether to enable high-standard delivery.
- `standard`: run tasks without forcing completion gate.
- `high`: force completion gate before a task may be marked done.
- `nexus:bug` and `nexus:feature` accept `--verify` and `--artifact` when high-standard delivery is selected.

- `ask`：主動詢問是否啟用高標交付。
- `standard`：不強制 completion gate。
- `high`：任務在標成 `done` 前必須通過 completion gate。
- `nexus:bug` 與 `nexus:feature` 在選擇高標交付時，可用 `--verify` 與 `--artifact` 提供驗證命令與交付產物。

### Per-task config / 任務層設定

```yaml
tasks:
  - id: docs.sync.r1
    run: "uv run scripts/nexus_cli.py nexus:runner --task docs.index.sync"
    done_when:
      type: command_rc_zero
    evidence_paths:
      - docs/INDEX.md
    completion_gate:
      task_level: delivery
      verify_commands:
        - "test -f docs/INDEX.md"
        - "uv run pytest tests/test_ci_gate_phantom_guard.py -q"
      artifact_paths:
        - docs/INDEX.md
```

`completion_gate.task_level` maps to the contract levels above.

`completion_gate.task_level` 對應上方契約中的任務等級。
