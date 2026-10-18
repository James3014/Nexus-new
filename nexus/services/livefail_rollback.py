"""Fast stop-the-bleeding after an independent LIVE_FAILED verdict (#2532, #2453).

Pure logic over immutable inputs, no network or subprocess.  Two things live here:

* ``evaluate_trigger`` decides whether an Issue carries an *independent* LIVE_FAILED
  verdict.  Only two sources count:
    A. a strict ``NEXUS_LIVE_FAILED_V1`` block in a trusted, unedited comment whose
       ``confirmer`` is not an author of the origin PR (the #2453 pilot path); or
    B. a promise-confirmation report (#2595) whose recommendation is LIVE_FAILED
       and where an independent (not ignored) confirmer verdict covers a FAILED
       promise or says REJECT.
  An author's own failure witness, a bare ``nexus:live-failed`` label or any
  untrusted comment never triggers anything.
* ``gateway_hold_plan`` / ``hold_text`` / ``release_allowed`` encode the deployer
  owner's conditions (workspace-86, 2026-10-18) for holding the auto-deployer
  while a failed merge is not yet live.

The result grants nothing: a trigger only lets the CLI open a *draft* revert PR
that still needs an independent review and green required checks to merge.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any

SCHEMA = "nexus.livefail_rollback.v1"
LIVE_FAILED_LABEL = "nexus:live-failed"
HOLD_PREFIX = "livefail-rollback:"
HOLD_MAX_AGE = timedelta(hours=6)
# Deployer states in which nothing is mid-switch (workspace-86: IN_SYNC / waiting /
# deferred).  Anything else (ERROR, HOLD, BACKOFF, journal pending...) means no hold.
HOLDABLE_STATUSES = frozenset({
    "IN_SYNC",
    "DEPLOYED",
    "CHECKS_PENDING",
    "DEBOUNCED",
    "SKIPPED_IRRELEVANT",
    "DEFERRED_TASKS_IN_FLIGHT",
    "DEFERRED_CONTROLLER_MOVED",
})
GATEWAY_SURFACES = frozenset({"gateway", "deployer"})
IRRELEVANT_PREFIXES = ("tasks/", "docs/", "tests/", ".github/", "archives/", "artifacts/")

_BLOCK_RE = re.compile(r"<!-- NEXUS_LIVE_FAILED_V1\s*\n(.*?)\nNEXUS_LIVE_FAILED_V1 -->", re.S)
_WITNESS_DECL_RE = re.compile(
    r"<!-- NEXUS_LIVE_WITNESS_V1\s*\n(.*?)\nNEXUS_LIVE_WITNESS_V1 -->", re.S
)
_BLOCK_KEYS = frozenset({"origin_pr", "merge_sha", "live_commit", "confirmer", "witness", "reason"})
_SHA40 = re.compile(r"^[0-9a-f]{40}$")
_TRUSTED_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
# "session" or "session/role": one or two plain segments, nothing else (no leading
# or trailing slash, backslash, spaces), so every segment can be compared.
_CONFIRMER_RE = re.compile(r"^[A-Za-z0-9._\[\]-]{1,64}(/[A-Za-z0-9._\[\]-]{1,64})?$")

Contains = Callable[[str, str], "bool | None"]


def _ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None


def _strict_loads(text: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        keys = [k for k, _ in items]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate key")
        return dict(items)

    def reject(token: str) -> Any:
        raise ValueError(token)

    return json.loads(text, object_pairs_hook=pairs, parse_constant=reject)


def _text(value: Any, limit: int = 2000) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit


def parse_block(text: str) -> dict[str, Any] | None:
    try:
        b = _strict_loads(text)
    except (ValueError, RecursionError):
        return None
    if not isinstance(b, dict) or set(b) != _BLOCK_KEYS:
        return None
    if type(b["origin_pr"]) is not int or b["origin_pr"] <= 0:
        return None
    if not all(isinstance(b[k], str) and _SHA40.match(b[k]) for k in ("merge_sha", "live_commit")):
        return None
    if not all(_text(b[k]) for k in ("confirmer", "witness", "reason")):
        return None
    if not _CONFIRMER_RE.match(b["confirmer"]):
        return None
    return {**b, "confirmer": b["confirmer"].strip()}


def witness_declaration(pr_body: str) -> dict[str, Any] | None:
    """The PR's NEXUS_LIVE_WITNESS_V1 declaration (surface etc.), or None."""
    found = _WITNESS_DECL_RE.findall(pr_body or "")
    if len(found) != 1:
        return None
    try:
        data = _strict_loads(found[0])
    except (ValueError, RecursionError):
        return None
    return data if isinstance(data, dict) else None


def _comment_trust(
    comment: Mapping[str, Any], trusted: frozenset[str], now: datetime
) -> str | None:
    """None when the comment may carry a verdict, else the reason it may not."""
    author = str(comment.get("author", "")).lower()
    if comment.get("author_association") not in _TRUSTED_ASSOCIATIONS and author not in trusted:
        return "UNTRUSTED_COMMENT_AUTHOR"
    created, updated = _ts(comment.get("created_at")), _ts(comment.get("updated_at"))
    if created is None or updated is None:
        return "COMMENT_EDIT_STATE_UNKNOWN"
    if created > now:
        return "FUTURE_COMMENT"
    if updated > created:
        return "COMMENT_EDITED_AFTER_POSTING"
    return None


