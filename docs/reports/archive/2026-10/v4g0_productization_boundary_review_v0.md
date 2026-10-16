# V4-G.0 Productization Boundary Review

## Status: V4G_PRODUCTIZATION_BOUNDARY_READY

## 1. Current Validated Capability

- Local 7B repair evidence handling
- Direct patch lane (VERBATIM)
- Canonical recovery lane
- Env-sensitive blocker classification
- Verifier-backed receipt
- 14B strict-prompt fallback candidate
- 3B auxiliary advisory (receipt/lane audit)
- Automated compliance checking

## 2. Internal-Only Capability Language

"Nexus has internally validated local 7B repair evidence handling across six real task observations and established guarded internal operations for repair artifact compliance. 14B is available as a strict-prompt fallback candidate. 3B remains auxiliary-only unless separately validated."

## 3. Forbidden Public Claims

- Nexus is production-ready
- Nexus beats benchmark X
- Nexus can repair arbitrary customer repositories
- 14B is generally better than 7B
- 3B can perform repair execution
- Repair outputs are training eligible by default
- Public claims are allowed

## 4. Commercial Demo Safe Framing

- "Internal proof of concept" not "production system"
- "Controlled environment results" not "general capability"
- "Internal validation" not "public benchmark"

## 5. Remaining Gaps Before Customer-Facing Use

- Runtime integration with actual repair pipeline
- Production-grade environment management
- Customer credential handling
- SLA/uptime guarantees
- Public benchmark validation
- Training export pipeline
- 14B full validation (not just strict-prompt)

## 6. Required Safeguards Before Runtime Integration

- Production environment isolation
- Credential management
- Rate limiting
- Error recovery
- Monitoring/alerting
- Rollback capability

## 7. Required Safeguards Before Training Export

- Human review of all exported data
- Claim separation verification
- Attribution audit
- Public claim gate enforcement

## 8. Required Safeguards Before Benchmark Publication

- Full SWE-bench validation
- Cross-repo testing
- Latency/throughput benchmarks
- Comparison with established baselines
- Peer review
