#!/bin/bash
# Run a #2721 harness runner with the measurement Gateway's environment.
#   run_with_gateway_env.sh <gateway start.sh or env file> runner|nexus|bare -- <runner args>
# Formal runs use "runner" (block-randomized, every arm); nexus/bare run one
# arm and refuse a paid run without --single-arm-debug.
# start.sh is never executed: gateway_env.py takes only its assignments and
# stops at the first `exec`.  The runner asserts NEXUS_MEASUREMENT_READ_ROOTS.
set -euo pipefail
env_file="$1"; runner="$2"; shift 2
[ "${1:-}" = "--" ] && shift
here="$(cd "$(dirname "$0")/../../.." && pwd)"
case "$runner" in
  runner) module=scripts.bench.measure_2721.runner ;;
  nexus) module=scripts.bench.measure_2721.nexus_driver ;;
  bare)  module=scripts.bench.measure_2721.arms; set -- bare "$@" ;;
  *) echo "runner must be runner, nexus or bare" >&2; exit 2 ;;
esac
cd "$here"
exec "${PYTHON:-python3}" -m "$module" --gateway-env "$env_file" "$@"
