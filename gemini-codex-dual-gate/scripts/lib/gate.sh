#!/bin/bash

MAX_REVIEWS=5

ensure_real_codex_cli() {
  local codex_bin
  codex_bin="$(command -v codex 2>/dev/null || true)"

  if [ -z "$codex_bin" ]; then
    echo "❌ Codex CLI not found in PATH."
    return 1
  fi

  # Block common local mocks unless explicitly allowed for test harnesses.
  if [ "${CODEX_ALLOW_MOCK:-0}" != "1" ]; then
    case "$codex_bin" in
      /tmp/*|*/fakebin/*)
        echo "❌ Refusing non-real Codex CLI path: $codex_bin"
        echo "   Set CODEX_ALLOW_MOCK=1 only for local test harness."
        return 1
        ;;
    esac
  fi

  local help_out
  help_out="$(codex review --help 2>&1 || true)"
  if ! echo "$help_out" | grep -q "Run a code review non-interactively"; then
    echo "❌ Codex CLI signature check failed. Unexpected 'codex review --help' output."
    return 1
  fi

  return 0
}

is_codex_quota_error() {
  local output="$1"

  if [ "${CODEX_FORCE_QUOTA_SKIP:-0}" = "1" ]; then
    return 0
  fi

  echo "$output" | grep -qiE \
    'insufficient_quota|quota|rate limit|429|billing|exceeded.*quota|usage limit'
}

check_gate() {
  local verdict="$1"
  local count="$2"
  
  if [ "$count" -ge "$MAX_REVIEWS" ]; then
    echo "BLOCKED: Max review limit reached ($count)"
    return 2
  fi

  if [ "$verdict" == "APPROVED" ] || [ "$verdict" == "PASS" ]; then
    echo "APPROVED"
    return 0
  else
    echo "REVISE"
    return 1
  fi
}
