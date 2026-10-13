---
artifact_authority: current
owner: James Chen
status: active
purpose: Conditional claim, verifier, telemetry, release, and benchmark gates.
---

# Claim and Receipt Overlay

Load this overlay for claim, release, benchmark, audit, or verifier work. A
receipt is evidence, not a claim by itself.

## Fail-closed proof

- Receipt adapters must validate verifier artifact/status and source hash;
  never trust `claim_verified=true` alone.
- Missing proof attributes set `gate_passed=false` and record the exact reason.
- Structural gates may validly report `token_usage=0`. When model calls occur,
  receipts must include real execution telemetry such as wall and overhead time.
- `selected`, `dispatched`, or `invoked` is not solve truth. Separate route
  wiring, invocation, consumer use, verifier proof, contribution, and benchmark
  value.
- Production-ready and public-claim states require the physical card-defined
  verifier, approval, and promotion gates; a green subset or prose report does
  not bypass them.

## Nexus Core issue-bound completion evidence

- This repository is enrolled in the standalone `nexus-certify` Golden Path through `.nexus-core/config.toml`.
- For mutation work tracked by a repository-local GitHub Issue, push the branch, then run `scripts/ops/nexus-core-precheck dispatch` (the Claude Code Stop hook does this automatically). It starts the signed Core issue check for the exact pushed HEAD on a trusted runner (30-60 min); the PR gate later reuses that receipt.
- In the completion report, give the Core status from `scripts/ops/nexus-core-precheck status --issue <N>` (`PENDING`, `VERIFIED`, `FAILED`, `NOT_FOUND`). Do not claim engineering completion until it is `VERIFIED`.
- The local `nexus-core-issue-check-local` / `nexus-certify issue-check` run remains optional; it needs Docker and produces an unsigned receipt.
- This binding is Evidence Trust + Completion only. It does not select the execution lane, route, worker/model, Candidate acceptance, merge, release, deployment, or production authority.
- DIRECT work remains transport-neutral. A Core mutation session is not required solely because repository files are being changed.
