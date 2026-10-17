"""Task Card create/commit of ``UnifiedMCPGateway``.

Big-file split G9a (Issue #2548). ``_TaskCardMixin`` holds ``_task_card_create``,
``_task_card_expected_evidence``, ``_task_card_issue_promises`` and ``_task_card_commit``,
plus the shared ``_safe_slug`` and ``_exact_hash`` helpers (also used through ``self`` by
the worker-candidate and candidate-operation mixins), moved out of
``nexus/orchestrator/unified_mcp_gateway.py``. Their source lines are verbatim, except that
every gateway-module name they load other than the standard library (``_git``,
``CANONICAL_SOURCE_ROOT``, ``_require_bound_controller``, ``_text``,
``_safe_relative_path``, ``protected_path_reason``, the card evidence / Issue-promise
parsers and models, ``bootstrap_agent_authority``, ``GatewayInputError``, ...) is resolved at
call time through ``_gateway()``, so patches on the gateway module keep reaching this code.

The owner authority check (``_require_owner_effect_authority`` / ``_owner_effect_key``)
stays in the gateway class and is reached through ``self``.
"""

from __future__ import annotations

import difflib
import hashlib
import importlib
import os
import re
import shutil
import subprocess
from typing import TYPE_CHECKING, Any, Mapping, Optional
from uuid import uuid4

if TYPE_CHECKING:
    from nexus.orchestrator.task_contract import ExpectedEvidenceUniverse, IssuePromiseBinding

    # Typing only: the candidate-operation (and, through it, every other mixin) helpers,
    # including the stubs for the members the gateway class provides.
    from nexus.orchestrator.unified_mcp_gateway_parts.candidate_ops import (
        _CandidateOpsMixin as _TaskCardBase,
    )
else:
    _TaskCardBase = object


def _gateway():
    # Late binding: the gateway imports this module at its top level, so its own
    # (and its patched) names are only resolved once a method runs.
    return importlib.import_module("nexus.orchestrator.unified_mcp_gateway")


