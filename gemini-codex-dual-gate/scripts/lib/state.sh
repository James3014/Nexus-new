#!/bin/bash
STATE_FILE=".ai/state.json"
STATE_SIG_FILE=".ai/state.sig"

state_digest() {
  python3 - <<'PY'
import hashlib
from pathlib import Path

state_file = Path(".ai/state.json")
if not state_file.exists():
    print("")
    raise SystemExit(0)

tracked = [
    ".ai/task.md",
    ".ai/constraints.md",
    ".ai/plan.md",
    ".ai/acceptance.md",
    ".ai/changed-files.md",
    ".ai/implementation-report.md",
    ".ai/test-results.md",
    ".ai/codex-plan-review.md",
    ".ai/codex-scorecard.md",
    ".ai/gemini-scorecard.md",
]

h = hashlib.sha256()
h.update(state_file.read_bytes())
for p in tracked:
    fp = Path(p)
    h.update(p.encode("utf-8"))
    if fp.exists():
        h.update(fp.read_bytes())
    else:
        h.update(b"__MISSING__")
print(h.hexdigest())
PY
}

seal_state() {
  local digest
  digest="$(state_digest)"
  DIGEST="$digest" STATE_SIG_FILE="$STATE_SIG_FILE" python3 - <<'PY'
import json
import os
from datetime import datetime, timezone
payload = {
  "state_sha256": os.environ["DIGEST"],
  "sealed_at_utc": datetime.now(timezone.utc).isoformat()
}
with open(os.environ["STATE_SIG_FILE"], "w", encoding="utf-8") as f:
  json.dump(payload, f, indent=2)
PY
}

verify_state() {
  [ -f "$STATE_FILE" ] || return 1
  [ -f "$STATE_SIG_FILE" ] || return 2

  local expected actual
  expected="$(python3 -c "import json;print(json.load(open('$STATE_SIG_FILE'))['state_sha256'])" 2>/dev/null)"
  actual="$(state_digest)"

  [ -n "$expected" ] && [ "$expected" = "$actual" ]
}

ensure_state_integrity() {
  [ -f "$STATE_FILE" ] || return 1
  if [ ! -f "$STATE_SIG_FILE" ]; then
    seal_state
  fi
  verify_state
}

read_state() {
  if ! ensure_state_integrity; then
    echo "❌ State integrity check failed (.ai/state.json signature mismatch)." >&2
    return 1
  fi
  cat "$STATE_FILE"
}

update_state() {
  local key="$1"
  local value="$2"
  if ! ensure_state_integrity; then
    echo "❌ State integrity check failed before update." >&2
    return 1
  fi
  # Use python to update json, convert true/false to True/False for python literal
  local py_val="$value"
  if [ "$value" == "true" ]; then py_val="True"; fi
  if [ "$value" == "false" ]; then py_val="False"; fi
  python3 -c "import json, sys; d=json.load(open('$STATE_FILE')); d['$key']=$py_val; json.dump(d, open('$STATE_FILE', 'w'), indent=2)"
  seal_state
}

set_status() {
  local status="$1"
  update_state "state" "\"$status\""
}

append_history() {
  local key="$1"
  local entry="$2"
  if ! ensure_state_integrity; then
    echo "❌ State integrity check failed before append_history." >&2
    return 1
  fi
  python3 -c "import json, sys; d=json.load(open('$STATE_FILE')); d['$key'].append($entry); json.dump(d, open('$STATE_FILE', 'w'), indent=2)"
  seal_state
}

increment_count() {
  local key="$1"
  if ! ensure_state_integrity; then
    echo "❌ State integrity check failed before increment_count." >&2
    return 1
  fi
  python3 -c "import json, sys; d=json.load(open('$STATE_FILE')); d['$key']+=1; json.dump(d, open('$STATE_FILE', 'w'), indent=2)"
  seal_state
}
