"""Per-promise confirmation report for #2453's independent confirmer (#2532 stage 3).

Pure logic over immutable inputs: the live Issue body, its edit history, its
comments (witness and confirmation blocks) and the listed PRs. It performs no
network or subprocess call. It grants nothing: no approve, merge, close or
label field exists; ``recommendation`` is text for the confirmer, and the
claim ceiling is ``PROMISE_CONFIRMATION_INPUT_ONLY``.

A promise is WITNESSED only by a witness comment that names the exact
promise-set identity, a listed PR, the statement's real entry and, for a
post-merge witness, a commit that contains every listed merge commit.
Independence of the confirmer is text-level only: all bot comments share one
GitHub login, so the confirmer string is compared with witness ``by`` values
and with the supplied author identities, which proves nothing cryptographic.

Optional ``entrypoints_touched`` (``nexus.entrypoints_touched.v1``, from
``scripts/governance/entrypoints_touched.py``, #2612) is advisory only: each
touched entry point that no statement ``entry`` names and that is not declared
out of scope adds ``ENTRYPOINT_UNCOVERED:<id>`` and makes the separate
``entrypoint_advisory_recommendation`` PROVISIONAL. It never changes
``recommendation`` (the VERIFIED rule belongs to #2453) and never blocks.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from hashlib import sha256
from typing import Any

from nexus.orchestrator.task_contract import (
    _parse_single_json_fence,
    issue_promise_set_identity,
    parse_issue_promise_set,
)

SCHEMA = "nexus.promise_confirmation_report.v1"
CLAIM_CEILING = "PROMISE_CONFIRMATION_INPUT_ONLY"
STATEMENTS_FENCE = "nexus.issue_promise_statements.v1"
SET_FENCE = "nexus.issue_promise_set.v1"

_STATEMENT_KEYS = ("promise_id", "statement", "observe", "entry", "counterexample")
_WITNESS_KEYS = frozenset(
    "promise_id promise_set_identity phase pr commit entry result observed_at by evidence".split()
)
_CONFIRM_KEYS = frozenset({"promise_set_identity", "commit", "confirmer", "promises"})
_CONFIRM_PROMISE_KEYS = frozenset({"promise_id", "verdict", "counterexample_checked", "note"})
_RESULTS = frozenset({"PASS", "ACTUAL_FAILED", "NOT_EXERCISED", "PARTIAL", "UNKNOWN_INFRA"})
_PHASES = ("PRE_MERGE", "POST_MERGE")
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_IDENT = re.compile(r"^sha256:[0-9a-f]{64}$")
_WITNESS_RE = re.compile(
    r"<!-- NEXUS_PROMISE_WITNESS_V1\s*\n(.*?)\nNEXUS_PROMISE_WITNESS_V1 -->", re.S
)
_CONFIRM_RE = re.compile(
    r"<!-- NEXUS_PROMISE_CONFIRMATION_V1\s*\n(.*?)\nNEXUS_PROMISE_CONFIRMATION_V1 -->", re.S
)
_STALE_REASONS = frozenset({
    "WITNESS_PROMISE_SET_MISMATCH",
    "WITNESS_PR_UNKNOWN",
    "WITNESS_COMMIT_NOT_LIVE_MERGE",
    "WITNESS_BEFORE_MERGE",
    "WITNESS_COMMIT_NOT_PR_HEAD",
})

Contains = Callable[[str, str], "bool | None"]

ENTRYPOINTS_SCHEMA = "nexus.entrypoints_touched.v1"
OUT_OF_SCOPE_FENCE = "nexus.entrypoints_out_of_scope.v1"
_ENTRY_ID = re.compile(r"^(gateway|script|launchd|console|workflow):[A-Za-z0-9_.*/@+-]{1,300}$")
_MAX_ENTRYPOINTS = 2000


def _canonical(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def statement_hash(statement: Mapping[str, Any]) -> str:
    return sha256(_canonical(dict(statement)).encode("utf-8")).hexdigest()


def _strict_loads(text: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        keys = [key for key, _ in items]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate key")
        return dict(items)

    def reject(token: str) -> Any:
        raise ValueError(f"non-finite number {token}")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=reject)


def _ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 2000


# --- authoring helpers ------------------------------------------------------


def emit_promise_blocks(
    statements: Sequence[Mapping[str, Any]],
    generation: int,
    phases_risks: Mapping[str, tuple[str, str]],
) -> str:
    """The two Issue fences (promise set + statements) with the hashes computed."""
    ordered = sorted((dict(s) for s in statements), key=lambda s: s["promise_id"])
    promises = [
        {
            "promise_id": s["promise_id"],
            "statement_sha256": statement_hash(s),
            "phase": phases_risks[s["promise_id"]][0],
            "risk": phases_risks[s["promise_id"]][1],
        }
        for s in ordered
    ]
    promise_set = {"promise_set_generation": generation, "promises": promises}
    return (
        f"```{SET_FENCE}\n{_canonical(promise_set)}\n```\n\n"
        f"```{STATEMENTS_FENCE}\n{_canonical({'statements': ordered})}\n```\n"
    )


def emit_witness_templates(
    statements: Sequence[Mapping[str, Any]],
    identity: str,
    phases_risks: Mapping[str, tuple[str, str]],
) -> str:
    """One witness comment template per promise; the author fills the <PLACEHOLDERS>."""
    blocks = []
    for s in sorted(statements, key=lambda s: s["promise_id"]):
        template = {
            "promise_id": s["promise_id"],
            "promise_set_identity": identity,
            "phase": phases_risks[s["promise_id"]][0],
            "pr": "<PR>",
            "commit": "<COMMIT>",
            "entry": s["entry"],
            "result": "<RESULT>",
            "observed_at": "<OBSERVED_AT>",
            "by": "<SESSION_NAME>",
            "evidence": "<EVIDENCE>",
        }
        blocks.append(
            f"<!-- NEXUS_PROMISE_WITNESS_V1\n{json.dumps(template)}\nNEXUS_PROMISE_WITNESS_V1 -->\n"
        )
    return "\n".join(blocks)


# --- parsing ----------------------------------------------------------------


def _parse_statements(body: str) -> dict[str, dict[str, str]]:
    raw = _parse_single_json_fence(body, STATEMENTS_FENCE, "PROMISE_STATEMENTS_INVALID")
    if raw is None:
        return {}
    items = raw.get("statements") if isinstance(raw, dict) and set(raw) == {"statements"} else None
    if not isinstance(items, list) or not items:
        raise ValueError("PROMISE_STATEMENTS_INVALID: statements must be a non-empty list")
    out: dict[str, dict[str, str]] = {}
    for item in items:
        if not isinstance(item, dict) or set(item) != set(_STATEMENT_KEYS):
            raise ValueError("PROMISE_STATEMENTS_INVALID: bad keys")
        if not all(_nonempty_str(item[key]) for key in _STATEMENT_KEYS):
            raise ValueError("PROMISE_STATEMENTS_INVALID: bad value")
        if item["promise_id"] in out:
            raise ValueError("PROMISE_STATEMENTS_INVALID: duplicate promise_id")
        out[item["promise_id"]] = item
    return out


_TRUSTED_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


def _blocks(
    comments: Sequence[Mapping[str, Any]],
    regex: re.Pattern[str],
    kind: str,
    trusted: frozenset[str],
    ignored: list[dict],
    now: datetime,
):
    """Yield (comment, block text) from trusted, unedited comments only."""
    for comment in comments:
        texts = regex.findall(str(comment.get("body", "")))
        if not texts:
            continue
        author = str(comment.get("author", ""))
        reason = None
        if (
            comment.get("author_association") not in _TRUSTED_ASSOCIATIONS
            and author.lower() not in trusted
        ):
            reason = "UNTRUSTED_COMMENT_AUTHOR"
        else:
            created, updated = _ts(comment.get("created_at")), _ts(comment.get("updated_at"))
            if created is None or updated is None:
                reason = "COMMENT_EDIT_STATE_UNKNOWN"
            elif created > now:
                reason = "FUTURE_COMMENT"
            elif updated > created:
                reason = "COMMENT_EDITED_AFTER_POSTING"
        for text in texts:
            if reason:
                ignored.append({
                    "kind": kind,
                    "author": author,
                    "created_at": comment.get("created_at"),
                    "reason": reason,
                })
            else:
                yield comment, text


def _parse_witness(text: str, now: datetime) -> dict[str, Any] | None:
    try:
        w = _strict_loads(text)
    except (ValueError, RecursionError):
        return None
    if not isinstance(w, dict) or set(w) != _WITNESS_KEYS:
        return None
    strings = ("promise_id", "entry", "observed_at", "by", "evidence")
    ok = (
        all(isinstance(w[k], str) and w[k].strip() for k in strings)
        and type(w["pr"]) is int
        and w["phase"] in _PHASES
        and w["result"] in _RESULTS
        and isinstance(w["commit"], str)
        and _SHA40.match(w["commit"])
        and isinstance(w["promise_set_identity"], str)
        and _IDENT.match(w["promise_set_identity"])
    )
    observed = _ts(w["observed_at"])
    if not ok or observed is None or observed > now:
        return None
    return {**w, "by": w["by"].strip()}


def _parse_confirmation(text: str) -> dict[str, Any] | None:
    try:
        c = _strict_loads(text)
    except (ValueError, RecursionError):
        return None
    if not isinstance(c, dict) or set(c) != _CONFIRM_KEYS or not isinstance(c["promises"], list):
        return None
    if not (isinstance(c["confirmer"], str) and c["confirmer"].strip()):
        return None
    c = {**c, "confirmer": c["confirmer"].strip()}
    if not (isinstance(c["commit"], str) and _SHA40.match(c["commit"])):
        return None
    if not (isinstance(c["promise_set_identity"], str) and _IDENT.match(c["promise_set_identity"])):
        return None
    for p in c["promises"]:
        if not isinstance(p, dict) or set(p) != _CONFIRM_PROMISE_KEYS:
            return None
        if p["verdict"] not in ("ACCEPT", "REJECT", "UNVERIFIED"):
            return None
        if type(p["counterexample_checked"]) is not bool or not isinstance(p["promise_id"], str):
            return None
    return c


# --- evaluation -------------------------------------------------------------


def _live_for_all(prs: Sequence[Mapping[str, Any]], commit: str, contains: Contains) -> bool:
    merged = [p["merge_sha"] for p in prs if p.get("merge_sha")]
    return bool(merged) and all(contains(sha, commit) is True for sha in merged)


def _judge_witness(w, *, promise_set, identity, statements, prs, contains) -> str | None:
    """First failing reason for one witness, or None when it is valid."""
    promise_id = w["promise_id"]
    if promise_id not in {p["promise_id"] for p in promise_set["promises"]}:
        return "WITNESS_UNKNOWN_PROMISE"
    if w["promise_set_identity"] != identity:
        return "WITNESS_PROMISE_SET_MISMATCH"
    listed = next((p for p in prs if p["number"] == w["pr"]), None)
    if listed is None:
        return "WITNESS_PR_UNKNOWN"
    if w["phase"] == "POST_MERGE":
        if not (listed.get("merge_sha") and listed.get("merged_at")):
            return "WITNESS_COMMIT_NOT_LIVE_MERGE"
        if not _live_for_all(prs, w["commit"], contains):
            return "WITNESS_COMMIT_NOT_LIVE_MERGE"
        if _ts(w["observed_at"]) < _ts(listed["merged_at"]):  # type: ignore[operator]
            return "WITNESS_BEFORE_MERGE"
    elif w["commit"] != listed.get("head_sha"):
        return "WITNESS_COMMIT_NOT_PR_HEAD"
    statement = statements.get(promise_id)
    if statement is None or w["entry"] != statement["entry"]:
        return "WITNESS_ENTRY_MISMATCH"
    return None


def _failure_counts(
    w: Mapping[str, Any], prs: Sequence[Mapping[str, Any]], contains: Contains
) -> bool:
    """Whether an ACTUAL_FAILED witness still counts as a failure."""
    if w["result"] != "ACTUAL_FAILED":
        return False
    if w["valid"]:
        return True
    reason = w["reason"]
    if w["phase"] != "POST_MERGE":
        return reason == "WITNESS_PROMISE_SET_MISMATCH"
    if reason not in ("WITNESS_PROMISE_SET_MISMATCH", "WITNESS_COMMIT_NOT_LIVE_MERGE"):
        return False
    own = next((p for p in prs if p["number"] == w["pr"]), None)
    return bool(own and own.get("merge_sha") and contains(own["merge_sha"], w["commit"]) is True)


def _superseding_fix(failure, valid, prs, contains) -> int | None:
    """PR number of a merged fix that a later valid PASS (same phase) contains, else None."""
    failed_at = _ts(failure["observed_at"])
    if failed_at is None:
        return None
    for ok in valid:
        if ok["result"] != "PASS" or ok["phase"] != failure["phase"]:
            continue
        passed_at = _ts(ok["observed_at"])
        if passed_at is None or passed_at <= failed_at:
            continue
        for p in prs:
            merged = _ts(p.get("merged_at")) if p.get("merged_at") else None
            if (
                merged
                and merged > failed_at
                and p.get("merge_sha")
                and contains(p["merge_sha"], ok["commit"]) is True
            ):  # type: ignore[operator]
                return p["number"]
    return None


def _required_phases(phase: str, risk: str) -> set[str]:
    return (
        {"PRE_MERGE", "POST_MERGE"}
        if risk == "HIGH"
        else {"POST_MERGE"}
        if phase == "POST_MERGE"
        else {"ANY"}
    )


def _satisfied(required: set[str], passed: set[str]) -> bool:
    return bool(passed) if required == {"ANY"} else required <= passed


def _predeclaration(
    history, start: datetime | None, current_set, current_identity, issue_created_at=None
) -> tuple[set[str], set[str]]:
    """(reasons to report, reasons that block VERIFIED); dropped ids use BLOCKED prefix."""
    unavailable = {"PROMISE_HISTORY_UNAVAILABLE"}
    created = _ts(issue_created_at) if issue_created_at is not None else None
    if start is None or (issue_created_at is not None and created is None):
        return unavailable, unavailable
    if created is not None and created > start:
        return {"PROMISE_SET_NOT_PREDECLARED"}, {"PROMISE_SET_NOT_PREDECLARED"}
    if history is None:
        return {"PROMISE_HISTORY_UNAVAILABLE"}, {"PROMISE_HISTORY_UNAVAILABLE"}
    if not history:
        # Never edited: the current body is the original, but only the Issue's
        # creation time proves it predates the work.
        if created is None:
            return {"PROMISE_HISTORY_UNAVAILABLE"}, {"PROMISE_HISTORY_UNAVAILABLE"}
        return set(), set()
    stamped = [(_ts(h.get("edited_at")), h) for h in history]
    if any(ts is None for ts, _ in stamped):
        # An unreadable timestamp cannot prove what was declared before work began.
        return {"PROMISE_HISTORY_UNAVAILABLE"}, {"PROMISE_HISTORY_UNAVAILABLE"}
    versions = [h for ts, h in sorted(stamped, key=lambda item: item[0]) if ts <= start]  # type: ignore[operator]
    old_set = None
    if versions:
        try:
            old_set = parse_issue_promise_set(versions[-1]["body"])
        except ValueError:
            old_set = None
    if old_set is None:
        return {"PROMISE_SET_NOT_PREDECLARED"}, {"PROMISE_SET_NOT_PREDECLARED"}
    dropped = {p["promise_id"] for p in old_set["promises"]} - {
        p["promise_id"] for p in current_set["promises"]
    }
    if dropped:
        reasons = {f"PROMISE_DROPPED_AFTER_WORK_START:{pid}" for pid in dropped}
        return reasons, reasons
    if issue_promise_set_identity(old_set) != current_identity:
        reason = {"PROMISE_SET_CHANGED_AFTER_WORK_START"}
        return reason, reason
    return set(), set()


def _confirmation(
    comments, identity, prs, contains, trusted, blocks_ignored, now
) -> tuple[dict | None, list[dict]]:
    ignored: list[dict] = []
    candidates: list[tuple[datetime, dict]] = []
    for comment, text in _blocks(
        comments, _CONFIRM_RE, "CONFIRMATION", trusted, blocks_ignored, now
    ):
        parsed = _parse_confirmation(text)
        created = _ts(comment.get("created_at"))
        if parsed is None or created is None:
            ignored.append({
                "created_at": comment.get("created_at"),
                "reason": "CONFIRMATION_MALFORMED",
            })
        elif parsed["promise_set_identity"] != identity:
            ignored.append({
                "created_at": comment.get("created_at"),
                "reason": "CONFIRMATION_PROMISE_SET_MISMATCH",
            })
        elif not _live_for_all(prs, parsed["commit"], contains):
            ignored.append({
                "created_at": comment.get("created_at"),
                "reason": "CONFIRMATION_COMMIT_NOT_LIVE_MERGE",
            })
        else:
            candidates.append((created, {**parsed, "_author": str(comment.get("author", ""))}))
    candidates.sort(key=lambda item: item[0])
    for created, _ in candidates[:-1]:
        ignored.append({"created_at": created.isoformat(), "reason": "CONFIRMATION_SUPERSEDED"})
    return (candidates[-1][1] if candidates else None), ignored


def _pr_key(value: Any) -> int | None:
    """A PR number as int; accepts int or an ASCII digit string, nothing else."""
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,9}", value):
        return int(value)
    return None


def _marker_names(value: Any) -> set[str]:
    """Usable lowercase names from one PR's marker value; anything odd yields none."""
    items = [value] if isinstance(value, str) else value if isinstance(value, (list, tuple)) else []
    return {x.strip().lower() for x in items if isinstance(x, str) and x.strip()}


