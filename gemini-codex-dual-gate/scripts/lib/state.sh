#!/bin/bash
STATE_FILE=".ai/state.json"

read_state() {
  cat "$STATE_FILE"
}

update_state() {
  local key="$1"
  local value="$2"
  # Use python to update json, convert true/false to True/False for python literal
  local py_val="$value"
  if [ "$value" == "true" ]; then py_val="True"; fi
  if [ "$value" == "false" ]; then py_val="False"; fi
  python3 -c "import json, sys; d=json.load(open('$STATE_FILE')); d['$key']=$py_val; json.dump(d, open('$STATE_FILE', 'w'), indent=2)"
}

set_status() {
  local status="$1"
  update_state "state" "\"$status\""
}

append_history() {
  local key="$1"
  local entry="$2"
  python3 -c "import json, sys; d=json.load(open('$STATE_FILE')); d['$key'].append($entry); json.dump(d, open('$STATE_FILE', 'w'), indent=2)"
}

increment_count() {
  local key="$1"
  python3 -c "import json, sys; d=json.load(open('$STATE_FILE')); d['$key']+=1; json.dump(d, open('$STATE_FILE', 'w'), indent=2)"
}
