"""Work-claim cluster of ``SelfHostedTaskService``.

Big-file split S1 (Issue #2533). ``_ClaimsMixin`` holds the Issue #129 work-claim
subrecord of the task receipt, moved out of
``nexus/orchestrator/self_hosted_task_service.py``: the claim identity / hash / fence
validators, ``acquire_work_claim``, ``_bridge_validate_claim`` (the #2374 durable attempt
binding of the stale fence), ``validate`` / ``release`` / ``recover_work_claim``, the
read-only ``read_work_claim`` / ``list_active_work_claims`` projection and their aliases.
Their source lines are verbatim, except that every facade-module name they load that the
facade defines or that tests patch on the facade (``SelfHostedTaskService``,
``TERMINAL_STATUSES``, ``_jsonable``, ``_utc_now``, ``_bounded_failure_text``, ``uuid4``)
is resolved at call time through ``_service_module()``.

The state lock and state store (``_state_lock``, ``_state_path``, ``_read_state``,
``_write_state_locked``) live in ``_StateStoreMixin`` (``parts/state_store.py``, split S6b)
and are reached through ``self``.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from typing import TYPE_CHECKING, Any, Mapping, Optional

if TYPE_CHECKING:
    from contextlib import AbstractContextManager
    from pathlib import Path


def _service_module():
    # Late binding: the service imports this module at its top level, so its own
    # (and its patched) names are only resolved once a method runs.
    return importlib.import_module("nexus.orchestrator.self_hosted_task_service")


class _ClaimsMixin:
    """Mixin base of ``SelfHostedTaskService``; never instantiated on its own."""

    if TYPE_CHECKING:  # provided by SelfHostedTaskService
        state_dir: Path
        _bound_attempt_claims: dict[tuple[str, str], dict[str, Any]]

        def _state_path(self, task_id: str) -> Path: ...

        def _state_lock(self) -> AbstractContextManager[None]: ...

        def _write_state_locked(self, task_id: str, state: dict[str, Any]) -> dict[str, Any]: ...

        def _read_state(self, task_id: str) -> Optional[dict[str, Any]]: ...

    # fmt: off
    # Issue #129: the claim is deliberately a subrecord of the existing task
    # receipt.  The state lock above is the sole serialization point.
    PUBLIC_WORK_CLAIM_SCHEMA = "nexus.orchestrator.work_claim_view.v1"
    PUBLIC_WORK_CLAIM_CEILING = "PROJECTION_READ_ONLY_REPO_ENFORCED"

    @staticmethod
    def _claim_identity(request: Mapping[str, Any]) -> dict[str, Any]:
        admission = request.get("workforce_admission", request.get("admission_binding"))
        preflight = request.get("provider_preflight", request.get("realm_preflight"))
        allowed = request.get("allowed_files", request.get("mutation_domain", []))
        if isinstance(allowed, str):
            allowed = [allowed]
        identity = {
            "repository": str(request.get("repository") or request.get("repo") or "").strip(),
            "issue": str(request.get("issue") or request.get("issue_number") or "").strip(),
            "task_id": str(request.get("task_id") or "").strip(),
            "attempt_id": str(request.get("attempt_id") or "").strip(),
            "action_id": str(request.get("action_id") or "").strip(),
            "worker_id": str(request.get("worker_id") or request.get("worker") or "").strip(),
            "provider": str(request.get("provider") or "").strip(),
            "model": str(request.get("model") or "").strip(),
            "role": str(request.get("role") or request.get("worker_role") or "").strip(),
            "claim_ceiling": str(request.get("claim_ceiling") or "").strip(),
            "base_revision": str(request.get("base_revision") or request.get("target_base_revision") or "").strip(),
            "source_hash": str(request.get("source_hash") or request.get("source_revision") or "").strip(),
            "task_card_path": str(request.get("task_card_path") or "").strip(),
            "allowed_files": sorted({str(item).strip() for item in allowed if str(item).strip()}),
            "admission_identity": (
                str(request.get("admission_identity") or "").strip()
                if "workforce_admission" not in request and "admission_binding" not in request and "admission_identity" in request
                else hashlib.sha256(json.dumps(_service_module()._jsonable(admission), sort_keys=True, separators=(",", ":")).encode()).hexdigest() if admission is not None else ""
            ),
            "provider_preflight_identity": (
                str(request.get("provider_preflight_identity") or "").strip()
                if "provider_preflight" not in request and "realm_preflight" not in request and "provider_preflight_identity" in request
                else hashlib.sha256(json.dumps(_service_module()._jsonable(preflight), sort_keys=True, separators=(",", ":")).encode()).hexdigest() if preflight is not None else ""
            ),
        }
        return identity

    @classmethod
    def _claim_hash(cls, identity: Mapping[str, Any]) -> str:
        return hashlib.sha256(json.dumps(_service_module()._jsonable(identity), sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _claim_request(request: Mapping[str, Any]) -> dict[str, Any]:
        identity = _service_module().SelfHostedTaskService._claim_identity(request)
        return {"identity": identity, "identity_hash": _service_module().SelfHostedTaskService._claim_hash(identity),
                "claim_id": str(request.get("claim_id") or _service_module().uuid4()),
                "generation": int(request.get("generation") or 1),
                "fencing_token": str(request.get("fencing_token") or "")}

    @classmethod
    def _validate_claim_record(cls, record: Mapping[str, Any]) -> None:
        if not isinstance(record, Mapping) or not isinstance(record.get("identity"), Mapping) or not record.get("identity"):
            raise RuntimeError("WORK_CLAIM_MALFORMED")
        if not isinstance(record.get("identity_hash"), str) or record.get("identity_hash") != cls._claim_hash(record["identity"]):
            raise RuntimeError("WORK_CLAIM_TAMPERED")
        if not isinstance(record.get("generation"), int) or isinstance(record.get("generation"), bool) or record["generation"] < 1 or not isinstance(record.get("claim_id"), str) or not record["claim_id"]:
            raise RuntimeError("WORK_CLAIM_MALFORMED")
        if record.get("status") != "CLAIMED":
            raise RuntimeError("WORK_CLAIM_MALFORMED")
        expected_fencing_token = f"{record['claim_id']}:{record['generation']}"
        if (
            not isinstance(record.get("fencing_token"), str)
            or record["fencing_token"] != expected_fencing_token
        ):
            raise RuntimeError("WORK_CLAIM_STALE_FENCE")

    @classmethod
    def _validate_claim_enclosure(
        cls,
        state: Mapping[str, Any],
        record: Mapping[str, Any],
        *,
        expected_task_id: str = "",
    ) -> None:
        identity = record.get("identity") or {}
        state_task_id = str(state.get("task_id") or "").strip()
        claim_task_id = str(identity.get("task_id") or "").strip()
        if not state_task_id or claim_task_id != state_task_id:
            raise RuntimeError("WORK_CLAIM_TAMPERED")
        if expected_task_id and state_task_id != expected_task_id:
            raise RuntimeError("WORK_CLAIM_TAMPERED")
        state_attempt_id = str(state.get("attempt_id") or "").strip()
        claim_attempt_id = str(identity.get("attempt_id") or "").strip()
        if state_attempt_id and claim_attempt_id != state_attempt_id:
            raise RuntimeError("WORK_CLAIM_TAMPERED")

    @staticmethod
    def _attempt_binding(record: Mapping[str, Any], task_id: str, attempt_id: str) -> dict[str, Any]:
        return {
            **(record.get("identity") or {}),
            "task_id": task_id,
            "attempt_id": attempt_id,
            "claim_id": record["claim_id"],
            "generation": record["generation"],
            "fencing_token": record["fencing_token"],
        }

    @staticmethod
    def _bindings_of(state: Mapping[str, Any]) -> dict[str, Any]:
        raw = state.get("attempt_claim_bindings")
        if raw is None:
            return {}
        if not isinstance(raw, Mapping):
            raise RuntimeError("WORK_CLAIM_BINDINGS_CORRUPT")
        return dict(raw)

    @classmethod
    def _validate_claim_locked(cls, state: Mapping[str, Any], request: Mapping[str, Any]) -> Mapping[str, Any]:
        record = state.get("work_claim")
        cls._validate_claim_record(record)  # pyright: ignore[reportArgumentType]
        cls._validate_claim_enclosure(
            state,
            record,  # pyright: ignore[reportArgumentType]
            expected_task_id=str(request.get("task_id") or "").strip(),
        )
        expected = cls._claim_identity(request)
        if record["identity_hash"] != cls._claim_hash(expected):  # pyright: ignore[reportOptionalSubscript]
            raise RuntimeError("WORK_CLAIM_FENCE_MISMATCH")
        expected_fencing_token = f"{record['claim_id']}:{record['generation']}"  # pyright: ignore[reportOptionalSubscript]
        if (
            not isinstance(record.get("fencing_token"), str)  # pyright: ignore[reportOptionalMemberAccess]
            or record["fencing_token"] != expected_fencing_token  # pyright: ignore[reportOptionalSubscript]
            or not isinstance(request.get("claim_id"), str)
            or request["claim_id"] != record["claim_id"]  # pyright: ignore[reportOptionalSubscript]
            or not isinstance(request.get("generation"), int)
            or isinstance(request.get("generation"), bool)
            or request["generation"] != record["generation"]  # pyright: ignore[reportOptionalSubscript]
            or not isinstance(request.get("fencing_token"), str)
            or request["fencing_token"] != expected_fencing_token
        ):
            raise RuntimeError("WORK_CLAIM_STALE_FENCE")
        return record  # pyright: ignore[reportReturnType]

    def acquire_work_claim(
        self, request: Mapping[str, Any], *, enforce_issue_uniqueness: bool = False
    ) -> dict[str, Any]:
        candidate = self._claim_request(request)
        task_id = candidate["identity"]["task_id"]
        if not task_id:
            return {"status": "BLOCKED", "reason": "TASK_ID_REQUIRED"}
        with self._state_lock():
            path = self._state_path(task_id)
            if not path.exists():
                return {"status": "BLOCKED", "reason": "TASK_NOT_FOUND"}
            state = json.loads(path.read_text(encoding="utf-8"))
            existing = state.get("work_claim")
            if existing is not None:
                self._validate_claim_record(existing)
                if existing["identity_hash"] == candidate["identity_hash"]:
                    return {"status": "ALREADY_CLAIMED", "claim": existing}
                return {"status": "BLOCKED", "reason": "ALREADY_CLAIMED", "claim": existing}

            # Check cross-task claim collision for the same repository and issue when requested
            should_check_issue = enforce_issue_uniqueness or bool(
                request.get("enforce_issue_uniqueness")
            )
            repo = candidate["identity"].get("repository")
            issue = candidate["identity"].get("issue")
            if should_check_issue and repo and issue and self.state_dir.exists():
                for other_path in sorted(self.state_dir.glob("*.json")):
                    if other_path.name.startswith(".") or other_path.name == f"{task_id}.json":
                        continue
                    try:
                        other_state = json.loads(other_path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError) as exc:
                        raise RuntimeError("WORK_CLAIM_INVENTORY_UNKNOWN") from exc
                    if not isinstance(other_state, Mapping):
                        raise RuntimeError("WORK_CLAIM_INVENTORY_UNKNOWN")
                    other_claim = other_state.get("work_claim")
                    if other_claim is None:
                        continue
                    if not isinstance(other_claim, Mapping):
                        raise RuntimeError("WORK_CLAIM_INVENTORY_UNKNOWN")
                    try:
                        self._validate_claim_record(other_claim)
                        self._validate_claim_enclosure(
                            other_state,
                            other_claim,
                            expected_task_id=str(other_state.get("task_id") or "").strip(),
                        )
                    except (KeyError, TypeError, ValueError, RuntimeError) as exc:
                        raise RuntimeError("WORK_CLAIM_INVENTORY_UNKNOWN") from exc
                    other_ident = other_claim.get("identity") or {}
                    if (
                        str(other_ident.get("repository") or "").strip() == repo
                        and str(other_ident.get("issue") or "").strip() == issue
                    ):
                        if (
                            other_state.get("status") not in _service_module().TERMINAL_STATUSES
                            and other_state.get("status") != "CANCELLED"
                        ):
                            return {
                                "status": "BLOCKED",
                                "reason": "ALREADY_CLAIMED",
                                "claim": other_claim,
                            }

            candidate["generation"] = 1
            candidate["fencing_token"] = f"{candidate['claim_id']}:{candidate['generation']}"
            candidate["status"] = "CLAIMED"
            candidate["claimed_at"] = _service_module()._utc_now()
            state["work_claim"] = candidate
            acquired_attempt = str(candidate["identity"].get("attempt_id") or "").strip()
            if acquired_attempt:
                bindings = self._bindings_of(state)
                bindings[acquired_attempt] = self._attempt_binding(
                    candidate, task_id, acquired_attempt
                )
                state["attempt_claim_bindings"] = bindings
            self._write_state_locked(task_id, state)
            return {"status": "CLAIMED", "claim": candidate}

    claim_work = acquire_work_claim

    def _bridge_validate_claim(
        self,
        task_id: str,
        attempt_id: str | None = None,
        *,
        operation: str = "MUTATION",
    ) -> Optional[dict[str, Any]]:
        state = self._read_state(task_id)
        if state is None:
            return None
        claim_record = state.get("work_claim")
        req = state.get("request") if isinstance(state.get("request"), Mapping) else {}
        contract_data = state.get("contract") if isinstance(state.get("contract"), Mapping) else {}
        is_issue_task = bool(
            req.get("claim_required")  # pyright: ignore[reportOptionalMemberAccess]
            or req.get("issue")  # pyright: ignore[reportOptionalMemberAccess]
            or req.get("issue_number")  # pyright: ignore[reportOptionalMemberAccess]
            or req.get("project_entry_authority_binding")  # pyright: ignore[reportOptionalMemberAccess]
            or contract_data.get("issue_number")  # pyright: ignore[reportOptionalMemberAccess]
            or claim_record is not None
        )
        if not is_issue_task:
            return None
        if claim_record is None:
            raise RuntimeError(f"WORK_CLAIM_REQUIRED:{operation}")

        with self._state_lock():
            path = self._state_path(task_id)
            if not path.exists():
                raise RuntimeError("WORK_CLAIM_NOT_FOUND")
            locked_state = json.loads(path.read_text(encoding="utf-8"))
            record = locked_state.get("work_claim")
            if record is None:
                raise RuntimeError(f"WORK_CLAIM_REQUIRED:{operation}")

            self._validate_claim_record(record)
            self._validate_claim_enclosure(
                locked_state,
                record,
                expected_task_id=task_id,
            )

            # Check for base revision drift
            locked_contract = locked_state.get("contract") or {}
            current_base = str(locked_contract.get("target_base_revision") or "").strip()
            claim_base = str((record.get("identity") or {}).get("base_revision") or "").strip()
            if current_base and claim_base and current_base != claim_base:
                raise RuntimeError("WORK_CLAIM_BASE_REVISION_DRIFT")

            current_source = str(locked_contract.get("controller_revision") or "").strip()
            claim_source = str((record.get("identity") or {}).get("source_hash") or "").strip()
            if current_source and claim_source and current_source != claim_source:
                raise RuntimeError("WORK_CLAIM_SOURCE_REVISION_DRIFT")

            effective_attempt_id = attempt_id or str(locked_state.get("attempt_id") or "")
            bound_key = (task_id, effective_attempt_id) if effective_attempt_id else None
            # The durable binding persisted with the attempt state is the source
            # of truth (#2374); the in-process dict is only a cache of it.
            persisted_all = self._bindings_of(locked_state)
            persisted = persisted_all.get(effective_attempt_id) if bound_key else None
            if persisted is not None and not isinstance(persisted, Mapping):
                raise RuntimeError("WORK_CLAIM_STALE_FENCE")
            cached = self._bound_attempt_claims.get(bound_key) if bound_key else None
            bound = persisted if persisted is not None else cached
            if bound is None and bound_key:
                # Legacy attempt (no persisted binding at all): adopt the current
                # generation, unchanged from before #2374.
                bound = self._attempt_binding(record, task_id, effective_attempt_id)
            if bound is not None:
                # Fail closed: the durable binding and any in-process cache must
                # both still match the on-disk claim.
                self._validate_claim_locked(locked_state, bound)
                if cached is not None and cached is not bound:
                    self._validate_claim_locked(locked_state, cached)
                if bound_key is not None:
                    self._bound_attempt_claims[bound_key] = dict(bound)
                if persisted is None:
                    persisted_all[effective_attempt_id] = dict(bound)
                    locked_state["attempt_claim_bindings"] = persisted_all
                    self._write_state_locked(task_id, locked_state)

            return record

    def validate_work_claim(self, request: Mapping[str, Any]) -> dict[str, Any]:
        task_id = str(request.get("task_id") or "")
        with self._state_lock():
            path = self._state_path(task_id)
            if not path.exists():
                raise RuntimeError("WORK_CLAIM_NOT_FOUND")
            state = json.loads(path.read_text(encoding="utf-8"))
            record = self._validate_claim_locked(state, request)
            return {"status": "CLAIMED", "claim": record}

    def release_work_claim(self, request: Mapping[str, Any]) -> dict[str, Any]:
        task_id = str(request["task_id"])
        with self._state_lock():
            state = json.loads(self._state_path(task_id).read_text(encoding="utf-8"))
            self._validate_claim_locked(state, request)
            state.pop("work_claim", None)
            self._write_state_locked(task_id, state)
        return {"status": "RELEASED", "task_id": task_id}

    def recover_work_claim(
        self,
        request: Mapping[str, Any],
        *,
        reason: str = "RECOVERY",
        authorized_attempt_id: str | None = None,
    ) -> dict[str, Any]:
        task_id = str(request["task_id"])
        with self._state_lock():
            state = json.loads(self._state_path(task_id).read_text(encoding="utf-8"))
            record = self._validate_claim_locked(state, request)
            generation = int(record["generation"]) + 1
            record["generation"] = generation  # pyright: ignore[reportIndexIssue]
            record["fencing_token"] = f"{record['claim_id']}:{generation}"  # pyright: ignore[reportIndexIssue]
            record["recovery_reason"] = _service_module()._bounded_failure_text(reason)  # pyright: ignore[reportIndexIssue]
            record["recovered_at"] = _service_module()._utc_now()  # pyright: ignore[reportIndexIssue]
            # Only the attempt the recovery explicitly authorizes is re-bound to
            # the new generation; every other bound attempt stays fenced (#2374).
            authorized = str(authorized_attempt_id or "").strip()
            bindings = self._bindings_of(state)  # fail closed on corrupt bindings
            if authorized:
                new_ident = dict(record.get("identity") or {})
                if str(new_ident.get("attempt_id") or "") != authorized:
                    # Recovery hands the claim to a new attempt: re-identify it so
                    # the old attempt's binding no longer matches the claim.
                    new_ident["attempt_id"] = authorized
                    stored_claim: dict[str, Any] = state["work_claim"]
                    stored_claim["identity"] = new_ident
                    stored_claim["identity_hash"] = self._claim_hash(new_ident)
                    state["attempt_id"] = authorized
                rebound = self._attempt_binding(record, task_id, authorized)
                bindings[authorized] = rebound
                state["attempt_claim_bindings"] = bindings
                self._bound_attempt_claims[(task_id, authorized)] = dict(rebound)
            self._write_state_locked(task_id, state)
            return {"status": "CLAIMED", "claim": record}

    renew_work_claim = validate_work_claim

    def _project_public_claim(
        self, claim_record: Mapping[str, Any], *, state: Mapping[str, Any]
    ) -> dict[str, Any]:
        identity = dict(claim_record.get("identity") or {})
        holder = (
            str(identity.get("worker_id") or "")
            or str(identity.get("role") or "")
            or str(identity.get("provider") or "")
        )
        gen = int(claim_record.get("generation") or 1)
        identity_hash = str(claim_record.get("identity_hash") or "")
        claim_projection_hash = hashlib.sha256(
            f"claim-view:{identity_hash}".encode("utf-8")
        ).hexdigest()
        fence_projection_hash = hashlib.sha256(
            f"claim-fence-view:{identity_hash}:{gen}".encode("utf-8")
        ).hexdigest()
        claim_identity = f"urn:nexus:claim:{claim_projection_hash}"
        fence_hash = fence_projection_hash
        fence_identity = f"urn:nexus:claim_fence:{fence_projection_hash}"
        return {
            "schema": self.PUBLIC_WORK_CLAIM_SCHEMA,
            "claim_ceiling": self.PUBLIC_WORK_CLAIM_CEILING,
            "claim_enforcement_state": "REPO_ENFORCED",
            "claim_identity": claim_identity,
            "generation": gen,
            "fence_identity": fence_identity,
            "fence_hash": fence_hash,
            "state": str(claim_record["status"]),
            "holder": holder,
            "repository": str(identity.get("repository") or ""),
            "issue": str(identity.get("issue") or ""),
            "task_id": str(identity.get("task_id") or ""),
            "attempt_id": str(identity.get("attempt_id") or ""),
            "action_id": str(identity.get("action_id") or ""),
            "worker_id": str(identity.get("worker_id") or ""),
            "provider": str(identity.get("provider") or ""),
            "model": str(identity.get("model") or ""),
            "role": str(identity.get("role") or ""),
            "allowed_files": list(identity.get("allowed_files") or []),
            "mutation_domain": list(identity.get("allowed_files") or []),
            "base_revision": str(identity.get("base_revision") or ""),
            "source_hash": str(identity.get("source_hash") or ""),
            "task_card_path": str(identity.get("task_card_path") or ""),
            "admission_identity": str(identity.get("admission_identity") or ""),
            "provider_preflight_identity": str(identity.get("provider_preflight_identity") or ""),
            "identity_hash": str(claim_record.get("identity_hash") or ""),
            "claimed_at": str(claim_record.get("claimed_at") or ""),
            "recovered_at": str(claim_record.get("recovered_at") or ""),
            "recovery_reason": str(claim_record.get("recovery_reason") or ""),
            "observed_at": _service_module()._utc_now(),
            "canonical_revision": int(state.get("revision") or state.get("task_revision") or 1),
        }

    def read_work_claim(self, request: Mapping[str, Any]) -> dict[str, Any]:
        task_id = str(request.get("task_id") or "").strip()
        if not task_id:
            return {"status": "BLOCKED", "reason": "TASK_ID_REQUIRED", "found": False}
        path = self._state_path(task_id)
        if not path.exists():
            return {
                "status": "NOT_FOUND",
                "reason": "TASK_NOT_FOUND",
                "found": False,
                "task_id": task_id,
            }
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {
                "status": "BLOCKED",
                "reason": "WORK_CLAIM_STATE_UNREADABLE",
                "found": False,
                "task_id": task_id,
            }
        claim_record = state.get("work_claim")
        if claim_record is None:
            return {
                "status": "NO_ACTIVE_CLAIM",
                "found": False,
                "task_id": task_id,
            }
        try:
            self._validate_claim_record(claim_record)
            self._validate_claim_enclosure(
                state,
                claim_record,
                expected_task_id=task_id,
            )
        except RuntimeError as exc:
            return {
                "status": "BLOCKED",
                "reason": str(exc),
                "found": False,
                "task_id": task_id,
            }

        expected_generation = request.get("generation")
        generation_status = "CURRENT"
        if expected_generation is not None:
            if not isinstance(expected_generation, int) or isinstance(expected_generation, bool):
                return {"status": "BLOCKED", "reason": "INVALID_GENERATION", "found": False}
            current_gen = int(claim_record.get("generation") or 1)
            if expected_generation < current_gen:
                generation_status = "STALE_GENERATION"
            elif expected_generation > current_gen:
                generation_status = "FUTURE_GENERATION"

        projected = self._project_public_claim(claim_record, state=state)
        projected["generation_status"] = generation_status
        return {
            "status": "FOUND",
            "found": True,
            "task_id": task_id,
            "claim": projected,
        }

    read_claim = read_work_claim

    def list_active_work_claims(
        self, filter_spec: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        results = []
        spec = dict(filter_spec or {})
        repo_filter = str(spec.get("repository") or spec.get("repo") or "").strip()
        issue_filter = str(spec.get("issue") or spec.get("issue_number") or "").strip()
        worker_filter = str(spec.get("worker_id") or spec.get("worker") or "").strip()
        status_filter = str(spec.get("status") or "").strip()

        candidates = sorted(self.state_dir.glob("*.json")) if self.state_dir.exists() else []
        for path in candidates:
            if path.name.startswith("."):
                continue
            try:
                state = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(
                    "WORK_CLAIM_LIST_BLOCKED:WORK_CLAIM_STATE_UNREADABLE"
                ) from exc
            claim_record = state.get("work_claim")
            if claim_record is None:
                continue
            if not isinstance(claim_record, Mapping):
                raise RuntimeError("WORK_CLAIM_LIST_BLOCKED:WORK_CLAIM_MALFORMED")
            try:
                self._validate_claim_record(claim_record)
                self._validate_claim_enclosure(state, claim_record)
            except RuntimeError as exc:
                raise RuntimeError(f"WORK_CLAIM_LIST_BLOCKED:{exc}") from exc

            identity = claim_record.get("identity") or {}
            if repo_filter and identity.get("repository") != repo_filter:
                continue
            if issue_filter and identity.get("issue") != issue_filter:
                continue
            if worker_filter and identity.get("worker_id") != worker_filter:
                continue
            if status_filter and claim_record.get("status") != status_filter:
                continue

            results.append(self._project_public_claim(claim_record, state=state))

        return sorted(results, key=lambda c: (str(c.get("task_id")), str(c.get("claimed_at"))))

    list_active_claims = list_active_work_claims
    # fmt: on