def comment_trust_reason(
    comment: Mapping[str, Any], trusted_logins: Sequence[str], now: str
) -> str | None:
    """Public form of the trust rule: None when the comment may carry a verdict."""
    now_dt = _ts(now)
    if now_dt is None:
        raise ValueError("now must be RFC3339 UTC ending in Z")
    return _comment_trust(comment, frozenset(t.lower() for t in trusted_logins), now_dt)


def evaluate_trigger(
    *,
    comments: Sequence[Mapping[str, Any]],
    origin_prs: Mapping[int, Mapping[str, Any]],
    now: str,
    contains: Contains,
    trusted_logins: Sequence[str] = (),
    shared_logins: Sequence[str] = (),
    labels: Sequence[str] = (),
    promise_report: Mapping[str, Any] | None = None,
    promise_judged_at: str | None = None,
    promise_prs: Sequence[int] = (),
) -> dict[str, Any]:
    """Whether an independent LIVE_FAILED verdict exists.

    ``origin_prs`` maps PR number -> {"merge_sha", "merged_at", "author",
    "author_sessions"} as read from GitHub (never from the comment).
    """
    now_dt = _ts(now)
    if now_dt is None:
        raise ValueError("now must be RFC3339 UTC ending in Z")
    trusted = frozenset(t.lower() for t in trusted_logins)
    shared = frozenset(s.lower() for s in shared_logins)
    ignored: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []

    for comment in comments:
        texts = _BLOCK_RE.findall(str(comment.get("body", "")))
        if not texts:
            continue
        reason = _comment_trust(comment, trusted, now_dt)
        for text in texts:
            entry = {"created_at": comment.get("created_at"), "author": comment.get("author")}
            if reason:
                ignored.append({**entry, "reason": reason})
                continue
            block = parse_block(text)
            if block is None:
                ignored.append({**entry, "reason": "BLOCK_MALFORMED"})
                continue
            pr = origin_prs.get(block["origin_pr"])
            if pr is None or not pr.get("merge_sha"):
                ignored.append({**entry, "reason": "ORIGIN_PR_NOT_MERGED_OR_UNKNOWN"})
                continue
            if pr["merge_sha"] != block["merge_sha"]:
                ignored.append({**entry, "reason": "MERGE_SHA_MISMATCH"})
                continue
            if contains(block["merge_sha"], block["live_commit"]) is not True:
                ignored.append({**entry, "reason": "MERGE_NOT_IN_LIVE_COMMIT"})
                continue
            authors = {str(pr.get("author", "")).lower()} - {""}
            sessions = {str(s).strip().lower() for s in pr.get("author_sessions") or ()} - {""}
            if not sessions:
                ignored.append({**entry, "reason": "AUTHOR_SESSION_UNKNOWN"})
                continue
            who = block["confirmer"].lower()
            names = {who, *who.split("/")}
            login = str(comment.get("author", "")).lower()
            if names & (authors | sessions) or (login in authors and login not in shared):
                ignored.append({**entry, "reason": "CONFIRMER_NOT_INDEPENDENT"})
                continue
            accepted.append({
                "source": "NEXUS_LIVE_FAILED_V1",
                "origin_prs": [block["origin_pr"]],
                "merge_shas": [block["merge_sha"]],
                "live_commit": block["live_commit"],
                "confirmer": block["confirmer"],
                "witness": block["witness"],
                "reason": block["reason"],
                "judged_at": comment.get("created_at"),
            })

    if promise_report is not None and promise_report.get("recommendation") == "LIVE_FAILED":
        independent = [
            r
            for r in promise_report.get("promises") or []
            if r.get("confirmer_verdict")
            and not r["confirmer_verdict"].get("ignored")
            and (r.get("status") == "FAILED" or r["confirmer_verdict"].get("verdict") == "REJECT")
        ]
        merged = [n for n in promise_prs if (origin_prs.get(n) or {}).get("merge_sha")]
        if not independent:
            ignored.append({"source": "PROMISE_REPORT", "reason": "NO_INDEPENDENT_CONFIRMER"})
        elif not merged or len(merged) != len(promise_prs):
            ignored.append({
                "source": "PROMISE_REPORT",
                "reason": "ORIGIN_PR_NOT_MERGED_OR_UNKNOWN",
            })
        elif _ts(promise_judged_at) is None or _ts(promise_judged_at) > now_dt:  # type: ignore[operator]
            ignored.append({"source": "PROMISE_REPORT", "reason": "JUDGED_AT_UNKNOWN"})
        else:
            accepted.append({
                "source": "PROMISE_CONFIRMATION",
                "origin_prs": sorted(merged),
                "merge_shas": [origin_prs[n]["merge_sha"] for n in sorted(merged)],
                "live_commit": None,
                "confirmer": independent[0]["confirmer_verdict"].get("confirmer"),
                "witness": "promise report: "
                + ", ".join(f"{r['promise_id']}={r['status']}" for r in independent),
                "reason": "promise_confirmation LIVE_FAILED",
                "judged_at": promise_judged_at,
            })

    accepted.sort(key=lambda a: _ts(a["judged_at"]) or now_dt)
    trigger = accepted[0] if accepted else None
    label = LIVE_FAILED_LABEL in set(labels)
    reasons = []
    if trigger is None and label:
        reasons.append("LABEL_WITHOUT_VALID_CONFIRMATION")
    return {
        "schema": SCHEMA,
        "triggered": trigger is not None,
        "trigger": trigger,
        "label_present": label,
        "reason_codes": reasons,
        "ignored": ignored,
    }


