#!/bin/bash

MAX_REVIEWS=5

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
