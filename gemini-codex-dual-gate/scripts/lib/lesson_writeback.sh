#!/bin/bash

persist_lesson_to_nexus() {
  local task_id="$1"
  local raw_lesson="$2"
  local category="$3"
  local root_cause="$4"
  local corrective_action="$5"
  local source_phase="C"
  local outcome="failure"

  # Convert arguments to JSON safe format
  local py_script=$(cat <<EOF
import json, sys, os
from pathlib import Path
from nexus.services.continuous_learning import persist_structured_lesson

try:
    repo_root = Path(os.getcwd())
    event = persist_structured_lesson(
        repo_root=repo_root,
        task_id="$task_id",
        raw_lesson="$raw_lesson",
        category="$category",
        root_cause="$root_cause",
        corrective_action="$corrective_action",
        source_phase="$source_phase",
        outcome="$outcome",
        evidence=[],
        artifact_refs=[]
    )
    # Output only the lesson_id
    print(event.lesson_id)
except Exception as e:
    print(f"ERROR: {str(e)}", file=sys.stderr)
    sys.exit(1)
EOF
)
  
  # Run the python script
  LESSON_ID=$(python3 -c "$py_script" 2> >(sed 's/^/STDERR: /' >&2))
  local status=$?

  if [ $status -eq 0 ] && [ ! -z "$LESSON_ID" ]; then
    echo "$LESSON_ID"
    return 0
  else
    return 1
  fi
}