def _pr_markers(raw: Mapping[Any, Any] | None) -> dict[int, set[str]]:
    """PR number -> marker names; bad keys ignored, the first entry for a number wins."""
    out: dict[int, set[str]] = {}
    for key, value in (raw if isinstance(raw, Mapping) else {}).items():
        number = _pr_key(key)
        if number is not None:
            out.setdefault(number, _marker_names(value))
    return out


def _normalize_pr(p: Mapping[str, Any]) -> dict[str, Any]:
    """A PR with an unreadable merged_at (or no merge pair) counts as not merged."""
    out = dict(p)
    out["number"] = _pr_key(out.get("number"))
    if not (out.get("merge_sha") and _ts(out.get("merged_at"))):
        out["merge_sha"], out["merged_at"] = None, None
    return out


def _work_start(
    prs: Sequence[Mapping[str, Any]], linked_pr_created_at: Sequence[str] | None
) -> datetime | None:
    """Earliest creation among the listed and all Issue-linked PRs; None when unknown."""
    if linked_pr_created_at is None:
        return None
    stamps = [_ts(p.get("created_at")) for p in prs] + [_ts(t) for t in linked_pr_created_at]
    if not stamps or any(t is None for t in stamps):
        return None
    return min(t for t in stamps if t is not None)


# --- entry points (advisory, #2612) -----------------------------------------


