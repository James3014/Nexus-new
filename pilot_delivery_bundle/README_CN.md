# Nexus Pilot 交付索引

這個目錄是朋友試用前的整理入口。

建議先看：

1. `NEXUS_PILOT_CLI_QUICKSTART_CN.md`
   朋友安裝、啟動、基本使用方式。
2. `NEXUS_PILOT_FRIEND_MESSAGE_CN.md`
   可直接轉貼給朋友的說明文字。
3. `DELIVERY_CONTRACT_CN.md`
   核心 Nexus 任務流的高標交付規則。
4. `pilot_cli_20_checks_report.md`
   本次交付前的檢查報告。
5. `pilot_cli_20_checks_transcript.txt`
   檢查過程 transcript。

腳本與入口：

- `install_nexus_pilot_friend.sh`
  朋友安裝 CLI 的腳本。
- `nexus_pilot_friend.py`
  朋友模式入口。
- `nexus_pilot_cli.py`
  Pilot Chat CLI 正式入口。
- `nexus_chat_cli.py`
  舊入口相容 shim。
- `pilot_cli_delivery_smoke.py`
  交付前 smoke test 腳本。

核心任務流如果要啟用高標交付，可使用：

```bash
python3 /Users/jameschen/Workspace/nexus/scripts/engine/nexus_cli.py nexus:bug --task "fix login callback" --delivery-mode ask
python3 /Users/jameschen/Workspace/nexus/scripts/engine/nexus_cli.py nexus:feature --task "add SSO audit trail" --delivery-mode ask
python3 /Users/jameschen/Workspace/nexus/scripts/engine/nexus_cli.py nexus:runner --delivery-mode ask
```

選 `high` 時，系統會：

- 自動推建議驗證命令（Python / Rust / Go）
- 顯示實際採用的驗證命令
- 顯示交付報告路徑

目前推薦朋友啟動方式：

```bash
nexus-pilot-friend pilot_a
```

```bash
nexus-pilot-friend pilot_b
```

## 注意事項：Command Not Found？

如果執行 `nexus-pilot-friend` 顯示 `command not found`，請確認您的 `PATH` 包含 `~/.local/bin`：

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

🏆 **Nexus Pilot CLI - 試用愉快！**
