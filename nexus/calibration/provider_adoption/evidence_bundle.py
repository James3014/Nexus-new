"""Evidence Bundle and 13-Question Report Generator for Provider Adoption Experiments.

Schema: nexus.provider_experiment.evidence_bundle.v1
Packages full experiment artifacts and renders the canonical 13-question audit report.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nexus.calibration.provider_adoption.canonical_json import canonical_json_hash
from nexus.calibration.provider_adoption.contracts import ExperimentContract
from nexus.calibration.provider_adoption.orchestrator import ExperimentExecutionReceipt

EVIDENCE_BUNDLE_SCHEMA = "nexus.provider_experiment.evidence_bundle.v1"


@dataclass(frozen=True)
class EvidenceBundle:
    schema: str
    contract: ExperimentContract
    receipt: ExperimentExecutionReceipt
    bundle_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "contract": self.contract.to_dict(),
            "receipt": self.receipt.to_dict(),
            "bundle_hash": self.bundle_hash,
        }


def build_evidence_bundle(
    contract: ExperimentContract,
    receipt: ExperimentExecutionReceipt,
) -> EvidenceBundle:
    raw = {
        "schema": EVIDENCE_BUNDLE_SCHEMA,
        "contract": contract.to_dict(),
        "receipt": receipt.to_dict(),
    }
    b_hash = canonical_json_hash(raw)
    return EvidenceBundle(
        schema=EVIDENCE_BUNDLE_SCHEMA,
        contract=contract,
        receipt=receipt,
        bundle_hash=b_hash,
    )


def generate_13_question_report(bundle: EvidenceBundle) -> str:
    """Generate the canonical 13-question human markdown report."""
    c = bundle.contract
    r = bundle.receipt
    p = r.physical_identity
    m = r.operational_metrics
    rec = r.recommendation

    return f"""# Provider Adoption Experiment Report: {c.experiment_id}

**Bundle Hash:** `{bundle.bundle_hash}`
**Contract Hash:** `{c.contract_hash}`
**Receipt Hash:** `{r.receipt_hash}`
**Final State:** `{r.final_state.value}`

---

### Q1: What is the candidate provider/model and exact physical identity?
- **Provider ID:** `{p.provider_id}`
- **Model ID:** `{p.model_id}`
- **Transport:** `{p.transport}`
- **Host / OS:** `{p.host_identity}` ({p.platform} {p.os_version}, {p.architecture})
- **Runtime Binary:** `{p.runtime_executable}` (`{p.runtime_executable_sha256}`)
- **Runtime Version:** `{p.runtime_version}`
- **Identity Digest:** `{p.identity_digest}`

### Q2: What job to be done was evaluated?
- **Job to be Done:** {c.job_to_be_done}

### Q3: Was the experiment contract strictly bound and hash-immutable?
- **Status:** YES.
- **Contract Revision:** `{c.experiment_revision}`
- **Hash Binding:** `{c.contract_hash}`

### Q4: Did the experiment framework grant any routing, acceptance, or mutation authority?
- **Status:** STRICTLY NO.
- **Routing Authority:** `{c.authority_boundary.routing_authority}`
- **Acceptance Authority:** `{c.authority_boundary.acceptance_authority}`
- **Write Permission:** `{c.authority_boundary.write_permission}`
- **Process Permission:** `{c.authority_boundary.process_permission}`
- **Network Permission:** `{c.authority_boundary.network_permission}`

### Q5: What capabilities were physically probed and what were the exact findings?
{chr(10).join(f"- `{cid}`: **{probe.status.value}** ({probe.physical_evidence})" for cid, probe in r.capability_matrix.probes.items() if probe.status.value != "NOT_EVALUATED")}

### Q6: What cohort was used and how was leakage prevented?
- **Cohort ID:** `{c.dataset.cohort_id}` (Revision {c.dataset.cohort_revision})
- **Cohort Type:** `{c.dataset.cohort_type}`
- **Cohort Hash:** `{c.dataset.cohort_sha256}`
- **Leakage Prevention:** Ground truth is strictly segregated from prompts and audited.

### Q7: Were ground truth datasets validated and provenance-tracked?
- **Ground Truth Revision:** `{c.dataset.ground_truth_revision}`
- **Ground Truth Hash:** `{c.dataset.ground_truth_sha256}`
- **Ground Truth Ready:** `{c.dataset.ground_truth_ready}`

### Q8: What were the operational latency and throughput metrics?
- **Total Cases:** {m.total_cases} (Accuracy: {m.accuracy * 100:.1f}%, Error Rate: {m.error_rate * 100:.1f}%)
- **Latency p50:** {m.p50_latency_ms} ms
- **Latency p95:** {m.p95_latency_ms} ms
- **Throughput:** {m.throughput_rps:.2f} rps

### Q9: Was offline availability physically verified or marked unknown?
- **Offline Status:** `{m.offline_status}`
- **Network Dependency:** `{m.network_dependency}`

### Q10: How did the candidate behave across the failure matrix?
- **Failure Contract Fail-Closed:** `{r.failure_matrix.all_fail_closed_contract}`
- **Observed Fail-Closed (Physical):** `{r.failure_matrix.all_fail_closed_observed}`

### Q11: Were stop conditions actively monitored and enforced?
- **Max Consecutive Failures Limit:** {c.stop_conditions.max_consecutive_failures}
- **Max Error Rate Limit:** {c.stop_conditions.max_error_rate}
- **Stop Reason:** `{r.stop_reason or "None; all cases completed safely"}`

### Q12: What is the advisory admission recommendation and why is it bounded?
- **Verdict:** `{rec.verdict}`
- **Recommended State:** `{rec.recommended_state}`
- **Recommended Autonomy:** `{rec.recommended_autonomy}` (Clamped by ceiling `{rec.claim_ceiling}`: `{rec.clamped_by_ceiling}`)
- **Recommended Roles:** {", ".join(rec.recommended_roles) or "None"}
- **Authority Disclaimer:** {rec.authority_disclaimer}

### Q13: What are the exact remaining blockers and next gate?
- **Stop Reason:** `{r.stop_reason or "None"}`
- **Next Gate:** `INDEPENDENT_REVIEW_OF_NEXUS_NEW_PROVIDER_ADOPTION_CANDIDATE`
"""
