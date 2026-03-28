# Nexus 超短版操作手冊（6 指令）

這份是給你和朋友的「日常最小集合」，先用這 6 個就夠。

## 0. CLI 入口
```bash
python3 /Users/jameschen/Workspace/nexus/scripts/engine/nexus_cli.py <command>
```

## 1. 套用正式模式（建議先跑）
用途：把日常任務切到正式交付策略（高標交付 + 高檢查 + strict 自癒）。

```bash
python3 /Users/jameschen/Workspace/nexus/scripts/engine/nexus_cli.py nexus:profile apply --name prod
python3 /Users/jameschen/Workspace/nexus/scripts/engine/nexus_cli.py nexus:profile show
```

## 2. 修 Bug
用途：執行修復任務。`prod` 模式下成功後會自動做 release gate。

```bash
python3 /Users/jameschen/Workspace/nexus/scripts/engine/nexus_cli.py nexus:bug --task "fix login callback" --delivery-mode ask
```

## 3. 做功能
用途：執行 feature 任務。`prod` 模式下成功後會自動做 release gate。

```bash
python3 /Users/jameschen/Workspace/nexus/scripts/engine/nexus_cli.py nexus:feature --task "add SSO audit trail" --delivery-mode ask
```

## 4. 自檢
用途：看現在健康狀態是否可交付。

```bash
python3 /Users/jameschen/Workspace/nexus/scripts/engine/nexus_cli.py nexus:check --level ask
```

## 5. 自癒
用途：出現降級或異常時快速修復。

```bash
python3 /Users/jameschen/Workspace/nexus/scripts/engine/nexus_cli.py nexus:self-heal --mode ask
```

## 6. 正式交付 Gate
用途：交付前總門檻，沒過就不算可交付。

```bash
python3 /Users/jameschen/Workspace/nexus/scripts/engine/nexus_cli.py nexus:release-ready
```

## 研究模式（需要時再用）
用途：跑 Phase 6 研究，不是每次任務都要開。

```bash
python3 /Users/jameschen/Workspace/nexus/scripts/engine/nexus_cli.py nexus:phase6 \
  --workspace /Users/jameschen/Downloads/obsidian/01_Projects/Autoresearch \
  --rounds 100 \
  --proof-ratio-min 95 \
  --output-prefix phase6
```

---

朋友快速啟動（對話入口）：
```bash
nexus-pilot-friend pilot_a
```

若出現 `command not found`，先補 PATH：
```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```
