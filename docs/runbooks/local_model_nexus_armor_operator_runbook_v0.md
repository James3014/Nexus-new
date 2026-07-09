# Local Model Nexus Armor Operator Runbook

## Scope

Cross-phase integration gate for P3 + P6 + P2 + P4 + P5 into unified Armor readiness.

## Phase Responsibilities

### P3: Provider-Assist / Synthetic Candidate Trace
- Synthetic candidate generation only (no real provider)
- Shadow/dry-run authority
- No runtime behavior change

### P6: Quota-Aware Degradation Advisory
- Advisory-only recommendations
- Cannot override P3/P4/P5
- Receipt-backed evidence only

### P2: Apply/Hash/Anchor Truth Authority
- Hash chain verification required
- Anchor truth required for any candidate
- Apply proof required before claim

### P4: Verifier/Claim Gate Authority
- Final verifier authority
- Claim gate required
- No P7/P6 override allowed

### P5: Selection Metadata Boundary
- Selection metadata recorded
- No P6 override of P5 selection

## Env Guard Rules
- NEXUS_ENABLE_P6_QUOTA_DEGRADATION required for any P6 behavior
- NEXUS_P3_CLOUD_WITH_LOCAL_ASSIST required for any P3 cloud behavior
- Both flags off = unchanged behavior

## Dry-Run/Synthetic-Only Restrictions
- No real provider execution
- No live model execution
- No patch application
- No network calls
- No API key usage

## Human Approval Required
- Any real provider/network smoke requires explicit human approval
- P8 human-approved network smoke package required before any live test
- Production rollout requires separate release gate

## Rollback Triggers
- provider_invoked=true
- network_invoked=true
- api_key_used=true
- patch_apply_invoked=true
- runtime_behavior_changed=true
- public_claim_allowed=true
- production_ready=true

## Forbidden Claims
- No production rollout
- No live quota routing
- No solve-rate improvement
- No public claim eligibility
- No production readiness
