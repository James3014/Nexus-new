from __future__ import annotations

from pathlib import Path
from typing import Any

from nexus.engine.asi_constraints import ASIConstraintExtractor, ASIConstraintStore
from nexus.engine.runtime_capability_receipts import emit_harness_runtime_receipts, write_runtime_receipt_json
from nexus.research.architecture_scout import DistantScoutPlanner
from nexus.research.formal_report_service import FormalReportService


def _write_runtime_receipt_json(repo_root: Path, *, category: str, receipt_slug: str, payload: dict[str, Any]) -> str:
    return write_runtime_receipt_json(repo_root, category=category, receipt_slug=receipt_slug, payload=payload)


def stringify_claims(rows: list[Any]) -> list[str]:
    out: list[str] = []
    for row in rows or []:
        if isinstance(row, dict):
            value = row.get("claim") or row.get("reason") or row.get("source") or row
        else:
            value = row
        text = str(value).strip()
        if text:
            out.append(text)
    return out


def augment_semantic_runtime_capabilities(
    *,
    repo_root: Path,
    task_id: str | None,
    task_desc: str,
    task_type: str,
    target_file: str | None,
    receipt_slug: str,
    selected_capabilities: set[str],
    nexus_usage_trace: dict[str, Any],
    route: dict[str, Any],
    asi_ledger: list[dict[str, Any]],
    plateau: dict[str, Any],
    artifact_verified: bool,
    normalized_success_criteria: str,
) -> None:
    capabilities = nexus_usage_trace.setdefault("capabilities", {})
    research_context = route.get("research_context", {}) if isinstance(route.get("research_context"), dict) else {}

    emit_harness_runtime_receipts(
        repo_root=repo_root,
        task_desc=task_desc,
        task_type=task_type,
        receipt_slug=receipt_slug,
        selected_capabilities=selected_capabilities,
        capabilities=capabilities,
        route=route,
        artifact_verified=artifact_verified,
    )

    if {"judge_panel", "llm_judge_panel"} & selected_capabilities:
        autoreason = nexus_usage_trace.get("autoreason", {}) if isinstance(nexus_usage_trace.get("autoreason"), dict) else {}
        votes = autoreason.get("judge_votes", []) if isinstance(autoreason.get("judge_votes"), list) else []
        winner = str(autoreason.get("winner") or "").strip()
        judge_mode = str(autoreason.get("judge_mode") or autoreason.get("mode") or "deterministic_evidence_quality").strip()
        if votes and winner:
            report = {
                "schema": "nexus_judge_panel_receipt_v1",
                "task_id": task_id or receipt_slug,
                "winner": winner,
                "votes": votes,
                "borda_scores": autoreason.get("borda_scores", {}),
                "judge_mode": judge_mode,
                "status": autoreason.get("status", ""),
            }
            report_path = _write_runtime_receipt_json(
                repo_root,
                category="judge_panel",
                receipt_slug=receipt_slug,
                payload=report,
            )
            capabilities["judge_panel_used"] = True
            capabilities["judge_panel_votes"] = votes
            capabilities["judge_panel_winner"] = winner
            capabilities["judge_panel_mode"] = judge_mode
            capabilities["judge_panel_report_path"] = report_path
            capabilities["judge_panel_gate_passed"] = bool(artifact_verified)
            # Backward-compatible trace keys for older reports and route audits.
            capabilities["llm_judge_panel_used"] = True
            capabilities["llm_judge_panel_votes"] = votes
            capabilities["llm_judge_panel_winner"] = winner
            capabilities["llm_judge_panel_mode"] = judge_mode
            capabilities["llm_judge_panel_report_path"] = report_path
            capabilities["llm_judge_panel_gate_passed"] = bool(artifact_verified)

    if "asi_constraint_extractor" in selected_capabilities:
        constraints_packet = ASIConstraintExtractor().extract(asi_ledger, task_id=task_id or receipt_slug)
        constraints = constraints_packet.get("constraints", []) if isinstance(constraints_packet.get("constraints"), list) else []
        blocked = [str(item) for item in (research_context.get("blocked_assumptions", []) or []) if str(item).strip()]
        lookup = research_context.get("constraint_lookup_receipt", {}) if isinstance(research_context.get("constraint_lookup_receipt"), dict) else {}
        lookup_refs = [str(item) for item in lookup.get("constraint_refs", []) or [] if str(item).strip()]
        if constraints or blocked:
            constraint_store_path = ASIConstraintStore(repo_root).append_constraints(constraints)
            report = {
                "schema": "nexus_asi_constraint_runtime_receipt_v1",
                "task_id": task_id or receipt_slug,
                "constraints_packet": constraints_packet,
                "blocked_assumptions": blocked,
                "constraint_lookup_receipt": lookup,
                "global_constraint_store_path": constraint_store_path,
            }
            capabilities["asi_constraints"] = constraints
            capabilities["blocked_assumptions"] = blocked
            capabilities["asi_constraint_lookup_refs"] = lookup_refs
            capabilities["asi_constraint_lookup_matched_count"] = int(lookup.get("matched_count", len(lookup_refs)) or 0)
            capabilities["asi_constraint_lookup_store_path"] = str(lookup.get("store_path") or "")
            capabilities["asi_constraint_report_path"] = _write_runtime_receipt_json(
                repo_root,
                category="asi_constraint_extractor",
                receipt_slug=receipt_slug,
                payload=report,
            )
            capabilities["asi_constraint_gate_passed"] = bool(artifact_verified and (constraints or blocked))

    if "architecture_scout" in selected_capabilities:
        scout_plateau = plateau if bool(plateau.get("detected")) else {
            "detected": True,
            "reason": "architecture_scout_selected_without_plateau",
            "family": "flow:architecture_boundary_probe",
        }
        plan = DistantScoutPlanner().plan(task_desc=task_desc, plateau=scout_plateau, asi_ledger=asi_ledger)
        if str(plan.get("status") or "") == "READY":
            report_path = _write_runtime_receipt_json(
                repo_root,
                category="architecture_scout",
                receipt_slug=receipt_slug,
                payload=plan,
            )
            architecture_refs = [str(item) for item in plan.get("architecture_actions", []) if str(item).strip()]
            blast_radius_refs = []
            if target_file:
                blast_radius_refs.append(str(target_file))
            codeintel = nexus_usage_trace.get("codeintel", {}) if isinstance(nexus_usage_trace.get("codeintel"), dict) else {}
            blast_radius_refs.extend(str(item) for item in codeintel.get("files", []) or [] if str(item).strip())
            capabilities["architecture_scout_used"] = True
            capabilities["architecture_scout_report_path"] = report_path
            capabilities["architecture_refs"] = architecture_refs
            capabilities["blast_radius_refs"] = list(dict.fromkeys(blast_radius_refs))
            capabilities["architecture_scout_gate_passed"] = bool(artifact_verified and architecture_refs)

    if "external_doc_scout" in selected_capabilities:
        doc_scout = research_context.get("doc_scout", {}) if isinstance(research_context.get("doc_scout"), dict) else {}
        hits = doc_scout.get("hits", []) if isinstance(doc_scout.get("hits"), list) else []
        refs = []
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            ref = str(hit.get("source_url") or hit.get("path") or "").strip()
            if ref:
                refs.append(ref)
        verified = stringify_claims(research_context.get("verified_claims", []) or [])
        rejected = stringify_claims(research_context.get("rejected_claims", []) or [])
        external_meta = doc_scout.get("external_metadata", {}) if isinstance(doc_scout.get("external_metadata"), dict) else {}
        providers_used = [str(item) for item in external_meta.get("providers_used", []) or [] if str(item).strip()]
        provider_errors = [str(item) for item in external_meta.get("provider_errors", []) or [] if str(item).strip()]
        verified_source_count = int(external_meta.get("verified_source_count", len(set(refs))) or 0)
        source_count = int(external_meta.get("source_count", verified_source_count) or 0)
        error_count = int(external_meta.get("error_count", len(provider_errors)) or 0)
        latency_ms = float(external_meta.get("latency_ms", 0.0) or 0.0)
        cache_age_sec = float(external_meta.get("cache_age_sec", 0.0) or 0.0)
        cache_status = str(external_meta.get("cache_status") or "disabled")
        verified_external = bool(refs and verified_source_count > 0)
        if refs or verified or rejected:
            report = {
                "schema": "nexus_external_doc_scout_receipt_v1",
                "task_id": task_id or receipt_slug,
                "external_doc_refs": refs,
                "verified_claims": verified,
                "rejected_claims": rejected,
                "providers_used": providers_used,
                "provider_errors": provider_errors,
                "cache_status": cache_status,
                "verified_source_count": verified_source_count,
                "source_count": source_count,
                "error_count": error_count,
                "latency_ms": latency_ms,
                "cache_age_sec": cache_age_sec,
            }
            report_path = _write_runtime_receipt_json(
                repo_root,
                category="external_doc_scout",
                receipt_slug=receipt_slug,
                payload=report,
            )
            capabilities["external_doc_scout_diagnostic_path"] = report_path
            capabilities["external_doc_scout_diagnostic_rejected_claims"] = rejected
            if verified_external:
                capabilities["external_doc_scout_used"] = True
                capabilities["external_doc_refs"] = list(dict.fromkeys(refs))
                capabilities["verified_claims"] = verified
                capabilities["rejected_claims"] = rejected
                capabilities["external_doc_scout_providers_used"] = providers_used
                capabilities["external_doc_scout_provider_errors"] = provider_errors
                capabilities["external_doc_scout_cache_status"] = cache_status
                capabilities["external_doc_scout_verified_source_count"] = verified_source_count
                capabilities["external_doc_scout_source_count"] = source_count
                capabilities["external_doc_scout_error_count"] = error_count
                capabilities["external_doc_scout_latency_ms"] = latency_ms
                capabilities["external_doc_scout_cache_age_sec"] = cache_age_sec
                capabilities["external_doc_scout_report_path"] = report_path
                capabilities["external_doc_scout_gate_passed"] = bool(artifact_verified and verified_external)

    if "formal_report" in selected_capabilities:
        service = FormalReportService()
        verification = [
            {
                "command": normalized_success_criteria,
                "status": "PASS" if artifact_verified else "BLOCKED",
            }
        ]
        route_receipts = [
            {
                "name": "artifact_gate",
                "evidence_present": bool(capabilities.get("artifact_refs")),
                "gate_passed": bool(capabilities.get("artifact_gate_passed", False)),
            },
            {
                "name": "judge_panel",
                "evidence_present": bool(capabilities.get("judge_panel_report_path")),
                "gate_passed": bool(capabilities.get("judge_panel_gate_passed", False)),
            },
        ]
        autoreason = nexus_usage_trace.get("autoreason", {}) if isinstance(nexus_usage_trace.get("autoreason"), dict) else {}
        critique = autoreason.get("adversarial_critique", {}) if isinstance(autoreason.get("adversarial_critique"), dict) else {}
        if critique:
            winner = str(autoreason.get("winner") or "").strip()
            discriminator_refs: list[str] = []
            winner_failed_discriminator = False
            for candidate_id, result in sorted(critique.items()):
                if not isinstance(result, dict):
                    continue
                candidate = str(candidate_id)
                if bool(result.get("fatal")):
                    discriminator_refs.append(f"discriminator_fatal:{candidate}")
                    if candidate == winner:
                        winner_failed_discriminator = True
                critiques = result.get("critiques", []) if isinstance(result.get("critiques"), list) else []
                defenses = result.get("defenses", []) if isinstance(result.get("defenses"), list) else []
                if critiques:
                    discriminator_refs.append(f"discriminator_critiques:{candidate}:{len(critiques)}")
                if defenses:
                    discriminator_refs.append(f"discriminator_defenses:{candidate}:{len(defenses)}")
            route_receipts.append(
                {
                    "name": "autoreason",
                    "evidence_present": bool(discriminator_refs),
                    "gate_passed": bool(artifact_verified and not winner_failed_discriminator),
                    "winner": winner,
                    "discriminator_refs": discriminator_refs,
                }
            )
        report = service.build(
            title=f"Nexus Formal Evidence Report: {task_id or receipt_slug}",
            hypothesis=task_desc,
            asi_constraints=capabilities.get("asi_constraints", []) or [],
            judge_votes=capabilities.get("judge_panel_votes", []) or capabilities.get("llm_judge_panel_votes", []) or [],
            verification=verification,
            route_receipts=route_receipts,
        )
        rel_path = Path(".nexus") / "reports" / "formal" / f"{receipt_slug}.md"
        report_path = service.write_markdown(repo_root=repo_root, path=rel_path, report=report)
        capabilities["formal_report_path"] = report_path
        capabilities["formal_report_schema_version"] = str(report.get("schema") or "")
        capabilities["verification_summary_ref"] = f"{normalized_success_criteria}:{verification[0]['status']}"
        capabilities["formal_report_gate_passed"] = bool(report.get("status") == "READY" and artifact_verified)
