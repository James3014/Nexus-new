#!/bin/bash
set -euo pipefail

calculate_hash() {
  local file="$1"
  if [ -f "$file" ]; then
    shasum -a 256 "$file" | cut -d' ' -f1
  else
    echo ""
  fi
}

generate_changed_files() {
  {
    echo "## Staged"
    git diff --cached --name-status
    echo
    echo "## Unstaged"
    git diff --name-status
  } > .ai/changed-files.md
}

has_real_changes() {
  if [ -n "$(git diff --cached --name-only)" ] || [ -n "$(git diff --name-only)" ]; then
    return 0
  fi
  return 1
}

load_test_commands() {
  local cmds=()
  if [ -n "${NEXUS_TEST_COMMANDS:-}" ]; then
    # Split by newlines.
    while IFS= read -r line; do
      [ -z "${line// }" ] && continue
      cmds+=("$line")
    done <<< "$NEXUS_TEST_COMMANDS"
  elif [ -f ".ai/test-commands.txt" ]; then
    while IFS= read -r line; do
      [ -z "${line// }" ] && continue
      [[ "$line" =~ ^# ]] && continue
      cmds+=("$line")
    done < .ai/test-commands.txt
  fi

  printf "%s\n" "${cmds[@]}"
}

run_test_commands_or_fail() {
  local cmds=()
  while IFS= read -r line; do
    [ -z "${line// }" ] && continue
    cmds+=("$line")
  done < <(load_test_commands)
  if [ "${#cmds[@]}" -eq 0 ]; then
    echo "❌ Missing test commands. Provide NEXUS_TEST_COMMANDS or .ai/test-commands.txt."
    return 1
  fi

  : > .ai/test-results.md
  for cmd in "${cmds[@]}"; do
    {
      echo "\$ $cmd"
      eval "$cmd"
      rc=$?
      echo "exit_code: $rc"
      if [ "$rc" -ne 0 ]; then
        echo "❌ command failed: $cmd"
        exit "$rc"
      fi
      echo
    } >> .ai/test-results.md 2>&1
  done
}

check_artifacts() {
  local required=("task.md" "constraints.md" "plan.md" "acceptance.md")
  for f in "${required[@]}"; do
    if [ ! -f ".ai/$f" ]; then
      echo "MISSING: .ai/$f"
      return 1
    fi
  done
  return 0
}
