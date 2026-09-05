#!/usr/bin/env bash
set -euo pipefail

# Core Task Cards bind physical evidence under /private/tmp on the campaign
# host. GitHub Ubuntu does not create /private by default, so materialize it
# without changing Candidate code or evidence paths.
sudo mkdir -p /private/tmp
sudo chown "$(id -u):$(id -g)" /private /private/tmp
chmod 0755 /private /private/tmp

# The frozen TG5 Task Card retained the historical `--run-live` spelling, but
# exact TG5 head 10b4cf7 no longer registers that pytest option. The test is
# still explicitly marked `live`; recovery therefore executes the exact same
# test selection with `-m live` and removes only the stale, unregistered flag.
# Keep the repository script immutable and patch only the hosted copy.
sed 's/ -m live --run-live/ -m live/' \
  scripts/ops/core_v1_tg5_tg6_physical_recovery.sh \
  > /tmp/core_v1_tg5_tg6_physical_recovery_hosted_run.sh
chmod 0755 /tmp/core_v1_tg5_tg6_physical_recovery_hosted_run.sh

exec bash /tmp/core_v1_tg5_tg6_physical_recovery_hosted_run.sh