def _entrypoint_ids(raw: Any) -> list[str] | None:
    """Sorted unique ids from a ``nexus.entrypoints_touched.v1`` document; None if invalid."""
    if not isinstance(raw, Mapping) or raw.get("schema") != ENTRYPOINTS_SCHEMA:
        return None
    items = raw.get("entrypoints")
    if not isinstance(items, list) or len(items) > _MAX_ENTRYPOINTS:
        return None
    ids = set()
    for item in items:
        eid = item.get("id") if isinstance(item, Mapping) else None
        if not isinstance(eid, str) or not _ENTRY_ID.match(eid):
            return None
        ids.add(eid)
    return sorted(ids)


def _out_of_scope_items(raw: Any) -> dict[str, str] | None:
    """id -> reason from a list of {"id", "reason"}; None when anything is malformed."""
    if not isinstance(raw, list) or len(raw) > _MAX_ENTRYPOINTS:
        return None
    out: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, Mapping) or set(item) != {"id", "reason"}:
            return None
        eid, why = item["id"], item["reason"]
        if not (isinstance(eid, str) and _ENTRY_ID.match(eid) and _nonempty_str(why)):
            return None
        out.setdefault(eid, why.strip())
    return out


def _declared_out_of_scope(issue_body: str, touched: Mapping[str, Any]) -> tuple[dict, set]:
    """Out-of-scope declarations from the Issue fence and the input document."""
    reasons: set[str] = set()
    declared: dict[str, str] = {}
    try:
        fence = _parse_single_json_fence(issue_body, OUT_OF_SCOPE_FENCE, "OUT_OF_SCOPE_INVALID")
    except ValueError:
        fence, reasons = None, {"ENTRYPOINT_OUT_OF_SCOPE_INVALID"}
    sources = []
    if fence is not None:
        ok = isinstance(fence, dict) and set(fence) == {"out_of_scope"}
        sources.append(fence["out_of_scope"] if ok else None)
    if "out_of_scope" in touched:
        sources.append(touched["out_of_scope"])
    for source in sources:
        parsed = _out_of_scope_items(source)
        if parsed is None:
            reasons.add("ENTRYPOINT_OUT_OF_SCOPE_INVALID")
            continue
        for eid, why in parsed.items():
            declared.setdefault(eid, why)
    return declared, reasons


