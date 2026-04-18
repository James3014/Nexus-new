#!/bin/bash

calculate_hash() {
  local file="$1"
  if [ -f "$file" ]; then
    shasum -a 256 "$file" | cut -d' ' -f1
  else
    echo ""
  fi
}

generate_changed_files() {
  git diff --name-status HEAD > .ai/changed-files.md
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
