# ARCHIVED: nexus-swarm-v22-prod

This directory is a stale snapshot of the Swarm deploy package and is **not buildable**
(it has no `go.mod`, `go.sum` or `api/`, yet its Dockerfiles `COPY go.mod go.sum`).
It is kept only for history (repo policy forbids deleting files). Do not deploy from it.

The single maintained, buildable Swarm deploy path is `nexus_swarm/`
(Go module `nexus-swarm`; `manager/`, `node/`, `helm/`, `scripts/`, `api/proto`).
Build the manager image with `nexus_swarm/` as the Docker build context:

    docker build -f nexus_swarm/manager/Dockerfile nexus_swarm
    docker build -f nexus_swarm/node/Dockerfile nexus_swarm

Known drift of this snapshot versus `nexus_swarm/`:

- `manager/dispatch_task.go` still uses `PreferredRegion`, which was removed from the proto.
- `manager/main.go` lacks the async DB upsert worker and gRPC keepalive tuning.