def _bounded(token: str, text: str, word: str) -> bool:
    return re.search(rf"(?<![{word}]){re.escape(token)}(?![{word}])", text) is not None


_NAME_CHARS = {
    "gateway": "A-Za-z0-9_",
    "script": "A-Za-z0-9_./-",
    "workflow": "A-Za-z0-9_./-",
    "launchd": "A-Za-z0-9_.-",
    "console": "A-Za-z0-9_.-",
}


def _entry_named(eid: str, entries: Sequence[str]) -> bool:
    """Whether a statement entry names this entry point (bounded, so a prefix never counts).

    The full id always counts; a gateway tool name, script or workflow path
    (or workflow file name) and a launchd label count on their own. The
    console id must be written in full, since ``nexus`` alone is too common.
    """
    kind, _, name = eid.partition(":")
    word = _NAME_CHARS.get(kind, "A-Za-z0-9_")
    tokens = [eid]
    if kind == "gateway" and name != "*":
        tokens.append(name)
    elif kind in ("script", "launchd"):
        tokens.append(name)
    elif kind == "workflow":
        tokens += [name, name.rsplit("/", 1)[-1]]
    return any(_bounded(token, text, word) for text in entries for token in tokens)


def _entrypoint_advisory(
    raw: Any, issue_body: str, statements: Mapping[str, Mapping[str, str]]
) -> tuple[dict[str, Any], set[str]]:
    """(report section, top-level advisory reasons). Never a blocker."""
    ids = _entrypoint_ids(raw)
    if ids is None:
        return {"valid": False, "touched": [], "uncovered": []}, {"ENTRYPOINTS_TOUCHED_INVALID"}
    declared, reasons = _declared_out_of_scope(issue_body, raw)
    entries = [s["entry"] for s in statements.values()]
    named = {eid for eid in ids if _entry_named(eid, entries)}
    if "gateway:*" in ids and any(e.startswith("gateway:") and e != "gateway:*" for e in named):
        named.add("gateway:*")
    out_of_scope = [
        {"id": eid, "reason": declared[eid]} for eid in ids if eid in declared and eid not in named
    ]
    skipped = {item["id"] for item in out_of_scope}
    uncovered = [eid for eid in ids if eid not in named and eid not in skipped]
    reasons |= {f"ENTRYPOINT_UNCOVERED:{eid}" for eid in uncovered}
    return {
        "valid": True,
        "touched": ids,
        "covered": sorted(named),
        "out_of_scope": out_of_scope,
        "uncovered": uncovered,
    }, reasons


