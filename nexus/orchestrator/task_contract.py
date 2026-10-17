from enum import Enum
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from typing import List, Optional, Dict, Any, Literal
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    computed_field,
    field_validator,
    model_validator,
)
import os

from nexus.contracts.collaboration_realm import CollaborationExecutionRealm


_EXACT_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_SAFE_TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class MutationMode(str, Enum):
    WORKING_TREE_ONLY = "WORKING_TREE_ONLY"


def _normalize_repository_path(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("path must be a non-empty repository-relative POSIX path")
    if "\\" in value:
        raise ValueError("path must be a repository-relative POSIX path")
    if value.startswith("/") or PurePosixPath(value).is_absolute():
        raise ValueError("path must be a repository-relative POSIX path")
    parts = value.split("/")
    if ".." in parts:
        raise ValueError("path traversal is not allowed")
    directory_prefix = value.endswith("/")
    raw_path = value[:-1] if directory_prefix else value
    if not raw_path or "." in raw_path.split("/") or "//" in value:
        raise ValueError("path must be normalized")
    normalized = PurePosixPath(raw_path).as_posix()
    if normalized != raw_path:
        raise ValueError("path must be normalized")
    return f"{normalized}/" if directory_prefix else normalized


class EvidenceRequirementMode(str, Enum):
    REQUIRED = "REQUIRED"
    CONDITIONALLY_REQUIRED = "CONDITIONALLY_REQUIRED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class EvidenceSubjectApplicability(str, Enum):
    APPLICABLE = "APPLICABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    UNRESOLVED = "UNRESOLVED"


# Bounds for the optional expected-evidence universe (§20-26, §55-57).
_MAX_EXPECTED_EVIDENCE_SUBJECTS = 256
_MAX_LOGICAL_SUBJECT_ID_CHARS = 512
_MAX_EVIDENCE_KIND_CHARS = 512


def _expected_evidence_universe_canonical_value(
    universe: Dict[str, Any],
) -> dict[str, Any]:
    """Return the canonical (sorted, normalized) value of an expected-evidence universe.

    Transport MUST project this value verbatim (sorted, no drops, no rewrites).
    """
    subjects = universe.get("subjects") or []
    return {
        "universe_generation": universe.get("universe_generation"),
        "subjects": [
            {
                "logical_subject_id": subject.get("logical_subject_id"),
                "evidence_kind": subject.get("evidence_kind"),
                "requirement_mode": subject.get("requirement_mode"),
                "applicability": subject.get("applicability"),
            }
            for subject in sorted(subjects, key=lambda s: str(s.get("logical_subject_id") or ""))
        ],
    }


def expected_evidence_universe_canonical_json(universe: Dict[str, Any]) -> str:
    return json.dumps(
        _expected_evidence_universe_canonical_value(universe),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def expected_evidence_universe_identity(universe: Dict[str, Any]) -> str:
    return "sha256:" + sha256(
        expected_evidence_universe_canonical_json(universe).encode("utf-8")
    ).hexdigest()


def _validate_logical_subject_id(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("logical_subject_id must be a string")
    stripped = value.strip()
    if not stripped:
        raise ValueError("logical_subject_id must be nonblank")
    if "\x00" in stripped:
        raise ValueError("logical_subject_id must not contain NUL")
    if len(stripped.encode("utf-8")) > _MAX_LOGICAL_SUBJECT_ID_CHARS:
        raise ValueError("logical_subject_id exceeds 512 chars")
    return stripped


def _validate_evidence_kind(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("evidence_kind must be a string")
    stripped = value.strip()
    if not stripped:
        raise ValueError("evidence_kind must be nonblank")
    if "\x00" in stripped:
        raise ValueError("evidence_kind must not contain NUL")
    if len(stripped.encode("utf-8")) > _MAX_EVIDENCE_KIND_CHARS:
        raise ValueError("evidence_kind exceeds 512 chars")
    return stripped


class ExpectedEvidenceSubject(BaseModel):
    """One declared member of the expected-evidence universe (producer-declared)."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    logical_subject_id: str
    evidence_kind: str
    requirement_mode: EvidenceRequirementMode
    applicability: EvidenceSubjectApplicability

    @field_validator("logical_subject_id")
    @classmethod
    def _validate_sid(cls, value: Any) -> str:
        return _validate_logical_subject_id(value)

    @field_validator("evidence_kind")
    @classmethod
    def _validate_kind(cls, value: Any) -> str:
        return _validate_evidence_kind(value)

    @model_validator(mode="after")
    def _validate_mode_applicability_consistency(self):
        mode = self.requirement_mode
        applicability = self.applicability
        if mode == EvidenceRequirementMode.REQUIRED and applicability != EvidenceSubjectApplicability.APPLICABLE:
            raise ValueError("REQUIRED requires APPLICABLE applicability")
        if mode == EvidenceRequirementMode.NOT_APPLICABLE and applicability != EvidenceSubjectApplicability.NOT_APPLICABLE:
            raise ValueError("NOT_APPLICABLE requires NOT_APPLICABLE applicability")
        # CONDITIONALLY_REQUIRED allows APPLICABLE | NOT_APPLICABLE | UNRESOLVED.
        return self


class ExpectedEvidenceUniverse(BaseModel):
    """Optional producer-declared expected-evidence universe (transport-opaque)."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    universe_generation: int = Field(ge=0, strict=True)
    subjects: List[ExpectedEvidenceSubject] = Field(min_length=1, max_length=_MAX_EXPECTED_EVIDENCE_SUBJECTS)

    @field_validator("universe_generation")
    @classmethod
    def _validate_generation(cls, value: Any) -> int:
        if type(value) is not int or isinstance(value, bool):
            raise ValueError("universe_generation must be an integer >= 0")
        if value < 0:
            raise ValueError("universe_generation must be an integer >= 0")
        return value

    @model_validator(mode="after")
    def _validate_no_duplicate_subjects(self):
        seen: set[str] = set()
        for subject in self.subjects:
            if subject.logical_subject_id in seen:
                raise ValueError(
                    f"duplicate logical_subject_id: {subject.logical_subject_id}"
                )
            seen.add(subject.logical_subject_id)
        # Canonicalization: keep subjects sorted by logical_subject_id.
        ordered = sorted(self.subjects, key=lambda s: s.logical_subject_id)
        object.__setattr__(self, "subjects", ordered)
        return self

    def canonical_json(self) -> str:
        return expected_evidence_universe_canonical_json(self.model_dump(mode="json"))

    @property
    def universe_identity(self) -> str:
        return expected_evidence_universe_identity(self.model_dump(mode="json"))


# A tracked task card declares its expected-evidence universe in exactly one
# fenced block with this info string. The card file is hashed as a whole
# (``task_card_hash``), so the declaration is bound by that hash; no worker or
# tool argument can supply or widen it (#2181).
TASK_CARD_EXPECTED_EVIDENCE_FENCE = "nexus-expected-evidence"


def parse_task_card_expected_evidence(text: str) -> Optional[Dict[str, Any]]:
    """Return the card-declared universe in canonical form, or None for legacy cards.

    Fails closed (ValueError) on a duplicated, unterminated or malformed block.
    """
    if not isinstance(text, str):
        raise ValueError("TASK_CARD_EXPECTED_EVIDENCE_INVALID: card text must be a string")
    lines = text.splitlines()
    opener = "```" + TASK_CARD_EXPECTED_EVIDENCE_FENCE
    fences = [
        index
        for index, line in enumerate(lines)
        if line.strip().startswith("```") and TASK_CARD_EXPECTED_EVIDENCE_FENCE in line
    ]
    starts = [index for index in fences if lines[index].strip() == opener]
    if fences != starts:
        # A near-miss fence must not silently drop a declared universe.
        raise ValueError("TASK_CARD_EXPECTED_EVIDENCE_INVALID: malformed fence")
    if not starts:
        return None
    if len(starts) != 1:
        raise ValueError("TASK_CARD_EXPECTED_EVIDENCE_INVALID: duplicate declaration")
    start = starts[0]
    end = next(
        (index for index in range(start + 1, len(lines)) if lines[index].strip() == "```"),
        None,
    )
    if end is None:
        raise ValueError("TASK_CARD_EXPECTED_EVIDENCE_INVALID: unterminated declaration")
    try:
        raw = json.loads("\n".join(lines[start + 1 : end]))
        universe = ExpectedEvidenceUniverse.model_validate(raw)
    except Exception as exc:
        raise ValueError(f"TASK_CARD_EXPECTED_EVIDENCE_INVALID: {exc}") from exc
    return universe.model_dump(mode="json")


# --- Issue behavior promises (#2532) ---------------------------------------
#
# An Issue declares its behavior promises in one fenced block in the Issue
# body with this info string. The Issue body is frozen by Core's existing
# issue_contract_hash, so an edited promise set reads as a changed contract.
ISSUE_PROMISE_SET_FENCE = "nexus.issue_promise_set.v1"
# A Task Card maps every promise of that set to declared expected-evidence
# subjects in one fenced block with this info string. Like the universe block
# it is covered by the card hash, so no worker or tool argument can change it.
TASK_CARD_ISSUE_PROMISES_FENCE = "nexus-issue-promises"

_MAX_ISSUE_PROMISES = 64
_PROMISE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9._-]{1,100}$")


class IssuePromisePhase(str, Enum):
    # Provable before merge by host-run verifier subjects.
    PRE_MERGE = "PRE_MERGE"
    # Provable only by a live witness after merge (#2453); never by a test.
    POST_MERGE = "POST_MERGE"


class IssuePromiseRisk(str, Enum):
    STANDARD = "STANDARD"
    # Needs both pre-merge evidence and a post-merge live witness (#2453).
    HIGH = "HIGH"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _validate_strict_generation(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field} must be an integer >= 0")
    return value


class IssuePromise(BaseModel):
    """One named behavior promise; the statement text stays in the Issue."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    promise_id: str
    statement_sha256: str
    phase: IssuePromisePhase
    risk: IssuePromiseRisk

    @field_validator("promise_id")
    @classmethod
    def _validate_promise_id(cls, value: Any) -> str:
        if not isinstance(value, str) or not _PROMISE_ID_RE.fullmatch(value):
            raise ValueError("promise_id must be a bounded slug")
        return value

    @field_validator("statement_sha256")
    @classmethod
    def _validate_statement_hash(cls, value: Any) -> str:
        if not isinstance(value, str) or not _SHA256_HEX_RE.fullmatch(value):
            raise ValueError("statement_sha256 must be a lowercase 64-hex SHA-256")
        return value


class IssuePromiseSet(BaseModel):
    """The promise set an Issue body declares (``nexus.issue_promise_set.v1``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    promise_set_generation: int
    promises: List[IssuePromise] = Field(min_length=1, max_length=_MAX_ISSUE_PROMISES)

    @field_validator("promise_set_generation", mode="before")
    @classmethod
    def _validate_generation(cls, value: Any) -> int:
        return _validate_strict_generation(value, "promise_set_generation")

    @model_validator(mode="after")
    def _validate_unique_sorted(self):
        ids = [promise.promise_id for promise in self.promises]
        duplicates = sorted({pid for pid in ids if ids.count(pid) > 1})
        if duplicates:
            raise ValueError(f"duplicate promise_id: {', '.join(duplicates)}")
        object.__setattr__(
            self, "promises", sorted(self.promises, key=lambda promise: promise.promise_id)
        )
        return self

    def canonical_json(self) -> str:
        return _canonical_json(self.model_dump(mode="json"))

    @property
    def identity(self) -> str:
        return "sha256:" + sha256(self.canonical_json().encode("utf-8")).hexdigest()


def issue_promise_set_identity(promise_set: Dict[str, Any]) -> str:
    """sha256 identity of one Issue promise set, over its canonical form."""
    return IssuePromiseSet.model_validate(promise_set).identity


class IssuePromiseSubjects(BaseModel):
    """The expected-evidence subjects one promise is proven by."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    promise_id: str
    subject_ids: List[str] = Field(min_length=1, max_length=_MAX_EXPECTED_EVIDENCE_SUBJECTS)

    @field_validator("subject_ids")
    @classmethod
    def _validate_subject_ids(cls, values: List[Any]) -> List[str]:
        normalized = [_validate_logical_subject_id(value) for value in values]
        if len(set(normalized)) != len(normalized):
            raise ValueError("duplicate subject_id")
        return sorted(normalized)


class IssuePromiseBinding(BaseModel):
    """A card's map from every Issue promise to expected-evidence subjects.

    The model checks the map covers exactly the Issue's promise set. Whether
    each subject is in the card's universe is checked where both are known
    (``nexus_task_card_create``). This grants no approval or closure.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    repository: str
    issue_number: int
    issue_contract_hash: str
    promise_set: IssuePromiseSet
    map: List[IssuePromiseSubjects] = Field(min_length=1, max_length=_MAX_ISSUE_PROMISES)

    @field_validator("repository")
    @classmethod
    def _validate_repository(cls, value: Any) -> str:
        if not isinstance(value, str) or not _REPOSITORY_RE.fullmatch(value):
            raise ValueError("repository must be owner/name")
        return value

    @field_validator("issue_number", mode="before")
    @classmethod
    def _validate_issue_number(cls, value: Any) -> int:
        if type(value) is not int or value < 1:
            raise ValueError("issue_number must be a positive integer")
        return value

    @field_validator("issue_contract_hash")
    @classmethod
    def _validate_contract_hash(cls, value: Any) -> str:
        if not isinstance(value, str) or not _SHA256_HEX_RE.fullmatch(value):
            raise ValueError("issue_contract_hash must be a lowercase 64-hex SHA-256")
        return value

    @model_validator(mode="after")
    def _validate_exact_promise_set(self):
        mapped = [entry.promise_id for entry in self.map]
        duplicates = sorted({pid for pid in mapped if mapped.count(pid) > 1})
        if duplicates:
            raise ValueError(f"duplicate promise_id in map: {', '.join(duplicates)}")
        declared = {promise.promise_id for promise in self.promise_set.promises}
        missing = sorted(declared - set(mapped))
        if missing:
            raise ValueError(f"promise not mapped to any subject: {', '.join(missing)}")
        extra = sorted(set(mapped) - declared)
        if extra:
            raise ValueError(f"promise not in the Issue promise set: {', '.join(extra)}")
        object.__setattr__(self, "map", sorted(self.map, key=lambda entry: entry.promise_id))
        return self

    def canonical_json(self) -> str:
        return _canonical_json(self.model_dump(mode="json"))

    @property
    def binding_identity(self) -> str:
        return "sha256:" + sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def subject_ids_for(self, promise_id: str) -> List[str]:
        for entry in self.map:
            if entry.promise_id == promise_id:
                return list(entry.subject_ids)
        return []


def _parse_single_json_fence(text: Any, fence: str, code: str) -> Optional[Any]:
    """The JSON body of exactly one ```<fence> block; None when there is none.

    Same rules as the expected-evidence block: a near-miss info string, a
    duplicate or an unterminated block fails closed.
    """
    if not isinstance(text, str):
        raise ValueError(f"{code}: text must be a string")
    lines = text.splitlines()
    opener = "```" + fence
    fences = [
        index
        for index, line in enumerate(lines)
        if line.strip().startswith("```") and fence in line
    ]
    starts = [index for index in fences if lines[index].strip() == opener]
    if fences != starts:
        raise ValueError(f"{code}: malformed fence")
    if not starts:
        return None
    if len(starts) != 1:
        raise ValueError(f"{code}: duplicate declaration")
    start = starts[0]
    end = next(
        (index for index in range(start + 1, len(lines)) if lines[index].strip() == "```"),
        None,
    )
    if end is None:
        raise ValueError(f"{code}: unterminated declaration")
    try:
        return json.loads("\n".join(lines[start + 1 : end]))
    except ValueError as exc:
        raise ValueError(f"{code}: {exc}") from exc


def parse_issue_promise_set(issue_body: str) -> Optional[Dict[str, Any]]:
    """The Issue body's promise set in canonical form, or None when it declares none."""
    code = "ISSUE_PROMISE_SET_INVALID"
    raw = _parse_single_json_fence(issue_body, ISSUE_PROMISE_SET_FENCE, code)
    if raw is None:
        return None
    try:
        return IssuePromiseSet.model_validate(raw).model_dump(mode="json")
    except ValueError as exc:
        raise ValueError(f"{code}: {exc}") from exc


def parse_task_card_issue_promises(text: str) -> Optional[Dict[str, Any]]:
    """The card's promise binding in canonical form, or None for cards without one."""
    code = "TASK_CARD_ISSUE_PROMISES_INVALID"
    raw = _parse_single_json_fence(text, TASK_CARD_ISSUE_PROMISES_FENCE, code)
    if raw is None:
        return None
    try:
        return IssuePromiseBinding.model_validate(raw).model_dump(mode="json")
    except ValueError as exc:
        raise ValueError(f"{code}: {exc}") from exc


class SelfHostedTaskContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    schema_: Literal["nexus.self_hosted_task_contract.v1"] = Field(
        default="nexus.self_hosted_task_contract.v1",
        alias="schema",
        serialization_alias="schema",
    )

    @property
    def schema(self) -> str:
        return self.schema_

    def model_dump(self, *args, **kwargs):
        kwargs.setdefault("by_alias", True)
        return super().model_dump(*args, **kwargs)

    def model_dump_json(self, *args, **kwargs):
        kwargs.setdefault("by_alias", True)
        return super().model_dump_json(*args, **kwargs)

    task_id: str
    objective: str
    controller_revision: str
    target_base_revision: str
    controller_repo_root: str
    target_repo_root: str
    target_worktree_root: str
    allowed_files: List[str]
    forbidden_files: List[str] = Field(default_factory=list)
    authorized_deletions: List[str] = Field(default_factory=list)
    verifier_commands: List[str] = Field(default_factory=list)
    protected_contracts: List[str] = Field(default_factory=list)
    preferred_provider: Optional[str] = None
    fallback_provider: Optional[str] = None
    provider_order: List[str] = Field(default_factory=list)
    maximum_provider_calls: int = Field(default=0, ge=0)
    maximum_replans: int = Field(default=0, ge=0)
    # Aggregate repair ceilings.  These are task-scoped (not attempt-scoped)
    # so retries/fallbacks cannot reset the budget.
    maximum_attempts_per_task: int = Field(default=1, ge=1)
    maximum_wall_time_seconds: float = Field(default=0.0, ge=0.0)
    maximum_changed_files: int = Field(default=0, ge=0)
    maximum_deleted_files: int = Field(default=0, ge=0)
    mutation_mode: MutationMode = MutationMode.WORKING_TREE_ONLY
    human_approval_required: bool = True
    collaboration_realm: Optional[CollaborationExecutionRealm] = None
    # Optional producer-declared expected-evidence universe (§20-26, §55-57).
    # Transport-opaque: transport MUST NOT author it; it only projects it.
    # Legacy contracts omit this field entirely and MUST parse/verify as before.
    expected_evidence: Optional[ExpectedEvidenceUniverse] = None

    @property
    def universe_identity(self) -> Optional[str]:
        """sha256 identity of the declared universe; None for legacy contracts."""
        if self.expected_evidence is None:
            return None
        return self.expected_evidence.universe_identity

    @field_validator("task_id")
    @classmethod
    def _validate_task_id(cls, value: str) -> str:
        if not _SAFE_TASK_ID_RE.fullmatch(value):
            raise ValueError("task_id must be a safe slug")
        return value

    @field_validator("objective")
    @classmethod
    def _validate_objective(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("objective must be non-empty")
        return value

    @field_validator("controller_revision", "target_base_revision")
    @classmethod
    def _validate_exact_revision(cls, value: str, info) -> str:
        if not _EXACT_GIT_SHA_RE.fullmatch(value):
            raise ValueError(f"{info.field_name} must be an exact 40-char lowercase Git SHA")
        return value

    @field_validator("allowed_files", "forbidden_files", "authorized_deletions")
    @classmethod
    def _validate_repository_paths(cls, values: List[str]) -> List[str]:
        return [_normalize_repository_path(value) for value in values]

    @model_validator(mode="after")
    def _validate_self_hosted_boundaries(self):
        if not self.allowed_files:
            raise ValueError("allowed_files must be non-empty")
        # Completion requires an applicable verifier (AGENTS.md): an empty
        # manifest (including the default) would otherwise verify vacuously.
        if not [c for c in self.verifier_commands if isinstance(c, str) and c.strip()]:
            raise ValueError("verifier_commands must be non-empty")
        forbidden = set(self.forbidden_files)
        for path in self.authorized_deletions:
            if path.endswith("/"):
                raise ValueError("authorized_deletions must contain exact file paths")
            allowed = any(
                path == boundary or (boundary.endswith("/") and path.startswith(boundary))
                for boundary in self.allowed_files
            )
            if not allowed:
                raise ValueError(f"authorized deletion is outside allowed_files: {path}")
            if any(
                path == boundary or (boundary.endswith("/") and path.startswith(boundary))
                for boundary in forbidden
            ):
                raise ValueError(f"authorized deletion is inside forbidden_files: {path}")
        if self.mutation_mode != MutationMode.WORKING_TREE_ONLY:
            raise ValueError("mutation_mode must be WORKING_TREE_ONLY")
        if not self.human_approval_required:
            raise ValueError("human approval is required")
        controller_root = Path(self.controller_repo_root).expanduser().resolve(strict=False)
        target_root = Path(self.target_repo_root).expanduser().resolve(strict=False)
        if controller_root == target_root:
            raise ValueError("controller and target roots must be physically separate")
        if self.collaboration_realm is not None:
            realm = self.collaboration_realm
            collaboration_root = Path(realm.collaboration.repo_root).resolve(strict=False)
            execution_root = Path(realm.execution_root).resolve(strict=False)
            control_plane_root = Path(realm.control_plane.repo_root).resolve(strict=False)
            target_worktree_root = Path(self.target_worktree_root).resolve(strict=False)
            if controller_root != collaboration_root:
                raise ValueError("collaboration realm repository root must be controller_repo_root")
            if target_worktree_root != execution_root:
                raise ValueError("collaboration realm execution root must be target_worktree_root")
            if target_root == execution_root or execution_root not in target_root.parents:
                raise ValueError("collaboration target must be below the collaboration execution root")
            if control_plane_root == controller_root:
                raise ValueError("control plane and collaboration repositories must be physically separate")
            if self.controller_revision != realm.collaboration.base.head_sha:
                raise ValueError("controller_revision must match the collaboration base SHA")
            if self.target_base_revision != realm.collaboration.base.head_sha:
                raise ValueError("target_base_revision must match the collaboration base SHA")
        if len(set(self.provider_order)) != len(self.provider_order):
            raise ValueError("provider_order must not contain duplicates")
        configured = {provider for provider in (self.preferred_provider, self.fallback_provider) if provider}
        if configured and not configured.issubset(set(self.provider_order or configured)):
            raise ValueError("provider_order must include preferred and fallback providers")
        self._validate_evidence_universe_coupling()
        return self

    def _required_verifier_id_set(self) -> set:
        """required_verifier_ids derivation — UNCHANGED authority (§21-22).

        The broader declared universe extends (never narrows) this set.
        """
        return set(self.verifier_commands or ())

    def _validate_evidence_universe_coupling(self) -> None:
        """Validate verifier authority coupling for the declared universe (§21-22).

        - required_verifier_ids derivation from verifier_commands is UNCHANGED.
        - New subjects extend the broader universe; they impose no narrowing.
        - If a subject logical_subject_id exactly equals a verifier id string,
          validate exact semantic equivalence: that verifier MUST be in the
          verifier_commands-derived set (exact string membership), and the
          subject must be REQUIRED/APPLICABLE (a verifier execution produces
          applicable evidence under its own id).
        - Namespaced ids (containing ':') impose no coupling: they are checked
          only for the mode/applicability consistency already enforced on the
          subject model itself.
        """
        universe = self.expected_evidence
        if universe is None:
            return
        verifier_ids = self._required_verifier_id_set()
        for subject in universe.subjects:
            sid = subject.logical_subject_id
            if ":" in sid:
                continue  # namespaced id: no coupling to verifier authority
            if sid in verifier_ids:
                if (
                    subject.requirement_mode != EvidenceRequirementMode.REQUIRED
                    or subject.applicability != EvidenceSubjectApplicability.APPLICABLE
                ):
                    raise ValueError(
                        f"subject {sid!r} equals a verifier id and must be REQUIRED/APPLICABLE"
                    )
                continue
            # Bare (non-namespaced) ids that are not verifier commands impose
            # no membership requirement — they extend the broader universe.

    @computed_field(return_type=str)
    @property
    def contract_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"contract_hash"})
        # Legacy preservation: contracts without a declared universe must hash
        # byte-identically to before the expected_evidence field existed.
        if payload.get("expected_evidence") is None:
            payload.pop("expected_evidence", None)
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return sha256(canonical).hexdigest()


def _non_empty_text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
    return value.strip()


class DevelopmentGoal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    what: str
    why: str

    @field_validator("what", "why")
    @classmethod
    def _validate_text(cls, value: str, info) -> str:
        return _non_empty_text(value, info.field_name)


class ArchitectureDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_id: str
    selected_option: str
    rationale: str
    rejected_alternatives: List[str] = Field(default_factory=list)

    @field_validator("decision_id")
    @classmethod
    def _validate_decision_id(cls, value: str) -> str:
        if not _SAFE_TASK_ID_RE.fullmatch(value):
            raise ValueError("decision_id must be a safe slug")
        return value

    @field_validator("selected_option", "rationale")
    @classmethod
    def _validate_text(cls, value: str, info) -> str:
        return _non_empty_text(value, info.field_name)

    @field_validator("rejected_alternatives")
    @classmethod
    def _validate_alternatives(cls, values: List[str]) -> List[str]:
        return [_non_empty_text(value, "rejected_alternatives") for value in values]


class AcceptanceProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    verifier_commands: List[str] = Field(default_factory=list)
    protected_contracts: List[str] = Field(default_factory=list)
    authorized_deletions: List[str] = Field(default_factory=list)
    required_evidence: List[str] = Field(default_factory=list)

    @field_validator("authorized_deletions")
    @classmethod
    def _validate_authorized_deletions(cls, values: List[str]) -> List[str]:
        return [_normalize_repository_path(value) for value in values]

    @field_validator("verifier_commands", "protected_contracts", "required_evidence")
    @classmethod
    def _validate_entries(cls, values: List[str], info) -> List[str]:
        return [_non_empty_text(value, info.field_name) for value in values]


class HumanApprovalPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision_approval_required: bool = True
    promotion_approval_required: bool = True
    approver_roles: List[str] = Field(default_factory=list)

    @field_validator("approver_roles")
    @classmethod
    def _validate_roles(cls, values: List[str]) -> List[str]:
        return [_non_empty_text(value, "approver_roles") for value in values]

    @model_validator(mode="after")
    def _require_approvals(self):
        if not self.decision_approval_required:
            raise ValueError("decision approval is required")
        if not self.promotion_approval_required:
            raise ValueError("promotion approval is required")
        if not self.approver_roles:
            raise ValueError("approver_roles must be non-empty")
        return self


class ArchitectTaskContract(SelfHostedTaskContract):
    """Versioned WHAT/WHY contract used to govern the self-hosted worker."""

    schema_: Literal["nexus.self_hosted_task_contract.v2"] = Field(
        default="nexus.self_hosted_task_contract.v2",
        alias="schema",
        serialization_alias="schema",
    )
    goal: DevelopmentGoal
    architecture_decisions: List[ArchitectureDecision]
    acceptance_profile: AcceptanceProfile
    human_approval_policy: HumanApprovalPolicy

    @model_validator(mode="after")
    def _validate_architect_boundaries(self):
        if not self.architecture_decisions:
            raise ValueError("architecture_decisions must be non-empty")
        if self.objective != self.goal.what:
            raise ValueError("objective must match goal.what")
        if self.acceptance_profile.verifier_commands != self.verifier_commands:
            raise ValueError("acceptance_profile.verifier_commands must match verifier_commands")
        if self.acceptance_profile.protected_contracts != self.protected_contracts:
            raise ValueError("acceptance_profile.protected_contracts must match protected_contracts")
        if self.acceptance_profile.authorized_deletions != self.authorized_deletions:
            raise ValueError("acceptance_profile.authorized_deletions must match authorized_deletions")
        if not self.human_approval_required:
            raise ValueError("human approval is required")
        return self


SelfHostedTaskContractV2 = ArchitectTaskContract

class TaskStatus(str, Enum):
    CREATED = "CREATED"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    INTEGRATED = "INTEGRATED"
    CLOSED = "CLOSED"
    
    # Failure states
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    CONFLICTED = "CONFLICTED"

class TaskStateTransition:
    ALLOWED_TRANSITIONS = {
        TaskStatus.CREATED: [TaskStatus.ASSIGNED, TaskStatus.BLOCKED, TaskStatus.CLOSED, TaskStatus.CONFLICTED, TaskStatus.FAILED],
        TaskStatus.ASSIGNED: [TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED, TaskStatus.CLOSED, TaskStatus.FAILED],
        TaskStatus.IN_PROGRESS: [TaskStatus.READY_FOR_REVIEW, TaskStatus.FAILED, TaskStatus.CONFLICTED, TaskStatus.BLOCKED, TaskStatus.CLOSED],
        TaskStatus.READY_FOR_REVIEW: [TaskStatus.INTEGRATED, TaskStatus.REJECTED, TaskStatus.FAILED, TaskStatus.CLOSED, TaskStatus.CONFLICTED],
        TaskStatus.INTEGRATED: [TaskStatus.CLOSED],
        TaskStatus.REJECTED: [TaskStatus.IN_PROGRESS, TaskStatus.CLOSED, TaskStatus.FAILED],
        TaskStatus.FAILED: [TaskStatus.IN_PROGRESS, TaskStatus.CLOSED],
        TaskStatus.CONFLICTED: [TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED, TaskStatus.CLOSED, TaskStatus.FAILED],
        TaskStatus.BLOCKED: [TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS, TaskStatus.CLOSED, TaskStatus.FAILED],
    }

    @classmethod
    def validate_transition(cls, current: TaskStatus, target: TaskStatus):
        if current == target:
            return
        if target not in cls.ALLOWED_TRANSITIONS.get(current, []):
            raise ValueError(f"Illegal state transition from {current} to {target}")


class EvidenceKind(str, Enum):
    PYTEST = "pytest"
    ACCEPTANCE_CHECK = "acceptance-check"
    DELIVERY_GATE = "delivery-gate"
    CODE_SCAN = "code-scan"
    CODE_IMPACT = "code-impact"
    HUMAN_APPROVAL = "human-approval"
    OTHER = "other"


class EvidenceRequirement(str, Enum):
    PYTEST = "pytest"
    ACCEPTANCE_CHECK = "acceptance-check"
    DELIVERY_GATE = "delivery-gate"
    CODE_SCAN = "code-scan"
    CODE_IMPACT = "code-impact"
    HUMAN_APPROVAL = "human-approval"


class DeliveryProfile(str, Enum):
    MOCK_ONLY = "mock_only"
    LIVE_BROWSER = "live_browser"
    LIVE_API = "live_api"


def normalize_requirement(
    requirement: str | EvidenceRequirement,
) -> str | EvidenceRequirement:
    if isinstance(requirement, EvidenceRequirement):
        return requirement
    text = str(requirement).strip().lower()
    if "pytest" in text:
        return EvidenceRequirement.PYTEST
    if "acceptance-check" in text:
        return EvidenceRequirement.ACCEPTANCE_CHECK
    if "delivery-gate" in text:
        return EvidenceRequirement.DELIVERY_GATE
    if "code-scan" in text or "code:scan" in text or "code scan" in text:
        return EvidenceRequirement.CODE_SCAN
    if "code-impact" in text or "code:impact" in text or "code impact" in text:
        return EvidenceRequirement.CODE_IMPACT
    if "human-approval" in text or "human approval" in text:
        return EvidenceRequirement.HUMAN_APPROVAL
    return text


def infer_evidence_kind(command: str) -> EvidenceKind:
    text = (command or "").strip().lower()
    if "delivery-gate" in text:
        return EvidenceKind.DELIVERY_GATE
    if "acceptance-check" in text:
        return EvidenceKind.ACCEPTANCE_CHECK
    if "code-scan" in text or "code:scan" in text or "code scan" in text:
        return EvidenceKind.CODE_SCAN
    if "code-impact" in text or "code:impact" in text or "code impact" in text:
        return EvidenceKind.CODE_IMPACT
    if "human-approval" in text or "human approval" in text:
        return EvidenceKind.HUMAN_APPROVAL
    if "pytest" in text:
        return EvidenceKind.PYTEST
    return EvidenceKind.OTHER

class Evidence(BaseModel):
    command: str
    exit_code: int
    output_summary: str
    artifact_path: Optional[str] = None
    kind: EvidenceKind = EvidenceKind.OTHER

    @model_validator(mode="after")
    def _infer_kind(self):
        if self.kind == EvidenceKind.OTHER:
            self.kind = infer_evidence_kind(self.command)
        return self

    def satisfies(self, requirement: str | EvidenceRequirement) -> bool:
        normalized = normalize_requirement(requirement)
        if isinstance(normalized, EvidenceRequirement):
            if normalized == EvidenceRequirement.PYTEST:
                return self.kind == EvidenceKind.PYTEST
            if normalized == EvidenceRequirement.ACCEPTANCE_CHECK:
                return self.kind in {EvidenceKind.ACCEPTANCE_CHECK, EvidenceKind.DELIVERY_GATE}
            if normalized == EvidenceRequirement.DELIVERY_GATE:
                return self.kind == EvidenceKind.DELIVERY_GATE
            if normalized == EvidenceRequirement.CODE_SCAN:
                return self.kind == EvidenceKind.CODE_SCAN
            if normalized == EvidenceRequirement.CODE_IMPACT:
                return self.kind == EvidenceKind.CODE_IMPACT
            if normalized == EvidenceRequirement.HUMAN_APPROVAL:
                return self.kind == EvidenceKind.HUMAN_APPROVAL
        return str(normalized) in self.command.lower()

class Task(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    task_id: str
    owner: str
    allowed_files: List[str]
    base_branch: str = "main"
    current_status: TaskStatus = TaskStatus.CREATED
    done_criteria: List[str]
    evidence_requirements: List[str | EvidenceRequirement]
    evidence_list: List[Evidence] = []
    branch_name: Optional[str] = None
    last_commit: Optional[str] = None
    working_dir: Optional[str] = None
    consulted_agents: List[str] = Field(default_factory=list)
    delivery_profile: DeliveryProfile = DeliveryProfile.MOCK_ONLY
    requires_proposal: bool = False
    proposal_ref: Optional[str] = None

    @field_validator("consulted_agents")
    @classmethod
    def check_consulted_agents_limit(cls, v: List[str]) -> List[str]:
        if len(v) > 2:
            raise ValueError("consulted_agents must contain at most 2 agents")
        return v

    @model_validator(mode="after")
    def check_workos_contract(self):
        if self.owner in self.consulted_agents:
            raise ValueError("owner cannot also be a consulted agent")
        if self.requires_proposal and not (self.proposal_ref or "").strip():
            raise ValueError("proposal_ref is required when requires_proposal is true")
        return self

    @field_validator("current_status")
    @classmethod
    def check_transition(cls, v: TaskStatus, info) -> TaskStatus:
        # info.data contains the validated fields so far. 
        # For validation on assignment, we need to compare with the current instance value.
        # But in field_validator, we don't have direct access to the old value easily without a hack.
        # However, for Pydantic V2 validate_assignment, this will be called.
        # We will implement a property setter or use a more robust transition method.
        return v

    def set_status(self, target: TaskStatus):
        TaskStateTransition.validate_transition(self.current_status, target)
        self.current_status = target

    def add_evidence(self, evidence: Evidence):
        self.evidence_list.append(evidence)

    @property
    def normalized_evidence_requirements(self) -> List[str | EvidenceRequirement]:
        return [normalize_requirement(req) for req in self.evidence_requirements]

    def missing_evidence_requirements(self) -> List[str | EvidenceRequirement]:
        missing: List[str | EvidenceRequirement] = []
        for requirement in self.normalized_evidence_requirements:
            if not any(evidence.satisfies(requirement) for evidence in self.evidence_list):
                missing.append(requirement)
        if (
            self.delivery_profile in {DeliveryProfile.LIVE_API, DeliveryProfile.LIVE_BROWSER}
            and EvidenceRequirement.HUMAN_APPROVAL not in missing
            and not any(evidence.satisfies(EvidenceRequirement.HUMAN_APPROVAL) for evidence in self.evidence_list)
        ):
            missing.append(EvidenceRequirement.HUMAN_APPROVAL)
        return missing

    def is_done_ready(self) -> bool:
        if not self.evidence_list:
            return False
        return not self.missing_evidence_requirements()

    def get_context_report(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "branch": self.branch_name,
            "commit": self.last_commit,
            "cwd": self.working_dir or os.getcwd(),
            "status": self.current_status
        }
# integrity-seal: 1776512137
