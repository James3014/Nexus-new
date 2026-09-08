"""One-root, same-owner writer transition orchestration over P6C primitives."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Mapping

from nexus.contracts.state_owner_transition import (
    Operation,
    ReceiptState,
    TransitionReceipt,
    TransitionValidationError,
    WriterTransitionRequest,
)
from nexus.events.state_owner_manifest import (
    COMMITTED_STATUS,
    StateOwnerBinding,
    StateOwnerSelection,
    classify,
    commit_owner_transaction,
    owner_transaction_guard,
    read_manifest,
)
from nexus.events.writer_generation import (
    EventWriterGeneration,
    event_store_lock,
    install_generation,
    read_generation,
)
from nexus.orchestrator.state_owner_transition_authority import (
    LoadedSourceIdentity,
    VerifiedWriterTransitionAuthority,
    WriterAuthorityError,
    is_authorized_for_request,
    is_registered_authority,
    load_verified_writer_transition_authority,
)


class TransitionServiceError(RuntimeError):
    pass


class MissingDependency(TransitionServiceError):
    pass


@dataclass(frozen=True, slots=True)
class LoadedRootTransition:
    """Typed one-root A boundary consumed by the F cohort coordinator.

    The request and service are captured from the already-loaded source
    service.  No method accepts a root selector or constructs a replacement
    service, which keeps the cohort barrier separate from A's per-root CAS.
    """

    service: "StateOwnerTransitionService"
    request: WriterTransitionRequest

    def __post_init__(self) -> None:
        if not isinstance(self.service, StateOwnerTransitionService):
            raise TypeError("loaded state owner transition service required")
        if (
            not isinstance(self.request, WriterTransitionRequest)
            or self.request.operation is not Operation.APPLY
        ):
            raise TypeError("typed APPLY request required")

    @property
    def root_id(self) -> str:
        return self.request.root_id

    def preflight(self) -> TransitionReceipt:
        return self.service.preflight(self.request)

    def apply(self) -> TransitionReceipt:
        return self.service.apply(self.request)

    def has_intent(self) -> bool:
        root = self.service._roots.get(self.request.root_id)
        if not isinstance(root, Path):
            raise MissingDependency("MISSING_LOADED_ROOT")
        prior = _read_intent(root)
        if prior is None:
            return False
        if (
            prior.get("request_digest") != self.request.request_digest
            or prior.get("idempotency_key") != self.request.idempotency_key
        ):
            raise TransitionServiceError("CONFLICTING_REPLAY")
        return True

    def reconcile(self) -> TransitionReceipt:
        return self.service.reconcile(replace(self.request, operation=Operation.RECONCILE))


class _VerifiedCollectorEvidence:
    """Private source-owned collector seam; production has no request selector."""

    __slots__ = ("payload",)

    def __init__(self, payload: Mapping[str, Any]):
        if not isinstance(payload, Mapping):
            raise TransitionServiceError("COLLECTOR_RECEIPT_INVALID")
        self.payload = dict(payload)


# Production is deliberately unconfigured until the source-owned collector
# adapter is supplied. Tests may monkeypatch this private seam with a typed
# in-memory adapter; there is no CLI or product selector for it.
_COLLECTOR_LOADER = None


def _root_hash(root: Path) -> str:
    return hashlib.sha256(str(root.resolve()).encode()).hexdigest()


def _file_hash(path: Path) -> tuple[int, str]:
    try:
        info = path.lstat()
    except OSError as exc:
        raise TransitionServiceError("SELECTED_FILE_MISSING") from exc
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise TransitionServiceError("SELECTED_FILE_UNSAFE")
    data = path.read_bytes()
    return len(data), hashlib.sha256(data).hexdigest()


def _intent_path(root: Path) -> Path:
    return root / ".nexus" / "events" / "writer_transition.intent.json"


def _read_intent(root: Path) -> Mapping[str, Any] | None:
    path = _intent_path(root)
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise TransitionServiceError("INTENT_RECORD_UNSAFE")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            opened = os.fstat(handle.fileno())
            if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                raise TransitionServiceError("INTENT_RECORD_CHANGED")
            data = json.load(handle)
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise TransitionServiceError("INTENT_RECORD_UNREADABLE") from exc
    if not isinstance(data, Mapping):
        raise TransitionServiceError("INTENT_RECORD_UNREADABLE")
    try:
        request = WriterTransitionRequest.from_mapping(data["request"])
        expected = _intent_payload(
            request,
            state=data["state"],
            receipt=data["outcome"],
            before_observation=data["before_observation"],
            phase=data["phase"],
        )
        if data != expected or data["state"] not in {"INTENT_RECORDED", "COMMITTED"}:
            raise ValueError
    except (KeyError, TypeError, ValueError, TransitionValidationError) as exc:
        raise TransitionServiceError("INTENT_RECORD_MALFORMED") from exc
    return data


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(dict(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def _intent_payload(
    req: WriterTransitionRequest,
    *,
    state: str,
    receipt: Mapping[str, Any] | None = None,
    before_observation: Mapping[str, Any] | None = None,
    phase: str | None = None,
) -> dict[str, Any]:
    return {
        "schema": "nexus.writer_transition_intent.v3",
        "request": req.to_dict(),
        "request_digest": req.request_digest,
        "authorization_intent_digest": req.authorization_intent_digest,
        "transaction_id": req.transaction_id,
        "idempotency_key": req.idempotency_key,
        "authority_receipt_id": req.authority_receipt_id,
        "authority_receipt_hash": req.authority_receipt_hash,
        "state": state,
        "phase": phase or state,
        "before_observation": dict(before_observation) if before_observation is not None else None,
        "outcome": dict(receipt or {}),
    }


def _record_intent(
    root: Path,
    req: WriterTransitionRequest,
    *,
    state: str = "INTENT_RECORDED",
    receipt: Mapping[str, Any] | None = None,
    before_observation: Mapping[str, Any] | None = None,
    phase: str | None = None,
) -> None:
    path = _intent_path(root)
    prior = _read_intent(root)
    payload = _intent_payload(
        req,
        state=state,
        receipt=receipt,
        before_observation=before_observation
        if before_observation is not None
        else (prior.get("before_observation") if prior else None),
        phase=phase,
    )
    if prior is not None:
        if (
            prior.get("request_digest") != req.request_digest
            or prior.get("idempotency_key") != req.idempotency_key
        ):
            raise TransitionServiceError("CONFLICTING_REPLAY")
        if prior.get("state") == "COMMITTED" and state != "COMMITTED":
            return
    _atomic_json(path, payload)


def _validate_card_scope(card_bytes: bytes, req: WriterTransitionRequest, repository: str) -> None:
    """Physical card constraint; this never replaces publication or grant authority."""
    import re

    try:
        text = card_bytes.decode("utf-8")
        blocks = re.findall(r"(?m)^```writer-transition-scope\n(.*?)^```[ \t]*$", text, re.DOTALL)
        if len(blocks) != 1 or text.count("```writer-transition-scope") != 1:
            raise ValueError

        def closed_pairs(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError
                value[key] = item
            return value

        scope = json.loads(blocks[0], object_pairs_hook=closed_pairs)
        if not isinstance(scope, dict) or set(scope) != {
            "schema",
            "mode",
            "task_id",
            "repository",
            "root_ids",
            "operations",
        }:
            raise ValueError
        roots = scope["root_ids"]
        if (
            scope["schema"] != "nexus.writer_transition_card_scope.v1"
            or scope["mode"] != "LIVE_SAME_OWNER"
            or scope["task_id"] != req.task_id
            or scope["repository"] != repository
        ):
            raise ValueError
        if (
            not isinstance(roots, list)
            or not roots
            or any(not isinstance(root, str) or not root or root != root.strip() for root in roots)
            or len(set(roots)) != len(roots)
            or req.root_id not in roots
        ):
            raise ValueError
        if scope["operations"] != ["APPLY", "RECONCILE"]:
            raise ValueError
        if req.operation not in (Operation.PREFLIGHT, Operation.APPLY, Operation.RECONCILE):
            raise ValueError
    except (UnicodeDecodeError, ValueError, TypeError) as exc:
        raise TransitionServiceError("LIVE_CARD_SCOPE_INVALID") from exc


class StateOwnerTransitionService:
    def __init__(
        self,
        *,
        roots: Mapping[str, Path],
        source: LoadedSourceIdentity,
        source_root: Path | None = None,
        service: Any = None,
    ):
        self._roots = {
            key: value.resolve() if isinstance(value, Path) else value
            for key, value in roots.items()
        }
        self._source = source
        self._source_root = source_root.resolve() if isinstance(source_root, Path) else None
        self._grant_result: Mapping[str, Any] = {}
        self._service = service
        self._authority_handle = None

    def loaded_root_transition(self, request: WriterTransitionRequest) -> LoadedRootTransition:
        """Bind one exact loaded A request for a multi-root coordinator.

        This is a typed adapter boundary only.  The cohort owner determines
        ordering and ACTIVE/release; A continues to own one-root physical
        intent, generation CAS, and manifest readback.
        """
        if not isinstance(request, WriterTransitionRequest):
            raise TransitionValidationError("LOADED_REQUEST_REQUIRED")
        if request.root_id not in self._roots:
            raise TransitionServiceError("ROOT_UNKNOWN")
        return LoadedRootTransition(self, request)

    def _receipt(
        self,
        req: WriterTransitionRequest,
        state: ReceiptState,
        *,
        writes=False,
        replayed=False,
        reconcile=False,
        error="",
        observed_before="",
        observed_after="",
    ) -> TransitionReceipt:
        if state not in (ReceiptState.COMMITTED, ReceiptState.RECONCILED):
            return TransitionReceipt(
                req.request_digest,
                req.transaction_id,
                state,
                writes,
                False,
                replayed,
                reconcile,
                error,
            )
        grant = self._grant_result
        selection_digest = hashlib.sha256(
            json.dumps(
                [x.to_dict() for x in req.selections], sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        return TransitionReceipt(
            req.request_digest,
            req.transaction_id,
            state,
            writes,
            False,
            replayed,
            reconcile,
            error,
            task_id=req.task_id,
            card_path=req.card_path,
            card_sha256=req.card_sha256,
            source_head=req.expected_source_head,
            source_tree=req.expected_source_tree,
            accepted_source_receipt=req.accepted_source_receipt,
            accepted_source_receipt_hash=getattr(req, "accepted_source_receipt_hash", ""),
            authority_receipt_id=req.authority_receipt_id,
            authority_receipt_hash=req.authority_receipt_hash,
            authorization_intent_digest=req.authorization_intent_digest,
            grant_id=str(grant.get("grant_id", "")),
            grant_hash=str(grant.get("grant_receipt_hash", "")),
            effect_hash=str(grant.get("effect_hash", "")),
            root_id=req.root_id,
            expected_root_identity=req.expected_root_identity,
            expected_owner_id=req.expected_owner_id,
            expected_generation=req.expected_generation,
            expected_writer_id=req.expected_writer_id,
            next_generation=req.next_generation,
            next_writer_id=req.next_writer_id,
            selection_digest=selection_digest,
            expected_manifest_sha256=req.expected_manifest_sha256,
            observed_before_manifest_sha256=observed_before or None,
            observed_after_manifest_sha256=observed_after,
            before_manifest_present=bool(observed_before),
            drain_receipt_id=req.drain_receipt_id,
            drain_receipt_hash=req.drain_receipt_hash,
            snapshot_receipt_id=req.snapshot_receipt_id,
            snapshot_receipt_hash=req.snapshot_receipt_hash,
            rollback_receipt_id=req.rollback_receipt_id,
            rollback_receipt_hash=req.rollback_receipt_hash,
            loaded_writer_plan_id=req.loaded_writer_plan_id,
            loaded_writer_plan_hash=req.loaded_writer_plan_hash,
        )

    def _request(self, raw: WriterTransitionRequest | Mapping[str, Any]) -> WriterTransitionRequest:
        return (
            raw
            if isinstance(raw, WriterTransitionRequest)
            else WriterTransitionRequest.from_mapping(raw)
        )

    def _validate_common(self, req: WriterTransitionRequest, *, allow_replay: bool = False) -> Path:
        root = self._roots.get(req.root_id)
        if (
            root is None
            or not isinstance(root, Path)
            or not root.is_absolute()
            or not root.is_dir()
        ):
            raise TransitionServiceError("ROOT_UNKNOWN")
        if _root_hash(root) != req.expected_root_identity:
            raise TransitionServiceError("ROOT_IDENTITY_MISMATCH")
        if (
            req.expected_source_head != self._source.source_head
            or req.expected_source_tree != self._source.source_tree
            or req.card_path != self._source.card_path
            or req.card_sha256 != self._source.card_sha256
        ):
            raise TransitionServiceError("SOURCE_OR_CARD_MISMATCH")
        if not req.accepted_source_receipt_hash:
            raise TransitionServiceError("SOURCE_ACCEPTANCE_HASH_REQUIRED")
        if self._source_root is None:
            raise TransitionServiceError("LOADED_SOURCE_ROOT_REQUIRED")
        source_root = self._source_root
        head, tree = _git_identity(source_root)

        def git(*args):
            return subprocess.check_output(
                ["git", "-C", str(source_root), *args], text=True, stderr=subprocess.DEVNULL
            ).strip()

        if git("status", "--porcelain", "--untracked-files=all"):
            raise TransitionServiceError("LOADED_SOURCE_DIRTY")
        if git("rev-parse", req.expected_source_head + "^{tree}") != req.expected_source_tree:
            raise TransitionServiceError("LOADED_SOURCE_TREE_MISMATCH")
        if head != req.expected_source_head:
            try:
                subprocess.check_call(
                    [
                        "git",
                        "-C",
                        str(source_root),
                        "merge-base",
                        "--is-ancestor",
                        req.expected_source_head,
                        head,
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except subprocess.CalledProcessError as exc:
                raise TransitionServiceError("LOADED_SOURCE_LINEAGE_MISMATCH") from exc
            changed = set(git("diff", "--name-only", req.expected_source_head, head).splitlines())
            permitted = {req.card_path, str(Path(req.card_path).parent / "INDEX.md")}
            if not changed or not changed.issubset(permitted):
                raise TransitionServiceError("LOADED_SOURCE_NOT_CARD_ONLY")
        elif tree != req.expected_source_tree:
            raise TransitionServiceError("LOADED_SOURCE_TREE_MISMATCH")
        card = source_root / req.card_path
        size, digest = _file_hash(card)
        if digest != req.card_sha256:
            raise TransitionServiceError("CARD_BYTES_MISMATCH")
        card_bytes = card.read_bytes()
        if hashlib.sha256(card_bytes).hexdigest() != req.card_sha256:
            raise TransitionServiceError("CARD_BYTES_MISMATCH")
        _validate_card_scope(card_bytes, req, self._source.repository)
        if req.next_generation <= (req.expected_generation or 0):
            raise TransitionServiceError("GENERATION_NOT_MONOTONIC")
        for item in req.selections:
            if item.role not in {"task_state", "runtime_receipt", "event_log", "effect_journal"}:
                raise TransitionServiceError("ROLE_INVALID")
            selected = root / item.relative_path
            if selected.resolve() != selected or not selected.resolve().is_relative_to(root):
                raise TransitionServiceError("SELECTED_FILE_UNSAFE")
            size, digest = _file_hash(selected)
            if size != item.size or digest != item.expected_sha256:
                raise TransitionServiceError("SELECTION_HASH_MISMATCH")
        manifest = read_manifest(root)
        if req.expected_generation is None:
            if manifest is not None and not allow_replay:
                raise TransitionServiceError("EXPECTED_INITIAL_MANIFEST_MISMATCH")
        elif manifest is None:
            if not allow_replay:
                raise TransitionServiceError("EXPECTED_MANIFEST_MISSING")
        elif not allow_replay:
            if (
                manifest.owner_id != req.expected_owner_id
                or manifest.writer_id != req.expected_writer_id
                or manifest.generation != req.expected_generation
            ):
                raise TransitionServiceError("OWNER_OR_GENERATION_MISMATCH")
            if (
                req.expected_manifest_sha256
                and manifest.manifest_sha256 != req.expected_manifest_sha256
            ):
                raise TransitionServiceError("MANIFEST_CAS_MISMATCH")
        installed = read_generation(root)
        if req.expected_generation is None:
            if installed is not None and not allow_replay:
                raise TransitionServiceError("EXPECTED_INITIAL_GENERATION_MISMATCH")
        elif not allow_replay and (
            installed is None
            or installed.generation != req.expected_generation
            or installed.writer_id != req.expected_writer_id
        ):
            raise TransitionServiceError("GENERATION_OR_WRITER_MISMATCH")
        return root

    def _authority(self, req: WriterTransitionRequest) -> VerifiedWriterTransitionAuthority:
        try:
            from nexus.orchestrator.autonomy_policy import evaluate_writer_transition_authority

            value = load_verified_writer_transition_authority(
                request=req, loaded_source_identity=self._source
            )
            if not is_registered_authority(value):
                raise WriterAuthorityError("AUTHORITY_HANDLE_UNREGISTERED")
            if not is_authorized_for_request(value, req):
                raise WriterAuthorityError("AUTHORITY_REQUEST_UNBOUND")
            valid, reason = evaluate_writer_transition_authority(
                value, operation_digest=req.authorization_intent_digest
            )
            if not valid:
                raise WriterAuthorityError(reason)
            self._authority_handle = value
            return value
        except WriterAuthorityError as exc:
            raise TransitionServiceError(str(exc)) from exc

    def _collector(self, req: WriterTransitionRequest) -> Mapping[str, Any]:
        if _COLLECTOR_LOADER is None:
            raise MissingDependency("MISSING_WRITER_TRANSITION_COLLECTOR")
        evidence = _COLLECTOR_LOADER(req)
        if isinstance(evidence, _VerifiedCollectorEvidence):
            evidence = evidence.payload
        if not isinstance(evidence, Mapping):
            raise TransitionServiceError("COLLECTOR_RECEIPT_INVALID")
        for ident, digest in (
            ("drain_receipt_id", "drain_receipt_hash"),
            ("snapshot_receipt_id", "snapshot_receipt_hash"),
            ("rollback_receipt_id", "rollback_receipt_hash"),
            ("loaded_writer_plan_id", "loaded_writer_plan_hash"),
        ):
            if evidence.get(ident) != getattr(req, ident) or evidence.get(digest) != getattr(
                req, digest
            ):
                raise TransitionServiceError("COLLECTOR_RECEIPT_MISMATCH")
        if (
            evidence.get("request_digest") != req.request_digest
            or evidence.get("drain_state") != "DRAINED"
        ):
            raise TransitionServiceError("COLLECTOR_NOT_DRAINED")
        if (
            evidence.get("root_id") != req.root_id
            or evidence.get("root_identity") != req.expected_root_identity
        ):
            raise TransitionServiceError("COLLECTOR_ROOT_MISMATCH")
        if (
            evidence.get("source_head") != req.expected_source_head
            or evidence.get("source_tree") != req.expected_source_tree
        ):
            raise TransitionServiceError("COLLECTOR_SOURCE_MISMATCH")
        if evidence.get("generation") not in (req.expected_generation, req.next_generation):
            raise TransitionServiceError("COLLECTOR_GENERATION_MISMATCH")
        artifact_bytes = evidence.get("artifact_bytes")
        if not isinstance(artifact_bytes, Mapping):
            raise TransitionServiceError("COLLECTOR_ARTIFACT_INVALID")
        for item in req.selections:
            data = artifact_bytes.get(item.relative_path)
            if (
                not isinstance(data, (bytes, bytearray))
                or len(data) != item.size
                or hashlib.sha256(bytes(data)).hexdigest() != item.expected_sha256
            ):
                raise TransitionServiceError("COLLECTOR_ARTIFACT_MISMATCH")
        receipt_bytes = evidence.get("source_receipt_bytes")
        if (
            not isinstance(receipt_bytes, (bytes, bytearray))
            or hashlib.sha256(bytes(receipt_bytes)).hexdigest() != req.accepted_source_receipt_hash
        ):
            raise TransitionServiceError("SOURCE_ACCEPTANCE_RECEIPT_MISMATCH")
        return evidence

    def _grant(self, req: WriterTransitionRequest) -> None:
        from nexus.contracts.autonomy_goal import (
            AutonomyActionClass,
            RepositoryIdentity,
            canonical_autonomy_hash,
        )
        from nexus.orchestrator.standing_grant_store import (
            StandingGrantReceiptError,
            authorize_durable_standing_grant_effect,
            load_standing_grant_receipt,
        )

        # The grant effect excludes only the authority locator/hash so the
        # external authority can bind the intent without a hash cycle.
        effect = req.to_dict()
        effect.pop("authority_receipt_id", None)
        effect.pop("authority_receipt_hash", None)
        effect["operation_digest"] = req.authorization_intent_digest
        try:
            durable = load_standing_grant_receipt()
            if durable is None or durable.context.thread_id != self._authority_handle.thread_id:
                raise TransitionServiceError("CANONICAL_GRANT_THREAD_MISMATCH")
            result = authorize_durable_standing_grant_effect(
                repository=RepositoryIdentity(
                    repository_id=self._source.repository,
                    canonical_remote="https://github.com/James3014/Nexus-new.git",
                ),
                action=AutonomyActionClass.RUNTIME_ACTIVATE,
                effect=effect,
            )
            if result.get("grant_receipt_hash") != durable.receipt_hash:
                raise TransitionServiceError("CANONICAL_GRANT_CHANGED")
            expected_effect_hash = canonical_autonomy_hash(effect)
            if (
                not isinstance(result, Mapping)
                or result.get("mutation_authorized") is not True
                or result.get("effect_hash") != expected_effect_hash
            ):
                raise TransitionServiceError("CANONICAL_GRANT_EFFECT_MISMATCH")
            for key in ("owner_id", "coordinator_id", "goal_id", "grant_id"):
                expected = getattr(self._authority_handle, key, "")
                if expected and result.get(key) != expected:
                    raise TransitionServiceError("CANONICAL_GRANT_SCOPE_MISMATCH")
            expected_grant_hash = getattr(self._authority_handle, "grant_receipt_hash", "")
            if expected_grant_hash and result.get("grant_receipt_hash") != expected_grant_hash:
                raise TransitionServiceError("CANONICAL_GRANT_SCOPE_MISMATCH")
            expected_context_hash = getattr(self._authority_handle, "grant_context_hash", "")
            if expected_context_hash and result.get("context_hash") != expected_context_hash:
                raise TransitionServiceError("CANONICAL_GRANT_SCOPE_MISMATCH")
            expected_repo = getattr(self._authority_handle, "repository", "")
            if expected_repo:
                expected_repo = RepositoryIdentity(
                    repository_id=expected_repo,
                    canonical_remote="https://github.com/James3014/Nexus-new.git",
                ).model_dump(mode="json")
                if result.get("repository") != expected_repo:
                    raise TransitionServiceError("CANONICAL_GRANT_SCOPE_MISMATCH")
            self._grant_result = result
        except (StandingGrantReceiptError, ValueError) as exc:
            raise TransitionServiceError(f"CANONICAL_GRANT_DENIED:{exc}") from exc

    def _validated_outcome(
        self, root: Path, req: WriterTransitionRequest, prior: Mapping[str, Any]
    ) -> TransitionReceipt:
        after = read_manifest(root)
        generation = read_generation(root)
        if (
            after is None
            or after.owner_id != req.expected_owner_id
            or after.writer_id != req.next_writer_id
            or after.generation != req.next_generation
            or after.transaction_id != req.transaction_id
            or generation is None
            or generation.generation != req.next_generation
            or generation.writer_id != req.next_writer_id
        ):
            raise TransitionServiceError("COMMITTED_REPLAY_READBACK_MISMATCH")
        before = prior.get("before_observation")
        expected_before = {
            "present": req.expected_generation is not None,
            "manifest_sha256": req.expected_manifest_sha256,
        }
        if (
            before != expected_before
            or after.previous_manifest_sha256 != req.expected_manifest_sha256
        ):
            raise TransitionServiceError("COMMITTED_BEFORE_OBSERVATION_MISMATCH")
        expected_selections = {
            (item.entry_id, item.role, item.relative_path) for item in req.selections
        }
        if {
            (item.entry_id, item.role, item.relative_path) for item in after.files
        } != expected_selections:
            raise TransitionServiceError("COMMITTED_SELECTION_MISMATCH")
        classified = classify(
            StateOwnerBinding(req.expected_owner_id, root, req.next_generation, req.transaction_id)
        )
        if classified.status != COMMITTED_STATUS or classified.reconcile_only:
            raise TransitionServiceError("COMMITTED_CLASSIFICATION_UNKNOWN")
        outcome = prior.get("outcome")
        # Reconstruct all bound fields from the current authenticated request and
        # physical readback; compare the complete canonical persisted receipt,
        # including its digest. No persisted field supplies new authority.
        committed = self._receipt(
            req,
            ReceiptState.COMMITTED,
            writes=True,
            observed_before=req.expected_manifest_sha256 or "",
            observed_after=after.manifest_sha256,
        )
        committed.require_claim_fields()
        if prior.get("state") == "INTENT_RECORDED" and outcome == {}:
            return committed
        if not isinstance(outcome, Mapping) or dict(outcome) != committed.to_dict():
            raise TransitionServiceError("COMMITTED_OUTCOME_BINDING_MISMATCH")
        return committed

    def preflight(self, raw: WriterTransitionRequest | Mapping[str, Any]) -> TransitionReceipt:
        req = self._request(raw)
        if req.operation not in (Operation.PREFLIGHT, Operation.APPLY):
            return self._receipt(req, ReceiptState.DENIED, error="OPERATION_MISMATCH_PREFLIGHT")
        try:
            self._authority(req)
            self._collector(req)
            self._grant(req)
            root = self._roots.get(req.root_id)
            prior = _read_intent(root) if isinstance(root, Path) and root.is_dir() else None
            self._validate_common(req, allow_replay=prior is not None)
            if prior and prior.get("request_digest") != req.request_digest:
                raise TransitionServiceError("CONFLICTING_REPLAY")
            if (
                prior
                and prior.get("request_digest") == req.request_digest
                and prior.get("idempotency_key") == req.idempotency_key
                and prior.get("state") == "COMMITTED"
            ):
                return TransitionReceipt(
                    req.request_digest,
                    req.transaction_id,
                    ReceiptState.PREFLIGHT_READY,
                    False,
                    False,
                    True,
                    False,
                )
            if (
                prior
                and prior.get("request_digest") == req.request_digest
                and prior.get("idempotency_key") == req.idempotency_key
            ):
                return TransitionReceipt(
                    req.request_digest,
                    req.transaction_id,
                    ReceiptState.PREFLIGHT_READY,
                    False,
                    False,
                    True,
                    True,
                )
            return TransitionReceipt(
                req.request_digest,
                req.transaction_id,
                ReceiptState.PREFLIGHT_READY,
                False,
                False,
                False,
                False,
            )
        except (
            TransitionServiceError,
            TransitionValidationError,
            OSError,
            subprocess.CalledProcessError,
        ) as exc:
            return TransitionReceipt(
                req.request_digest if isinstance(req, WriterTransitionRequest) else "",
                getattr(req, "transaction_id", ""),
                ReceiptState.DENIED,
                False,
                False,
                False,
                False,
                str(exc),
            )

    def apply(self, raw: WriterTransitionRequest | Mapping[str, Any]) -> TransitionReceipt:
        req = self._request(raw)
        if req.operation is not Operation.APPLY:
            return self._receipt(req, ReceiptState.DENIED, error="OPERATION_MISMATCH_APPLY")
        writes_started = False
        try:
            root = self._validate_common(req, allow_replay=True)
            prior = _read_intent(root)
            if (
                prior
                and prior.get("request_digest") == req.request_digest
                and prior.get("idempotency_key") == req.idempotency_key
                and prior.get("state") == "COMMITTED"
            ):
                self._authority(req)
                self._collector(req)
                self._grant(req)
                committed = self._validated_outcome(root, req, prior)
                return replace(committed, writes_observed=False, replayed=True)

            if prior is not None:
                raise TransitionServiceError(
                    "RECONCILE_REQUIRED"
                    if prior.get("request_digest") == req.request_digest
                    else "CONFLICTING_REPLAY"
                )
            ready = self.preflight(req)
            if ready.state is not ReceiptState.PREFLIGHT_READY:
                return ready
            token = EventWriterGeneration(req.next_generation, req.next_writer_id)
            with event_store_lock(root):
                # All CAS and physical checks are repeated while the one source-owned
                # event-store lock is held, immediately before the durable intent.
                self._validate_common(req)
                self._authority(req)
                self._collector(req)
                self._grant(req)
                before = read_manifest(root)
                before_hash = before.manifest_sha256 if before is not None else ""
                _record_intent(
                    root,
                    req,
                    before_observation={
                        "present": before is not None,
                        "manifest_sha256": before_hash or None,
                    },
                )
                writes_started = True
                install_generation(root, token, expected_generation=req.expected_generation)
                _record_intent(root, req, phase="GENERATION_ADVANCED")
                binding = StateOwnerBinding(
                    req.expected_owner_id, root, req.next_generation, req.transaction_id
                )
                selections = tuple(
                    StateOwnerSelection(x.entry_id, x.role, x.relative_path) for x in req.selections
                )
                with owner_transaction_guard(
                    binding,
                    writer_generation=token,
                    selections=selections,
                    previous_manifest_sha256=req.expected_manifest_sha256,
                ) as context:
                    _record_intent(root, req, phase="PREPARED")
                    committed = commit_owner_transaction(context)
                after = read_manifest(root)
                if (
                    after is None
                    or after.owner_id != req.expected_owner_id
                    or after.writer_id != req.next_writer_id
                    or after.generation != req.next_generation
                    or after.transaction_id != req.transaction_id
                    or after.manifest_sha256 != committed.manifest_sha256
                ):
                    raise TransitionServiceError("COMMIT_POSTCONDITION_MISMATCH")
                receipt = self._receipt(
                    req,
                    ReceiptState.COMMITTED,
                    writes=True,
                    observed_before=before_hash,
                    observed_after=after.manifest_sha256,
                )
                receipt.require_claim_fields()
                _record_intent(root, req, state="COMMITTED", receipt=receipt.to_dict())
                return receipt
        except Exception as exc:
            return self._receipt(
                req,
                ReceiptState.UNKNOWN,
                writes=writes_started,
                reconcile=writes_started,
                error=str(exc),
            )

    def reconcile(self, raw: WriterTransitionRequest | Mapping[str, Any]) -> TransitionReceipt:
        req = self._request(raw)
        root = self._roots.get(req.root_id)
        if req.operation is not Operation.RECONCILE:
            return self._receipt(req, ReceiptState.DENIED, error="OPERATION_MISMATCH_RECONCILE")
        if root is None:
            return TransitionReceipt(
                req.request_digest,
                req.transaction_id,
                ReceiptState.DENIED,
                False,
                False,
                False,
                False,
                "ROOT_UNKNOWN",
            )
        try:
            prior = _read_intent(root)
            if not prior or prior.get("state") not in {"INTENT_RECORDED", "COMMITTED"}:
                raise TransitionServiceError("RECONCILE_INTENT_MISSING")
            original = prior.get("request")
            if not isinstance(original, Mapping):
                raise TransitionServiceError("RECONCILE_INTENT_MALFORMED")
            auth_req = WriterTransitionRequest.from_mapping(original)
            if (
                replace(req, operation=auth_req.operation) != auth_req
                or prior.get("request_digest") != auth_req.request_digest
                or prior.get("authorization_intent_digest") != auth_req.authorization_intent_digest
            ):
                raise TransitionServiceError("RECONCILE_TRANSACTION_MISMATCH")
            self._authority(auth_req)
            self._collector(auth_req)
            self._grant(auth_req)
            self._validate_common(auth_req, allow_replay=True)
            committed = self._validated_outcome(root, auth_req, prior)
            return replace(
                committed, state=ReceiptState.RECONCILED, writes_observed=False, replayed=True
            )
        except Exception as exc:
            return TransitionReceipt(
                req.request_digest,
                req.transaction_id,
                ReceiptState.UNKNOWN,
                False,
                False,
                False,
                True,
                str(exc),
            )


def _git_identity(root: Path) -> tuple[str, str]:
    try:
        head = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        tree = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD^{tree}"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if len(head) != 40 or len(tree) != 40:
            raise ValueError
        return head, tree
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        raise MissingDependency("MISSING_LOADED_SOURCE_IDENTITY") from exc


def build_source_owned_transition_service(service: Any = None) -> StateOwnerTransitionService:
    """Construct from the already-loaded source/task service registry.

    Request fields are intentionally never consulted for source or root
    selection.  A production caller must expose a loaded source identity and
    exact root registry; otherwise construction fails closed.
    """
    if service is None:
        try:
            from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

            service = SelfHostedTaskService(auto_reconcile=False)
        except Exception as exc:
            raise MissingDependency("MISSING_LOADED_TASK_SERVICE") from exc
    source = getattr(service, "loaded_source_identity", None) or getattr(
        service, "source_identity", None
    )
    source_root = getattr(service, "source_root", None) or getattr(service, "repository_root", None)
    if source is None and source_root is not None:
        source_root = Path(source_root).resolve()
        head, tree = _git_identity(source_root)
        card = getattr(service, "active_card_path", None) or getattr(service, "card_path", None)
        if not card:
            raise MissingDependency("MISSING_LOADED_TASK_CARD")
        card_path = Path(card)
        card_rel = (
            str(card_path.relative_to(source_root)) if card_path.is_absolute() else str(card_path)
        )
        card_bytes = (source_root / card_rel).read_bytes()
        source = LoadedSourceIdentity(
            "James3014/Nexus-new", head, tree, card_rel, hashlib.sha256(card_bytes).hexdigest()
        )
    if not isinstance(source, LoadedSourceIdentity):
        raise MissingDependency("MISSING_LOADED_SOURCE_IDENTITY")
    roots = getattr(service, "writer_roots", None) or getattr(service, "roots", None)
    state_dir = getattr(service, "state_dir", None)
    if roots is None and state_dir is not None:
        roots = {"task_state": Path(state_dir).resolve()}
    if not isinstance(roots, Mapping) or not roots:
        raise MissingDependency("MISSING_LOADED_WRITER_ROOTS")
    return StateOwnerTransitionService(
        roots=roots,
        source=source,
        source_root=Path(source_root).resolve() if source_root else None,
        service=service,
    )
