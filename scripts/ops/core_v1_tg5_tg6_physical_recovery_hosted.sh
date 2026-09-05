#!/usr/bin/env bash
set -euo pipefail

# Core Task Cards intentionally bind physical evidence under /private/tmp on the
# campaign host. GitHub Ubuntu runners do not create /private by default, so
# the controller recovery host materializes that path without changing the
# Candidate or the Task Card-visible evidence locations.
sudo mkdir -p /private/tmp
sudo chown "$(id -u):$(id -g)" /private /private/tmp
chmod 0755 /private /private/tmp

exec bash scripts/ops/core_v1_tg5_tg6_physical_recovery.sh
