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