def build_promise_confirmation_report(
    *,
    issue_body: str,
    body_history: Sequence[Mapping[str, Any]] | None,
    comments: Sequence[Mapping[str, Any]],
    prs: Sequence[Mapping[str, Any]],
    contains: Contains,
    now: str,
    author_identities: Sequence[str],
    trusted_logins: Sequence[str] = (),
    issue_created_at: str | None = None,
    shared_logins: Sequence[str] = (),
    author_sessions: Sequence[str] | None = (),
    pr_author_sessions: Mapping[int, Sequence[str]] | None = None,
    linked_pr_created_at: Sequence[str] | None = None,
    entrypoints_touched: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    base = {"schema": SCHEMA, "claim_ceiling": CLAIM_CEILING}
    try:
        promise_set = parse_issue_promise_set(issue_body)
    except ValueError as exc:
        return {
            **base,
            "applicable": True,
            "recommendation": "BLOCKED",
            "reason_codes": ["PROMISE_SET_INVALID"],
            "detail": str(exc),
        }
    if promise_set is None:
        return {**base, "applicable": False, "recommendation": "NOT_APPLICABLE"}
    try:
        statements = _parse_statements(issue_body)
    except ValueError as exc:
        return {
            **base,
            "applicable": True,
            "recommendation": "BLOCKED",
            "reason_codes": ["PROMISE_STATEMENTS_INVALID"],
            "detail": str(exc),
        }
    identity = issue_promise_set_identity(promise_set)
    now_dt = _ts(now)
    if now_dt is None:
        raise ValueError("now must be RFC3339 UTC ending in Z")
    prs = [_normalize_pr(p) for p in prs]
    declared = {p["promise_id"]: p for p in promise_set["promises"]}

    witnesses: dict[str, list[dict]] = {pid: [] for pid in declared}
    malformed = unknown = 0
    trusted = frozenset(t.lower() for t in trusted_logins)
    ignored_blocks: list[dict] = []
    all_by: set[str] = set()
    for _, text in _blocks(comments, _WITNESS_RE, "WITNESS", trusted, ignored_blocks, now_dt):
        w = _parse_witness(text, now_dt)
        if w is None:
            malformed += 1
            continue
        all_by.add(w["by"].lower())
        reason = _judge_witness(
            w,
            promise_set=promise_set,
            identity=identity,
            statements=statements,
            prs=prs,
            contains=contains,
        )
        if reason == "WITNESS_UNKNOWN_PROMISE":
            unknown += 1
            continue
        witnesses[w["promise_id"]].append({**w, "valid": reason is None, "reason": reason})

    confirmation, ignored = _confirmation(
        comments, identity, prs, contains, trusted, ignored_blocks, now_dt
    )
    authors = {a.strip().lower() for a in author_identities}
    shared = {x.strip().lower() for x in shared_logins}
    sessions = {x.strip().lower() for x in (author_sessions or ()) if x.strip()}
    pr_marked = _pr_markers(pr_author_sessions)
    excluded = sessions.union(*pr_marked.values())
    verdicts = {p["promise_id"]: p for p in confirmation["promises"]} if confirmation else {}

    rows = []
    for pid, promise in declared.items():
        ws, reasons = witnesses[pid], set()
        statement = statements.get(pid)
        valid = [w for w in ws if w["valid"]]
        reasons |= {w["reason"] for w in ws if w["reason"]}
        passed = {w["phase"] for w in valid if w["result"] == "PASS"}
        required = _required_phases(promise["phase"], promise["risk"])
        live_failures = []
        # A failure whose only defect is an older promise-set identity still counts.
        failing = [w for w in ws if _failure_counts(w, prs, contains)]
        for failure in failing:
            fix = _superseding_fix(failure, valid, prs, contains)
            if fix is None:
                live_failures.append(failure)
            else:
                reasons.add(f"FAILURE_SUPERSEDED_BY_FIX:{fix}")
        if statement is None:
            reasons.add("PROMISE_STATEMENT_MISSING")
        elif statement_hash(statement) != promise["statement_sha256"]:
            reasons.add("PROMISE_STATEMENT_MISMATCH")
        if "PROMISE_STATEMENT_MISMATCH" in reasons:
            status = "STALE"
        elif live_failures:
            status = "FAILED"
        elif statement is not None and _satisfied(required, passed):
            status = "WITNESSED"
        elif ws and all(w["reason"] in _STALE_REASONS for w in ws):
            status = "STALE"
        else:
            status = "UNCOVERED"
            if passed and not _satisfied(required, passed):
                reasons.add("WITNESS_PHASE_INSUFFICIENT")
        verdict = None
        if confirmation is not None and pid in verdicts:
            v = verdicts[pid]
            who = confirmation["confirmer"].lower()
            login = confirmation["_author"].lower()
            independent = (
                who not in all_by
                and who not in authors
                and who not in excluded
                and (login in shared or login not in authors)
            )
            if not independent:
                reasons.add("CONFIRMER_NOT_INDEPENDENT")
            verdict = {
                "verdict": v["verdict"],
                "counterexample_checked": v["counterexample_checked"],
                "confirmer": confirmation["confirmer"],
                "ignored": not independent,
            }
        rows.append({
            "promise_id": pid,
            "phase": promise["phase"],
            "risk": promise["risk"],
            "status": status,
            "reason_codes": sorted(reasons),
            "witnesses": [
                {
                    k: w[k]
                    for k in ("commit", "phase", "result", "by", "observed_at", "valid", "reason")
                }
                for w in ws
            ],
            "confirmer_verdict": verdict,
        })

    info, blockers = _predeclaration(
        None if body_history is None else list(body_history),
        _work_start(prs, linked_pr_created_at),
        promise_set,
        identity,
        issue_created_at,
    )
    top: set[str] = set(info)
    if not excluded:
        top.add("AUTHOR_SESSION_UNKNOWN")
        blockers = set(blockers) | {"AUTHOR_SESSION_UNKNOWN"}
    numbers = [p["number"] for p in prs]
    for duplicate in sorted({n for n in numbers if n is not None and numbers.count(n) > 1}):
        top.add(f"DUPLICATE_PR_LISTED:{duplicate}")
    for number in numbers:
        if number is None or not pr_marked.get(number):
            reason = f"PR_AUTHOR_SESSION_MISSING:{'?' if number is None else number}"
            top.add(reason)
            blockers = set(blockers) | {reason}
    if not prs:
        top.add("NO_PR_LISTED")
    if any(not p.get("merge_sha") for p in prs):
        top.add("PR_NOT_MERGED")
    if unknown:
        top.add("WITNESS_UNKNOWN_PROMISE")

    def accepted(row: dict) -> bool:
        v = row["confirmer_verdict"]
        return bool(
            v and not v["ignored"] and v["verdict"] == "ACCEPT" and v["counterexample_checked"]
        )

    uncovered = [r["promise_id"] for r in rows if not (r["status"] == "WITNESSED" and accepted(r))]
    rejected = any(
        r["confirmer_verdict"]
        and not r["confirmer_verdict"]["ignored"]
        and r["confirmer_verdict"]["verdict"] == "REJECT"
        for r in rows
    )
    if (
        any(r.startswith("PROMISE_DROPPED") for r in info)
        or {"NO_PR_LISTED", "PR_NOT_MERGED"} & top
        or any(r.startswith("DUPLICATE_PR_LISTED") for r in top)
    ):
        recommendation = "BLOCKED"
    elif rejected or any(r["status"] == "FAILED" for r in rows):
        recommendation = "LIVE_FAILED"
    elif not uncovered and not blockers:
        recommendation = "VERIFIED"
    else:
        recommendation = "PROVISIONAL"
    count = lambda s: sum(r["status"] == s for r in rows)  # noqa: E731
    extra: dict[str, Any] = {}
    if entrypoints_touched is not None:
        # Advisory only: computed after ``recommendation`` and never feeds it.
        section, advisory = _entrypoint_advisory(entrypoints_touched, issue_body, statements)
        top |= advisory
        extra = {
            "entrypoints": section,
            "entrypoint_advisory_recommendation": (
                "PROVISIONAL"
                if recommendation == "VERIFIED" and (section["uncovered"] or advisory)
                else recommendation
            ),
        }
    return {
        **base,
        "applicable": True,
        "promise_set_identity": identity,
        "recommendation": recommendation,
        "reason_codes": sorted(top),
        "promises": rows,
        "uncovered": uncovered if recommendation == "PROVISIONAL" else [],
        "promises_total": len(rows),
        "witnessed": count("WITNESSED"),
        "uncovered_count": count("UNCOVERED"),
        "failed": count("FAILED"),
        "stale": count("STALE"),
        "malformed_witnesses": malformed,
        "ignored_confirmations": ignored,
        "ignored_blocks": ignored_blocks,
        **extra,
    }
