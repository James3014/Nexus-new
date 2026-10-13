#!/usr/bin/env bash
# Stop: if HEAD is pushed and bound to an open Issue, start the trusted Nexus Core
# precheck (repository_dispatch) and block once so the agent reports Core status
# as PENDING. Never blocks on tool failure, offline, or a repeated stop.
set -u
input="$(cat 2>/dev/null || true)"
printf '%s' "$input" | grep -q '"stop_hook_active"[[:space:]]*:[[:space:]]*true' && exit 0
root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$root" 2>/dev/null || exit 0
command -v python3 >/dev/null 2>&1 || exit 0
command -v gh >/dev/null 2>&1 || exit 0
helper="$root/scripts/ops/nexus-core-precheck"
[ -f "$helper" ] || helper="$(command -v nexus-core-precheck 2>/dev/null || true)"
[ -n "$helper" ] && [ -f "$helper" ] || exit 0
limit="${NEXUS_CORE_PRECHECK_HOOK_TIMEOUT:-30}"
cmd=(python3 "$helper" dispatch --auto --repo-root "$root")
if command -v timeout >/dev/null 2>&1; then
  out="$(timeout "$limit" "${cmd[@]}" 2>/dev/null)" || true
elif command -v gtimeout >/dev/null 2>&1; then
  out="$(gtimeout "$limit" "${cmd[@]}" 2>/dev/null)" || true
elif command -v perl >/dev/null 2>&1; then
  out="$(perl -e 'alarm shift; exec @ARGV' "$limit" "${cmd[@]}" 2>/dev/null)" || true
else
  out="$("${cmd[@]}" 2>/dev/null)" || true
fi
fields="$(printf '%s' "$out" | python3 -c '
import json, sys
try:
    d = json.loads(sys.stdin.read().strip().splitlines()[-1])
except Exception:
    sys.exit(0)
if d.get("status") == "DISPATCHED":
    print(d.get("head") or "", d.get("issue") or "")
' 2>/dev/null)" || exit 0
[ -n "$fields" ] || exit 0
head="${fields% *}"; issue="${fields##* }"
cat >&2 <<MSG
[core-precheck] Nexus Core precheck started for ${head:0:12} on Issue #${issue} (takes 30-60 min).
In your completion report, state Core status as PENDING and how to check it:
  scripts/ops/nexus-core-precheck status --issue ${issue}
Do not claim Issue #${issue} complete until that status is VERIFIED.
MSG
exit 2
