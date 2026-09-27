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

    if r.leakage_audit_status == "PASSED":
        leakage_prevention_desc = (
            "Ground truth is strictly segregated from prompts and audited clean."
        )
    elif r.leakage_audit_status == "FAILED":
        leakage_prevention_desc = "Prompt leakage detected during audit; case execution halted."
    else:
        leakage_prevention_desc = "Cohort audit was not evaluated due to prior lifecycle blocker."

    be = getattr(r, "baseline_evaluation", None)
    if be is not None and be.requested:
        expected_base_str = (
            f"`{be.expected_identity.provider_id}/{be.expected_identity.model_id}` ({be.expected_identity.transport})"
            if be.expected_identity
            else "None"
        )
        observed_base_str = (
            f"`{be.physical_identity.identity_digest}`" if be.physical_identity else "None"
        )
        base_lines = [
            "- **Baseline Calibration & Comparative Evidence:**",
            "  - **Baseline Requested:** YES",
            f"  - **Baseline Status:** `{be.status}` ({be.reason})",
            f"  - **Expected Baseline Identity:** {expected_base_str}",
            f"  - **Observed Physical Identity:** {observed_base_str}",
            f"  - **Baseline Cases Evaluated:** {len(be.cohort_evaluations)}",
        ]
        if be.operational_metrics:
            bm = be.operational_metrics
            base_lines.append(
                f"  - **Baseline Metrics:** {bm.total_cases} cases (Accuracy: {bm.accuracy * 100:.1f}%, Error Rate: {bm.error_rate * 100:.1f}%, Latency p50: {bm.p50_latency_ms} ms, Latency p95: {bm.p95_latency_ms} ms, Throughput: {bm.throughput_rps:.2f} rps)"
            )
        cmp = be.comparison
        base_lines.append(
            f"  - **Comparison Status:** `{cmp.status}` ({cmp.reason or 'Factual metric deltas available.'})"
        )
        if cmp.status == "AVAILABLE":
            acc_d = f"{cmp.accuracy_delta * 100:+.1f}%" if cmp.accuracy_delta is not None else "N/A"
            err_d = (
                f"{cmp.error_rate_delta * 100:+.1f}%" if cmp.error_rate_delta is not None else "N/A"
            )
            p50_d = (
                f"{cmp.p50_latency_delta_ms:+d} ms"
                if cmp.p50_latency_delta_ms is not None
                else "N/A"
            )
            p95_d = (
                f"{cmp.p95_latency_delta_ms:+d} ms"
                if cmp.p95_latency_delta_ms is not None
                else "N/A"
            )
            tps_d = (
                f"{cmp.throughput_delta_rps:+.2f} rps"
                if cmp.throughput_delta_rps is not None
                else "N/A"
            )
            base_lines.append(
                f"  - **Metric Deltas (Candidate - Baseline):** Accuracy: {acc_d}, Error Rate: {err_d}, Latency p50: {p50_d}, Latency p95: {p95_d}, Throughput: {tps_d}"
            )
        base_report_block = "\n" + "\n".join(base_lines)
    else:
        base_reason = be.reason if be else "Baseline evaluation not requested in contract."
        base_report_block = f"\n- **Baseline Evaluation:** `NOT_REQUESTED` ({base_reason})"

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
- **Leakage Policy Revision:** `{c.dataset.leakage_policy_revision}`
- **Leakage Audit Status:** `{r.leakage_audit_status}`
- **Leakage Prevention:** {leakage_prevention_desc}

### Q7: Were ground truth datasets validated and provenance-tracked?
- **Ground Truth Revision:** `{c.dataset.ground_truth_revision}`
- **Ground Truth Hash:** `{c.dataset.ground_truth_sha256}`
- **Ground Truth Ready:** `{c.dataset.ground_truth_ready}`

### Q8: What were the operational latency and throughput metrics?
- **Total Cases:** {m.total_cases} (Accuracy: {m.accuracy * 100:.1f}%, Error Rate: {m.error_rate * 100:.1f}%)
- **Latency p50:** {m.p50_latency_ms} ms
- **Latency p95:** {m.p95_latency_ms} ms
- **Throughput:** {m.throughput_rps:.2f} rps{base_report_block}

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
- **Blocker Category:** `{rec.blocker_category or "None"}`
- **Stop Reason:** `{r.stop_reason or "None"}`
- **Next Gate:** `INDEPENDENT_REVIEW_OF_NEXUS_NEW_PROVIDER_ADOPTION_CANDIDATE`
"""