class _TaskCardMixin(_TaskCardBase):
    """Mixin base of ``UnifiedMCPGateway``; never instantiated on its own."""

    # fmt: off
    @staticmethod
    def _safe_slug(value: Any, field: str, *, max_length: int = 80) -> str:
        result = _gateway()._text(value, field, max_length=max_length)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0," + str(max_length - 1) + r"}", result):
            raise _gateway().GatewayInputError(f"{field} must be a stable bounded slug")
        return result

    def _task_card_create(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if arguments.get("owner_confirmation") is not True:
            raise _gateway().GatewayInputError("OWNER_CONFIRMATION_REQUIRED")
        _gateway()._require_bound_controller()
        owner_key = self._owner_effect_key(arguments)
        campaign = self._safe_slug(arguments.get("campaign_id"), "campaign_id")
        task_id = self._safe_slug(arguments.get("task_id"), "task_id")
        objective = _gateway()._text(arguments.get("objective"), "objective", max_length=4000)
        allowed = [str(path).strip() for path in arguments.get("allowed_files") or [] if str(path).strip()]
        if not allowed or len(allowed) > 10:
            raise _gateway().GatewayInputError("allowed_files must contain 1-10 bounded paths")
        for path in allowed:
            resolved_path = _gateway()._safe_relative_path(path, "allowed_files")
            # #1750: a card must never authorize authority-bearing paths, named
            # directly or through a symlink. This runs before any authority
            # check, record or file write.
            reason = _gateway().protected_path_reason(path) or _gateway().protected_path_reason(
                resolved_path.relative_to(_gateway().CANONICAL_SOURCE_ROOT).as_posix()
            )
            if reason is not None:
                raise _gateway().GatewayInputError(f"TASK_CARD_CREATE_PROTECTED_PATH:{reason}:{path}")
        verifiers = [str(command).strip() for command in arguments.get("verifier_commands") or [] if str(command).strip()]
        if not verifiers:
            raise _gateway().GatewayInputError("verifier_commands is required")
        universe = self._task_card_expected_evidence(arguments)
        promises = self._task_card_issue_promises(arguments, universe)
        head = self._exact_hash(_gateway()._git("rev-parse", "HEAD").strip(), "expected_head", 40)
        effect: dict[str, Any] = {
            "campaign_id": campaign,
            "task_id": task_id,
            "expected_head": head,
            "allowed_files": allowed,
            "verifier_commands": verifiers,
            "objective_sha256": hashlib.sha256(objective.encode("utf-8")).hexdigest(),
        }
        if universe is not None:
            # Bind the Owner authorization to the exact declared universe.
            effect["expected_evidence_identity"] = universe.universe_identity
        if promises is not None:
            # ...and to the exact Issue promise -> subject map (#2532).
            effect["issue_promises_identity"] = promises.binding_identity
        campaign_root = _gateway().CANONICAL_SOURCE_ROOT / "tasks" / campaign
        index_path = campaign_root / "INDEX.md"
        card_path = campaign_root / f"00-{task_id}.md"
        if campaign_root.exists() or index_path.exists() or card_path.exists():
            raise _gateway().GatewayInputError("TASK_CARD_CREATE_WOULD_OVERWRITE")
        card = "\n".join([
            f"# Task Card: {task_id}", "", "artifact_authority: current", f"task_id: `{task_id}`",
            "owner: James Chen", "status: ACTIVE", "execution_lane: GOVERNED",
            "commit_required: true", "candidate_required: true", "worker_may_commit: true",
            "worker_may_approve: false", "worker_may_integrate: false",
            "worker_may_push: false", "AUTO_CHAIN: false", "", "## Objective", "", objective, "",
            "## Allowed files", "", *[f"- `{path}`" for path in allowed], "", "## Verification commands", "",
            "```bash", *verifiers, "```", "",
            *(
                []
                if universe is None
                else [
                    "## Expected evidence", "",
                    "```" + _gateway().TASK_CARD_EXPECTED_EVIDENCE_FENCE, universe.canonical_json(), "```", "",
                ]
            ),
            *(
                []
                if promises is None
                else [
                    "## Issue promises", "",
                    "```" + _gateway().TASK_CARD_ISSUE_PROMISES_FENCE, promises.canonical_json(), "```", "",
                ]
            ),
            "## Exit criteria", "", "Owner review of the exact scoped commit.",
            "", "## Block classification", "", "Unverifiable or out-of-scope mutation is a HARD_BLOCK.", "",
        ])
        # The hashed card is the only universe source (#2181): the rendered card
        # must read back as exactly the validated universe, or as none at all.
        # This also stops objective or verifier text from smuggling in a block.
        try:
            declared = _gateway().parse_task_card_expected_evidence(card)
        except ValueError as exc:
            raise _gateway().GatewayInputError("TASK_CARD_CREATE_EXPECTED_EVIDENCE_INVALID:card text declares a malformed block") from exc
        if declared != (None if universe is None else universe.model_dump(mode="json")):
            raise _gateway().GatewayInputError("TASK_CARD_CREATE_EXPECTED_EVIDENCE_INVALID:card text does not round-trip")
        # The same holds for the promise map (#2532).
        try:
            declared_promises = _gateway().parse_task_card_issue_promises(card)
        except ValueError as exc:
            raise _gateway().GatewayInputError("TASK_CARD_CREATE_ISSUE_PROMISES_INVALID:card text declares a malformed block") from exc
        if declared_promises != (None if promises is None else promises.model_dump(mode="json")):
            raise _gateway().GatewayInputError("TASK_CARD_CREATE_ISSUE_PROMISES_INVALID:card text does not round-trip")
        # Authority is checked (and recorded) only for a card that passed every
        # validation above, so a rejected card never consumes or records it.
        owner_authority = self._require_owner_effect_authority(
            _gateway().AutonomyActionClass.TASK_CARD_CREATE,
            effect,
            key=owner_key,
        )
        index = "\n".join([
            f"# Campaign Index: {campaign}", "", "artifact_authority: current", "owner: James Chen",
            "status: active, governed and sequential", "AUTO_CHAIN: false", "", "## Objective", "", objective,
            "", "## Ordered cards", "", "| Order | Task ID | Card | Status | Dependency |", "|---:|---|---|---|---|",
            f"| 0 | `{task_id}` | `00-{task_id}.md` | ACTIVE | Owner confirmation |", "",
        ])
        tasks_root = _gateway().CANONICAL_SOURCE_ROOT / "tasks"
        tasks_root.mkdir(parents=True, exist_ok=True)
        temporary_root = tasks_root / f".{campaign}.create-{uuid4().hex}"
        try:
            temporary_root.mkdir(parents=False, exist_ok=False)
            temporary_index = temporary_root / "INDEX.md"
            temporary_card = temporary_root / f"00-{task_id}.md"
            temporary_index.write_text(index, encoding="utf-8")
            temporary_card.write_text(card, encoding="utf-8")
            if not temporary_index.is_file() or not temporary_card.is_file():
                raise RuntimeError("TASK_CARD_CREATE_ATOMIC_WRITE_FAILED")
            hashed = subprocess.run(["git", "hash-object", str(temporary_card)], cwd=_gateway().CANONICAL_SOURCE_ROOT, capture_output=True, text=True, check=False)
            card_hash = hashed.stdout.strip()
            if hashed.returncode != 0 or not _gateway()._SHA_RE.fullmatch(card_hash):
                raise RuntimeError("TASK_CARD_CREATE_HASH_FAILED")
            card_sha256 = hashlib.sha256(card.encode("utf-8")).hexdigest()
            if campaign_root.exists():
                raise _gateway().GatewayInputError("TASK_CARD_CREATE_WOULD_OVERWRITE")
            os.replace(temporary_root, campaign_root)
        except Exception:
            shutil.rmtree(temporary_root, ignore_errors=True)
            raise
        diff_lines = list(difflib.unified_diff([], card.splitlines(True), fromfile="/dev/null", tofile=str(card_path.relative_to(_gateway().CANONICAL_SOURCE_ROOT))))
        index_diff_lines = list(difflib.unified_diff([], index.splitlines(True), fromfile="/dev/null", tofile=str(index_path.relative_to(_gateway().CANONICAL_SOURCE_ROOT))))
        return {
            "schema": "nexus.task_card_create.v1",
            "status": "CREATED_PENDING_COMMIT",
            "campaign_id": campaign,
            "task_id": task_id,
            "index_path": str(index_path.relative_to(_gateway().CANONICAL_SOURCE_ROOT)),
            "card_path": str(card_path.relative_to(_gateway().CANONICAL_SOURCE_ROOT)),
            "card_hash": card_sha256,
            "index_hash": hashlib.sha256(index.encode("utf-8")).hexdigest(),
            "git_blob_sha": card_hash,
            "exact_card_diff": "".join(diff_lines),
            "exact_index_diff": "".join(index_diff_lines),
            "successor_execution": "NOT_STARTED",
            "authority_basis": _gateway().bootstrap_agent_authority.authority_basis(owner_authority),
            "owner_confirmation": _gateway().bootstrap_agent_authority.authority_basis(owner_authority)
            == _gateway().bootstrap_agent_authority.BASIS_OWNER_GRANT,
            "owner_authority": owner_authority,
        }

    @staticmethod
    def _task_card_expected_evidence(arguments: Mapping[str, Any]) -> Optional[ExpectedEvidenceUniverse]:
        """Validate the optional card-declared universe with the card reader's model."""
        raw = arguments.get("expected_evidence")
        if raw is None:
            return None
        if not isinstance(raw, Mapping):
            raise _gateway().GatewayInputError("TASK_CARD_CREATE_EXPECTED_EVIDENCE_INVALID:expected_evidence must be an object")
        try:
            return _gateway().ExpectedEvidenceUniverse.model_validate(dict(raw))
        except ValueError as exc:
            reason = " ".join(str(exc).split())[:500]
            raise _gateway().GatewayInputError(f"TASK_CARD_CREATE_EXPECTED_EVIDENCE_INVALID:{reason}") from exc

    @staticmethod
    def _task_card_issue_promises(
        arguments: Mapping[str, Any], universe: Optional[ExpectedEvidenceUniverse]
    ) -> Optional[IssuePromiseBinding]:
        """Validate the optional Issue promise -> subject map against the card universe (#2532).

        Runs before any authority check or write. Every promise of the Issue
        set must be mapped, every mapped subject must be declared in this
        card's universe, and each promise needs at least one REQUIRED /
        APPLICABLE subject.
        """
        raw = arguments.get("issue_promises")
        if raw is None:
            return None
        prefix = "TASK_CARD_CREATE_ISSUE_PROMISES_INVALID"
        if not isinstance(raw, Mapping):
            raise _gateway().GatewayInputError(f"{prefix}:issue_promises must be an object")
        if universe is None:
            raise _gateway().GatewayInputError(f"{prefix}:issue_promises requires expected_evidence")
        try:
            binding = _gateway().IssuePromiseBinding.model_validate(dict(raw))
        except ValueError as exc:
            reason = " ".join(str(exc).split())[:500]
            raise _gateway().GatewayInputError(f"{prefix}:{reason}") from exc
        if binding.expected_evidence_identity != universe.universe_identity:
            raise _gateway().GatewayInputError(f"{prefix}:expected_evidence_identity is not this card's universe")
        subjects = {subject.logical_subject_id: subject for subject in universe.subjects}
        for entry in binding.map:
            unknown = [sid for sid in entry.subject_ids if sid not in subjects]
            if unknown:
                raise _gateway().GatewayInputError(
                    f"{prefix}:subject not in expected_evidence for {entry.promise_id}: {unknown[0][:200]}"
                )
            if not any(
                subjects[sid].requirement_mode is _gateway().EvidenceRequirementMode.REQUIRED
                and subjects[sid].applicability is _gateway().EvidenceSubjectApplicability.APPLICABLE
                for sid in entry.subject_ids
            ):
                raise _gateway().GatewayInputError(
                    f"{prefix}:promise has no REQUIRED/APPLICABLE subject: {entry.promise_id}"
                )
        return binding

    def _task_card_commit(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if arguments.get("owner_confirmation") is not True:
            raise _gateway().GatewayInputError("OWNER_CONFIRMATION_REQUIRED")
        _gateway()._require_bound_controller()
        owner_key = self._owner_effect_key(arguments)
        campaign = self._safe_slug(arguments.get("campaign_id"), "campaign_id")
        task_id = self._safe_slug(arguments.get("task_id"), "task_id")
        expected_head = str(arguments.get("expected_head") or "").strip().lower()
        expected_card_hash = str(arguments.get("card_hash") or "").strip().lower()
        expected_index_hash = str(arguments.get("index_hash") or "").strip().lower()
        if not _gateway()._SHA_RE.fullmatch(expected_head):
            raise _gateway().GatewayInputError("expected_head must be a lowercase 40-hex SHA")
        if not re.fullmatch(r"[0-9a-f]{64}", expected_card_hash):
            raise _gateway().GatewayInputError("card_hash must be a lowercase 64-hex SHA-256")
        if not re.fullmatch(r"[0-9a-f]{64}", expected_index_hash):
            raise _gateway().GatewayInputError("index_hash must be a lowercase 64-hex SHA-256")

        campaign_root = _gateway().CANONICAL_SOURCE_ROOT / "tasks" / campaign
        index_path = campaign_root / "INDEX.md"
        card_path = campaign_root / f"00-{task_id}.md"
        if not index_path.is_file() or not card_path.is_file():
            raise _gateway().GatewayInputError("TASK_CARD_COMMIT_SOURCE_MISSING")
        for path in (index_path, card_path):
            if path.is_symlink():
                raise _gateway().GatewayInputError("TASK_CARD_COMMIT_SYMLINK_FORBIDDEN")
            try:
                path.resolve().relative_to(_gateway().CANONICAL_SOURCE_ROOT.resolve())
            except ValueError as exc:
                raise _gateway().GatewayInputError("TASK_CARD_COMMIT_PATH_ESCAPE") from exc

        card_bytes = card_path.read_bytes()
        index_bytes = index_path.read_bytes()
        card_text = card_bytes.decode("utf-8")
        index_text = index_bytes.decode("utf-8")
        if hashlib.sha256(card_bytes).hexdigest() != expected_card_hash:
            raise _gateway().GatewayInputError("TASK_CARD_COMMIT_HASH_MISMATCH")
        if hashlib.sha256(index_bytes).hexdigest() != expected_index_hash:
            raise _gateway().GatewayInputError("TASK_CARD_COMMIT_INDEX_HASH_MISMATCH")
        if f"task_id: `{task_id}`" not in card_text or "status: ACTIVE" not in card_text or "AUTO_CHAIN: false" not in card_text:
            raise _gateway().GatewayInputError("TASK_CARD_COMMIT_CARD_NOT_ACTIVE")
        if f"# Campaign Index: {campaign}" not in index_text or "AUTO_CHAIN: false" not in index_text:
            raise _gateway().GatewayInputError("TASK_CARD_COMMIT_INDEX_NOT_BOUND")

        current_head = _gateway()._git("rev-parse", "HEAD").strip()
        if current_head != expected_head:
            raise _gateway().GatewayInputError("TASK_CARD_COMMIT_HEAD_MISMATCH")
        _gateway()._require_bound_controller(expected_head)
        owner_authority = self._require_owner_effect_authority(
            _gateway().AutonomyActionClass.TASK_CARD_COMMIT,
            {
                "campaign_id": campaign,
                "task_id": task_id,
                "expected_head": expected_head,
                "card_hash": expected_card_hash,
                "index_hash": expected_index_hash,
            },
            key=owner_key,
        )
        branch = subprocess.run(
            ["git", "symbolic-ref", "-q", "--short", "HEAD"],
            cwd=_gateway().CANONICAL_SOURCE_ROOT,
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
        )
        if branch.returncode == 0 and branch.stdout.strip():
            raise _gateway().GatewayInputError("TASK_CARD_COMMIT_REQUIRES_DETACHED_CONTROLLER")
        if branch.returncode not in (0, 1):
            raise RuntimeError(branch.stderr.strip() or "failed to inspect controller branch state")

        index_rel = str(index_path.relative_to(_gateway().CANONICAL_SOURCE_ROOT))
        card_rel = str(card_path.relative_to(_gateway().CANONICAL_SOURCE_ROOT))
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=_gateway().CANONICAL_SOURCE_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=3.0,
            check=False,
        )
        if status.returncode != 0:
            raise RuntimeError(status.stderr.decode("utf-8", errors="replace").strip() or "git status failed")
        entries = {os.fsdecode(raw) for raw in status.stdout.split(b"\0") if raw}
        expected_entries = {f"?? {index_rel}", f"?? {card_rel}"}
        if entries != expected_entries:
            raise _gateway().GatewayInputError("TASK_CARD_COMMIT_CONTROLLER_NOT_EXACTLY_PENDING_CARD")

        _gateway()._git("add", "--", index_rel, card_rel)
        staged = {line for line in _gateway()._git("diff", "--cached", "--name-only", "--", index_rel, card_rel).splitlines() if line}
        if staged != {index_rel, card_rel}:
            _gateway()._git("reset", "--", index_rel, card_rel)
            raise RuntimeError("TASK_CARD_COMMIT_STAGE_MISMATCH")

        def staged_sha256(relative: str) -> str:
            result = subprocess.run(
                ["git", "show", f":{relative}"],
                cwd=_gateway().CANONICAL_SOURCE_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=3.0,
                check=False,
            )
            if result.returncode != 0:
                raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip() or "failed to read staged task-card content")
            return hashlib.sha256(result.stdout).hexdigest()

        try:
            if staged_sha256(card_rel) != expected_card_hash or staged_sha256(index_rel) != expected_index_hash:
                raise RuntimeError("TASK_CARD_COMMIT_STAGED_HASH_MISMATCH")
            _gateway()._git("commit", "-m", f"chore(tasks): bind {task_id}", timeout=30.0)
        except Exception:
            _gateway()._git("reset", "--", index_rel, card_rel)
            raise

        commit_sha = _gateway()._git("rev-parse", "HEAD").strip()
        parent_sha = _gateway()._git("rev-parse", "HEAD^").strip()
        tree_sha = _gateway()._git("rev-parse", "HEAD^{tree}").strip()
        if parent_sha != expected_head or not _gateway()._SHA_RE.fullmatch(commit_sha) or not _gateway()._SHA_RE.fullmatch(tree_sha):
            raise RuntimeError("TASK_CARD_COMMIT_IDENTITY_MISMATCH")
        remaining = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=_gateway().CANONICAL_SOURCE_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=3.0,
            check=False,
        )
        if remaining.returncode != 0:
            raise RuntimeError(remaining.stderr.decode("utf-8", errors="replace").strip() or "git status failed")
        if remaining.stdout:
            raise RuntimeError("TASK_CARD_COMMIT_CONTROLLER_NOT_CLEAN_AFTER_COMMIT")
        committed_paths = {
            line for line in _gateway()._git("diff-tree", "--no-commit-id", "--name-only", "-r", commit_sha).splitlines() if line
        }
        if committed_paths != {index_rel, card_rel}:
            raise RuntimeError("TASK_CARD_COMMIT_SCOPE_MISMATCH")
        return {
            "schema": "nexus.task_card_commit.v1",
            "status": "COMMITTED",
            "campaign_id": campaign,
            "task_id": task_id,
            "previous_head": expected_head,
            "commit_sha": commit_sha,
            "tree_sha": tree_sha,
            "index_path": index_rel,
            "card_path": card_rel,
            "card_hash": expected_card_hash,
            "index_hash": expected_index_hash,
            "committed_paths": sorted(committed_paths),
            "controller_clean": True,
            "successor_execution": "READY_FOR_GOVERNED_START",
            "authority_basis": _gateway().bootstrap_agent_authority.authority_basis(owner_authority),
            "owner_confirmation": _gateway().bootstrap_agent_authority.authority_basis(owner_authority)
            == _gateway().bootstrap_agent_authority.BASIS_OWNER_GRANT,
            "owner_authority": owner_authority,
        }

    @staticmethod
    def _exact_hash(value: Any, field: str, length: int) -> str:
        text = _gateway()._text(value, field)
        pattern = rf"^[0-9a-f]{{{length}}}$"
        if not re.fullmatch(pattern, text):
            raise _gateway().GatewayInputError(f"{field} must be an exact lowercase Git hash")
        return text
    # fmt: on
