---
name: sf-systematic-governance_and_trust-aegisops-ai-0aa841e2
description: Autonomous DevSecOps & FinOps Guardrails. Orchestrates Gemini 3 Flash to audit Linux Kernel patches, Terraform cost drifts, and K8s compliance.
metadata: {"source_status":"systematic_compiled_interface", "runtime_eligible":false, "ablation_eligible":true}
---

# aegisops-ai

## Load when
- Kernel Patch Review:** Auditing raw C-based Git diffs for memory safety.
- Pre-Apply IaC Audit:** Analyzing `terraform plan` outputs to prevent bill spikes.
- Cluster Hardening:** Generating "Least Privilege" securityContexts for deployments.
- CI/CD Quality Gating:** Blocking non-compliant merges via GitHub Actions.

## Do not load when
- Direct Resource Mutation:** This is an *auditor*, not a deployment tool. It does not execute `terraform apply` or `kubectl apply`.
- Post-Mortem Analysis:** For analyzing *why* a previous AI session failed, use `/analyze-project` instead.
- 

## Required receipts
- selected
- injected
- used
- evidence_present
- gate_passed
- outcome_contributed

## Source
- /private/tmp/nexus-sf-round4/sickn33-antigravity-awesome-skills/plugins/antigravity-awesome-skills/skills/aegisops-ai/SKILL.md
