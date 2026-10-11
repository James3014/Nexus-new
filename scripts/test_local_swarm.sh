#!/bin/bash
# RETIRED: the v18 Go swarm demo (nexus_swarm/cmd/swarm-manager) targeted proto
# messages that no longer exist and is excluded from the build (build tag
# legacy_v18_demo). The maintained swarm manager is nexus_swarm/manager:
#   cd nexus_swarm && go build ./manager
#   docker build -f manager/Dockerfile nexus_swarm
echo "scripts/test_local_swarm.sh is retired: the v18 swarm demo was removed from the build." >&2
echo "Use nexus_swarm/manager (cd nexus_swarm && go build ./manager)." >&2
exit 78
