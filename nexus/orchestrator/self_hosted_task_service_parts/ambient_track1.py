"""Ambient-Core / Track-1 members of ``SelfHostedTaskService``.

Big-file split S10 (Issue #2692). ``_AmbientTrack1Mixin`` holds, moved out of
``nexus/orchestrator/self_hosted_task_service.py``:

* ``_ambient_core_required``, ``_prepare_ambient_core`` and ``_revalidate_ambient_core``:
  whether a request needs the ambient Core envelope, and the mutation binding opened /
  re-validated through the instance's ``ambient_core_port``;
* the static ``_card_evidence_binding_error`` and ``_direct_lane_claims_evidence``: the
  declared evidence universe and the Core requirement bound to the hashed Task Card
  (#2181), and whether a request claims evidence (and so may not take the direct lane);
* the static ``_core_blocked_receipt`` and ``_verify_ambient_core_candidate``: Core's
  verdict on a verified Candidate, as a recorded receipt or ``AmbientCoreVerdictBlocked``;
* ``_record_track1_verified_outcome``: the telemetry-only mirror of a natural self-hosted
  Candidate into Track-1 research evidence.

Their source lines are verbatim, except that every facade-module name they load at run
time (``ambient_core_required``, ``normalize_preparation``, ``build_core_verdict``,
``normalize_verification_projection``, ``projection_hash``, ``AmbientCoreVerdictBlocked``,
``parse_task_card_expected_evidence``, ``_resolve_task_card_path``, ``replace`` and
``subprocess``) is resolved at call time through ``_service_module()``, so patches on the
facade keep taking effect; ``hashlib`` and ``json`` are imported by the part itself.  So is ``__file__``:
``_record_track1_verified_outcome`` passes ``Path(__file__).resolve().parents[2]`` (the
repository root) to the research-experiment refresh, and that must stay the facade's file.

Not all of it is pure: ``_prepare_ambient_core`` / ``_revalidate_ambient_core`` /
``_verify_ambient_core_candidate`` call the ambient Core control port (its transport and
any Core-side state are the port's), the card checks read the Task Card file, and
``_record_track1_verified_outcome`` runs ``git diff`` in the Target worktree and writes
research evidence under the configured evidence root (failures are returned as bounded
metadata).  None of them takes the state lock or writes task state; members are reached
through ``self``.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Optional

if TYPE_CHECKING:
    from nexus.executors.worker_contract import WorkerExecutionReceipt
    from nexus.orchestrator.ambient_core import AmbientCoreControlPort, AmbientCoreVerdictBlocked
    from nexus.orchestrator.candidate_verifier import VerifiedCandidateReceipt


def _service_module():
    # Late binding: the service imports this module at its top level, so its own
    # (and its patched) names are only resolved once a method runs.
    return importlib.import_module("nexus.orchestrator.self_hosted_task_service")


class _AmbientTrack1Mixin:
    """Mixin base of ``SelfHostedTaskService``; never instantiated on its own."""

    if TYPE_CHECKING:  # provided by SelfHostedTaskService (set in its constructor)
        ambient_core_port: Optional[AmbientCoreControlPort]

    # fmt: off
    def _ambient_core_required(self, contract, request: Mapping[str, Any]) -> bool:
        return _service_module().ambient_core_required(request)

    def _prepare_ambient_core(
        self,
        contract,
        request: Mapping[str, Any],
        lease,
        state: Mapping[str, Any],
        *,
        task_id: str,
        attempt_id: str,
    ) -> Mapping[str, Any]:
        if not self._ambient_core_required(contract, request):
            raise RuntimeError("AMBIENT_CORE_PREPARATION_NOT_REQUIRED")
        if self.ambient_core_port is None:
            raise RuntimeError("AMBIENT_CORE_CONTROL_PORT_REQUIRED")
        prepared = self.ambient_core_port.open_or_reuse_mutation_binding(
            contract=contract,
            request=request,
            lease=lease,
            state=state,
            task_id=task_id,
            attempt_id=attempt_id,
        )
        return _service_module().normalize_preparation(prepared, attempt_id=attempt_id)

    def _revalidate_ambient_core(
        self,
        preparation: Mapping[str, Any],
        contract,
        request: Mapping[str, Any],
        lease,
        state: Mapping[str, Any],
        *,
        task_id: str,
        attempt_id: str,
        active_provider: str,
    ) -> None:
        if not self._ambient_core_required(contract, request):
            raise RuntimeError("AMBIENT_CORE_PREPARATION_UNEXPECTED")
        if self.ambient_core_port is None:
            raise RuntimeError("AMBIENT_CORE_CONTROL_PORT_REQUIRED")
        normalized = _service_module().normalize_preparation(preparation, attempt_id=attempt_id)
        self.ambient_core_port.revalidate_mutation_binding(
            normalized,
            contract=contract,
            request=request,
            lease=lease,
            state=state,
            task_id=task_id,
            attempt_id=attempt_id,
            active_provider=active_provider,
        )

    @staticmethod
    def _card_evidence_binding_error(contract, request: Mapping[str, Any]) -> Optional[str]:
        """Bind the declared universe and the Core requirement to the hashed card (#2181).

        Runs for every task, before the Core short-circuit, at intake and at
        finalize. A card that declares a universe cannot be satisfied by a
        request that drops it, and a universe never comes from anywhere but
        the card. For a card-less legacy request nothing is read.
        """
        universe = getattr(contract, "expected_evidence", None)
        dump = getattr(universe, "model_dump", None)
        declared_by_contract = dump(mode="json") if callable(dump) else universe
        core_required = _service_module().ambient_core_required(request)
        claims_evidence = declared_by_contract is not None or core_required
        card_path = request.get("task_card_path")
        raw_hash = request.get("task_card_hash")
        card_hash = raw_hash if isinstance(raw_hash, str) and raw_hash else None
        if not isinstance(card_path, str) or not card_path:
            return (
                "EXPECTED_EVIDENCE_UNIVERSE_NOT_CARD_BOUND"
                if declared_by_contract is not None
                else None
            )
        # The card is read whenever a path is supplied, with or without a hash,
        # so omitting the hash cannot hide a universe card.
        try:
            card_bytes = _service_module()._resolve_task_card_path(card_path).read_bytes()
        except OSError:
            # Legacy binding errors stay with the existing card-binding gates.
            return "EXPECTED_EVIDENCE_TASK_CARD_UNREADABLE" if claims_evidence else None
        if card_hash is not None and hashlib.sha256(card_bytes).hexdigest() != card_hash:
            return "EXPECTED_EVIDENCE_TASK_CARD_HASH_MISMATCH" if claims_evidence else None
        try:
            declared_by_card = _service_module().parse_task_card_expected_evidence(card_bytes.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return "EXPECTED_EVIDENCE_TASK_CARD_INVALID"
        if declared_by_card != declared_by_contract:
            return "EXPECTED_EVIDENCE_UNIVERSE_CARD_MISMATCH"
        if core_required != (declared_by_card is not None):
            return "CORE_ENVELOPE_REQUIRED_CARD_MISMATCH"
        if declared_by_card is not None and card_hash is None:
            # A universe is honoured only from a hash-bound card.
            return "EXPECTED_EVIDENCE_TASK_CARD_HASH_MISSING"
        return None

    @staticmethod
    def _direct_lane_claims_evidence(request: Mapping[str, Any]) -> bool:
        if request.get("expected_evidence") is not None or request.get("core_envelope_required"):
            return True
        card_path = request.get("task_card_path")
        if not isinstance(card_path, str) or not card_path:
            return False
        # Any supplied card is read, hash or no hash: the direct lane must not
        # be reachable by omitting the hash of a universe card. A card that
        # cannot be read or parsed fails closed for this lane.
        try:
            card_bytes = _service_module()._resolve_task_card_path(card_path).read_bytes()
            return _service_module().parse_task_card_expected_evidence(card_bytes.decode("utf-8")) is not None
        except (OSError, UnicodeDecodeError, ValueError):
            return True

    @staticmethod
    def _core_blocked_receipt(
        verified: VerifiedCandidateReceipt, verdict: Mapping[str, Any]
    ) -> VerifiedCandidateReceipt:
        reasons = [
            f"AMBIENT_CORE:{code}"
            for code in (*verdict.get("host_reason_codes", ()), *verdict.get("reason_codes", ()))
        ]
        return _service_module().replace(
            verified,
            verified=False,
            candidate_commit_allowed=False,
            core_provenance_required=True,
            # Never "VERIFIED" on a blocked receipt, even when Core said so;
            # Core's own status stays in ``core_verdict``.
            core_verification_status=f"HOST_BLOCKED:{verdict.get('core_status') or 'UNAVAILABLE'}",
            core_verification_result_hash=str(verdict.get("projection_hash") or ""),
            core_verdict=dict(verdict),
            failure_reasons=[*verified.failure_reasons, *reasons],
        )

    def _verify_ambient_core_candidate(
        self,
        *,
        contract,
        request: Mapping[str, Any],
        lease,
        state: Mapping[str, Any],
        candidate,
        verified: VerifiedCandidateReceipt,
    ) -> VerifiedCandidateReceipt:
        """Obtain and record Core's verdict; raise ``AmbientCoreVerdictBlocked`` when blocked.

        The blocked exception carries the durable blocked receipt so the
        caller can persist the verdict before failing the attempt.
        """

        def blocked(message: str, verdict: Mapping[str, Any]) -> AmbientCoreVerdictBlocked:
            receipt = self._core_blocked_receipt(verified, verdict)
            return _service_module().AmbientCoreVerdictBlocked(message, receipt=receipt, verdict=verdict)

        def fail_closed(code: str) -> AmbientCoreVerdictBlocked:
            verdict = _service_module().build_core_verdict(contract=contract, projection=None, transport_error=code)
            return blocked(code, verdict)

        # Card binding first: dropping the universe must not reach the
        # legacy short-circuit below.
        card_error = self._card_evidence_binding_error(contract, request)
        if card_error is not None:
            raise fail_closed(card_error)
        if not self._ambient_core_required(contract, request):
            return verified
        if self.ambient_core_port is None:
            raise fail_closed("AMBIENT_CORE_CONTROL_PORT_REQUIRED")
        attempt_id = str(state.get("attempt_id") or "")
        try:
            preparation = _service_module().normalize_preparation(
                state.get("host_preparation") or {}, attempt_id=attempt_id
            )
        except RuntimeError as exc:
            raise fail_closed(str(exc)) from exc
        try:
            raw_projection = self.ambient_core_port.verify_candidate(
                preparation=preparation,
                contract=contract,
                request=request,
                lease=lease,
                state=state,
                candidate=candidate,
                verifier_evidence=verified.verifier_evidence,
            )
        except Exception as exc:
            code = str(exc).split(":", 1)[0].strip() or type(exc).__name__
            raise fail_closed(f"CORE_TRANSPORT_FAILED:{code}") from exc
        verdict = _service_module().build_core_verdict(contract=contract, projection=raw_projection)
        if verdict["blocking"]:
            raise blocked(verdict["host_reason_codes"][0], verdict)
        try:
            projection = _service_module().normalize_verification_projection(
                raw_projection,
                preparation=preparation,
                candidate_state_hash=verified.candidate_state_hash,
            )
        except RuntimeError as exc:
            verdict = {
                **verdict,
                "blocking": True,
                "coverage_complete": False,
                "host_reason_codes": [*verdict["host_reason_codes"], str(exc)],
            }
            raise blocked(str(exc), verdict) from exc
        hashes = projection["core_response"]["hashes"]
        return _service_module().replace(
            verified,
            core_provenance_required=True,
            core_binding_hash=preparation["binding_hash"],
            core_mutation_session_id=preparation["session_id"],
            core_verification_status="VERIFIED",
            core_change_set_hash=hashes["change_set_hash"],
            core_evidence_bundle_hash=hashes["evidence_bundle_hash"],
            core_verification_result_hash=_service_module().projection_hash(projection),
            core_verdict=verdict,
            # Coverage never grants authority: commit stays tied to the
            # verified result alone.
            candidate_commit_allowed=verified.verified,
        )

    def _record_track1_verified_outcome(
        self,
        *,
        contract,
        lease,
        state: Mapping[str, Any],
        candidate,
        verified: VerifiedCandidateReceipt,
        execution: WorkerExecutionReceipt,
    ) -> dict[str, Any]:
        """Mirror one natural self-hosted Candidate into Track-1 research evidence.

        This is telemetry only. It reuses the existing candidate-evidence and
        trajectory contracts and never changes selection, verification,
        acceptance, routing, or admission. Failures are returned as bounded
        metadata so the caller can preserve runtime behavior.
        """
        from nexus.research.clm_system_one.research_evidence_root import (
            explicit_research_evidence_root_configured,
        )

        if not explicit_research_evidence_root_configured():
            return {"status": "SKIPPED", "reason": "shared_evidence_root_not_configured"}

        provider = str(getattr(execution, "provider", "") or "")
        attempt_id = str(state.get("attempt_id") or "")
        if not provider or not attempt_id:
            return {"status": "SKIPPED", "reason": "trajectory_identity_missing"}

        try:
            from nexus.research.clm_system_one.candidate_evidence_collector import (
                collect_candidate_group,
            )
            from nexus.research.clm_system_one.trajectory_continuity import (
                bind_trajectory_outcome,
                refresh_registered_experiment,
                resolve_research_evidence_root,
                self_hosted_worker_trajectory_id,
            )

            repo_root = str(
                getattr(contract, "controller_repo_root", "")
                or getattr(contract, "target_repo_root", "")
            )
            evidence_root = resolve_research_evidence_root(repo_root)
            trajectory_id = self_hosted_worker_trajectory_id(
                task_id=str(contract.task_id),
                attempt_id=attempt_id,
                provider=provider,
            )
            source_revision = str(
                getattr(contract, "target_base_revision", "")
                or getattr(contract, "controller_revision", "")
            )
            diff_proc = _service_module().subprocess.run(
                ["git", "diff", "--binary", "--no-ext-diff", source_revision, "--"],
                cwd=str(lease.target_worktree),
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            tracked_diff = diff_proc.stdout if diff_proc.returncode in {0, 1} else ""
            candidate_payload = json.dumps(
                {
                    "schema": "nexus.self_hosted_candidate_payload.v1",
                    "tracked_diff": tracked_diff,
                    "tracked_diff_sha256": str(getattr(candidate, "tracked_diff_sha256", "") or ""),
                    "untracked_content_hashes": dict(
                        getattr(candidate, "untracked_content_hashes", {}) or {}
                    ),
                    "changed_files": list(getattr(candidate, "changed_files", ()) or ()),
                    "untracked_files": list(getattr(candidate, "untracked_files", ()) or ()),
                    "deleted_files": list(getattr(candidate, "deleted_files", ()) or ()),
                    "candidate_state_hash": str(
                        getattr(candidate, "candidate_state_hash", "") or ""
                    ),
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            )

            verifier_rows = list(getattr(verified, "verifier_evidence", ()) or ())
            gate_results = []
            for item in verifier_rows:
                command = str(getattr(item, "command", "") or "")
                passed = (
                    str(getattr(item, "status", "") or "") == "COMPLETED"
                    and getattr(item, "exit_code", None) == 0
                )
                gate_results.append(
                    {
                        "cmd_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
                        "passed": bool(passed),
                    }
                )

            verifier_status = "PASS" if bool(verified.verified) else "FAIL"
            aggregate_matches = bool(gate_results) and (
                all(row["passed"] for row in gate_results) == bool(verified.verified)
            )
            label_quality = "MECHANICAL_GATE" if aggregate_matches else "TRACE_ONLY"
            candidate_id = f"{contract.task_id}#self-hosted-{attempt_id}"
            dispatch_envelope = state.get("canonical_dispatch_envelope")
            dispatch_envelope = (
                dispatch_envelope if isinstance(dispatch_envelope, Mapping) else {}
            )
            selected_model = str(
                state.get("selected_model") or dispatch_envelope.get("model") or ""
            )
            collection = collect_candidate_group(
                repo_root=repo_root,
                task_id=str(contract.task_id),
                attempt_id=attempt_id,
                collector_source="self_hosted_worker",
                source_revision=source_revision,
                contract_identity=contract.model_dump(mode="json"),
                verifier_identity={
                    "kind": "candidate_verifier",
                    "commands": list(getattr(contract, "verifier_commands", ()) or ()),
                },
                candidates=[
                    {
                        "candidate_id": candidate_id,
                        "candidate_model": selected_model,
                        "candidate_source": provider,
                        "candidate_payload": candidate_payload,
                        "candidate_state_hash": str(
                            getattr(candidate, "candidate_state_hash", "") or ""
                        ),
                        "verifier_status": verifier_status,
                        "label_quality": label_quality,
                        "verifier_evidence": {"gate_results": gate_results},
                        "failure_reason_codes": list(verified.failure_reasons or ()),
                        "selected": bool(verified.verified),
                    }
                ],
                winner_id=candidate_id if verified.verified else "",
            )
            result = {
                "status": collection.status,
                "eligible_count": collection.eligible_count,
                "trajectory_id": trajectory_id,
                "group_sha256": collection.group_sha256,
                "outcome_bound": False,
            }
            if collection.eligible_count == 1 and collection.row_refs:
                bind_trajectory_outcome(
                    evidence_root=evidence_root,
                    trajectory_id=trajectory_id,
                    candidate_evidence_ref=collection.row_refs[0],
                )
                refresh = refresh_registered_experiment(
                    repo_root=Path(_service_module().__file__).resolve().parents[2],  # pyright: ignore[reportArgumentType]
                    candidate_evidence_root=evidence_root,
                )
                result.update(
                    outcome_bound=True,
                    readiness=(refresh.get("readiness") or {}).get("disposition"),
                    checkpoint_status=(refresh.get("checkpoint") or {}).get("status"),
                    checkpoint_sha256=(refresh.get("checkpoint") or {}).get(
                        "checkpoint_sha256"
                    ),
                )
            else:
                result["reason"] = "strong_verifier_truth_unavailable"
            return result
        except Exception as exc:
            return {
                "status": "ERROR",
                "error_type": type(exc).__name__,
            }
    # fmt: on