# --- revert planning (pure parts) -------------------------------------------


_PR_IN_SUBJECT = re.compile(r"\(#(\d+)\)\s*$")


def pr_number_of(subject: str) -> int | None:
    m = _PR_IN_SUBJECT.search(subject or "")
    return int(m.group(1)) if m else None


def gateway_relevant(paths: Sequence[str]) -> bool:
    return any(
        not p.startswith(IRRELEVANT_PREFIXES) and not ("/" not in p and p.endswith(".md"))
        for p in paths
    )


def is_gateway_class(surfaces: Sequence[str | None], paths: Sequence[str]) -> bool:
    """A declared gateway/deployer surface, or no declaration and a deployable path."""
    declared = [s for s in surfaces if isinstance(s, str) and s]
    if declared:
        return any(s.lower() in GATEWAY_SURFACES for s in declared)
    return gateway_relevant(paths)


def gateway_hold_plan(
    *,
    merge_shas: Sequence[str],
    status: Mapping[str, Any] | None,
    hold_present: bool,
    hold_env: bool,
    contains: Contains,
    last_receipt: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """What to do with the auto-deployer.  Never more than a HOLD while not live."""
    previous = {
        "previous_commit": (last_receipt or {}).get("previous_commit"),
        "previous_root": (last_receipt or {}).get("previous_root"),
    }
    live = (status or {}).get("live_commit")
    state = (status or {}).get("status")
    if not isinstance(live, str) or not _SHA40.match(live) or not isinstance(state, str):
        return {"action": "NONE", "reason": "DEPLOYER_STATUS_UNREADABLE", **previous}
    flags = [contains(m, live) for m in merge_shas]
    if any(f is None for f in flags):
        return {
            "action": "NONE",
            "reason": "LIVE_ANCESTRY_UNKNOWN",
            "live_commit": live,
            **previous,
        }
    if any(flags):
        return {
            "action": "RECOMMEND_FAST_REVERT",
            "reason": "MERGE_ALREADY_LIVE",
            "live_commit": live,
            "advice": "A HOLD now would also block the revert's deploy. Merge the revert PR "
            "first; the deployer ships it normally. For an emergency return to the "
            "previous verified deployment ask workspace-86 (manual hold -> rebind "
            "previous_root -> adopt -> release).",
            **previous,
        }
    if hold_present or hold_env:
        return {
            "action": "NONE",
            "reason": "HOLD_ALREADY_PRESENT" if hold_present else "HOLD_ENV_SET",
            "live_commit": live,
            **previous,
        }
    if state not in HOLDABLE_STATUSES:
        return {
            "action": "NONE",
            "reason": f"DEPLOYER_STATUS_{state}",
            "live_commit": live,
            **previous,
        }
    return {"action": "HOLD", "reason": "MERGE_NOT_YET_LIVE", "live_commit": live, **previous}


def hold_text(
    issue: int, origin_prs: Sequence[int], merge_shas: Sequence[str], created_at: str
) -> str:
    prs = ",".join(f"#{n}" for n in origin_prs)
    shas = ",".join(m[:12] for m in merge_shas)
    return f"{HOLD_PREFIX} issue #{issue} origin {prs} merge {shas} created {created_at}\n"


def release_allowed(
    *, current_text: str | None, written_text: str, revert_merged: bool, now: str
) -> tuple[bool, str]:
    """Release only our own, unchanged HOLD, only after the revert merged, within 6 h."""
    if current_text is None:
        return False, "HOLD_ABSENT"
    if current_text != written_text or not written_text.startswith(HOLD_PREFIX):
        return False, "HOLD_TEXT_CHANGED"
    m = re.search(r" created (\S+)\n$", written_text)
    created, now_dt = _ts(m.group(1)) if m else None, _ts(now)
    if created is None or now_dt is None:
        return False, "HOLD_CREATED_AT_UNKNOWN"
    if created > now_dt:
        return False, "HOLD_CREATED_IN_FUTURE"
    if now_dt - created > HOLD_MAX_AGE:
        return False, "HOLD_OLDER_THAN_6H_ASK_WORKSPACE_86"
    if not revert_merged:
        return False, "REVERT_NOT_MERGED"
    return True, "RELEASE"


def minutes_between(start: str | None, end: str | None) -> float | None:
    a, b = _ts(start), _ts(end)
    if a is None or b is None:
        return None
    return round((b - a).total_seconds() / 60, 1)
