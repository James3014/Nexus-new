#!/bin/bash
# 啟動帶有遠端偵錯埠的 Chrome
# 預設埠: 9222
# 預設 Profile: /tmp/chrome-profile-stable

/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir=/tmp/chrome-profile-stable \
  --no-first-run \
  --no-default-browser-check &

echo "Chrome Debug Mode 已啟動 (Port: 9222)"
