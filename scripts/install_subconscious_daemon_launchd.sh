#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT_PATH="$REPO_ROOT/scripts/subconscious_daemon.py"
PLIST_PATH="$HOME/Library/LaunchAgents/com.musenexus.subconscious-daemon.plist"
LOG_DIR="$HOME/.muse_logs"

if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "❌ 找不到腳本: $SCRIPT_PATH"
  exit 1
fi

VAULT_ROOT_DEFAULT="/Users/jameschen/Downloads/obsidian/知識庫"
if [[ -d "$VAULT_ROOT_DEFAULT" ]]; then
  VAULT_ROOT="$VAULT_ROOT_DEFAULT"
else
  VAULT_ROOT="$REPO_ROOT"
fi

mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.musenexus.subconscious-daemon</string>
  <key>RunAtLoad</key>
  <true/>
  <key>StartInterval</key>
  <integer>3600</integer>
  <key>EnvironmentVariables</key>
  <dict>
    <key>VAULT_ROOT</key>
    <string>$VAULT_ROOT</string>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/zsh</string>
    <string>-lc</string>
    <string>cd "$REPO_ROOT" &amp;&amp; /usr/bin/env python3 "$SCRIPT_PATH" &gt;&gt; "$LOG_DIR/subconscious_daemon.log" 2&gt;&amp;1</string>
  </array>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/subconscious_daemon.stdout.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/subconscious_daemon.stderr.log</string>
</dict>
</plist>
PLIST

launchctl unload "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl load "$PLIST_PATH"

echo "✅ 已安裝/更新 launchd：com.musenexus.subconscious-daemon"
echo "   VAULT_ROOT=$VAULT_ROOT"
echo "   LOG=$LOG_DIR/subconscious_daemon.log"
