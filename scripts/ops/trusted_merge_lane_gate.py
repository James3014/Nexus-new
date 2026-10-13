"""Trusted default-branch merge-lane binding gate for protected pull requests."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import stat
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

ENFORCEMENT_START_PR_NUMBER = 1061
# Pre-enforcement compatibility is pinned to the exact head each still-open
# legacy PR had at cut-over (#1749). A new head pushed to an old PR number is
# enforced like any other PR instead of inheriting the exemption.
LEGACY_PR_HEAD_ALLOWLIST: Mapping[int, str] = MappingProxyType({
    113: "dd41f999c738a2928ad6f7297b48baa28e6903f7",
    242: "631179d175f1f656c7b957eb7d872e30ce057d84",
    271: "61765f15e9f768cdfeeca18ecc9e97c19efd2e42",
    296: "7d973c4efb76e5ff4062c2d31fbdb3372872cb3b",
    335: "0f9583553c5d7d1d3fb75b61943e3b0fee34dcee",
    353: "b48b04885e67b5ab31e9539537ea0082f87408da",
    399: "eb843222b3800781088c7b566e077ca5cc18e89e",
    402: "f37242f8e58f09826fa6b0e817b6e97b6a5bf5f1",
    407: "d512057d54f4d451ba62da07da4173f90e9ad966",
    410: "c901877cacb8f12998fee80983c59f0a1cad42fd",
    421: "a51f16ee0a1d7225e2a2c1f0850dea646c134fa3",
    425: "055889065f2f5d4e2bb8c6521a11d1bb21a24006",
    429: "cdb0491e52b6ee54a6afe985eb9e1418cf1f7d9d",
    486: "448db7e4a32b33d9b5f1d23cd7063204011f1800",
    496: "7c7160ce252b7078acfeb5d023de31ec023d658c",
    511: "01147758578e2fc47ee25c1ca1c5a834aab4ed8f",
    519: "5b4b53ffece35512de06221c88d76d1420acbb5b",
    521: "ef59ea5a935faf486cfd5de3d5445cc92ab11632",
    529: "17f0ad064aceca5cd128904b46d921a3345a3cce",
    534: "d936bd41c249e1efe712e0691dd207ec2cef34f1",
    537: "4b6fa2bfd8aa89dd4e2eaafe5c23a8b38ac7d0a3",
    551: "bdd83c080e96fd6c4816ecda12f277a1230c80bc",
    565: "67b897e6f0de435d664f2c4a1fcda19c5e411d44",
    591: "110d910b7b6cb083825804510e169aa5ac41c375",
    606: "71f4298787b248b99b4b07cc6b8a96384472659c",
    616: "878e752cdc7b0f6c89373c2e90b4cf660734db5c",
    620: "9c19bb6ba697c3de2fb3fcc6d4fd3e02dad37af7",
    622: "08f762fd59d211855a4c276fbbd0c61f415023d7",
    623: "34625010e07f66ee944f92fd70660dc809ce6dc8",
    627: "1b652c251ceb9f45db2d41a67f7ce608b83cf6c3",
    629: "53a99d83a26b32eabcc94e8206585c000b59f83a",
    630: "785b865816a51ed2e39ebd101fe06e995410c77a",
    633: "a985b3158260c0cff42eebe75c651a2fb182eba5",
    634: "53306681d41fffbbbc483fc5247814ba97ec0683",
    635: "362a9a85ed4576c10df40da47ddf6678305bf7a4",
    654: "ab33952caebb2ee9ba51bb576746f13f468feabf",
    677: "12a97a9502965c7cae6778f3a7a896de67cde6ac",
    687: "abf34007f856a2ff11fdd037901e7f87253f7ce9",
    689: "c66b400137f10dbfddc3c5068497ec854eccea1b",
    791: "d2bd29073c489ae3b1676bf82c8d9ca0d405ce99",
    794: "931d1969da39433f2123ccc61591461e783b5cb3",
    795: "e47392ebf82a24e2292dda3a3acd1edb37823987",
    817: "d79afac8548405395ecf0b05a3158e0d3b617264",
    818: "1c9c19dc4e8b42dce7935021798339311157187b",
    847: "4ad900be248ede97fd4569853c714482d80b39c9",
    904: "2fe2d6e7aa88304f30c7ec4babc5e6c53447055d",
    961: "f1b147063c6575a2a6ea3fed7e0d94a5ada769be",
    1017: "c7ac9d99c8b3bea22fa6ad3968be1fe815a03138",
})
_TERMINAL_CARD_STATUS_PREFIXES = (
    "SUPERSEDED",
    "COMPLETED",
    "CLOSED",
    "RETIRED",
    "CANCELLED",
    "ABANDONED",
)
BINDING_SCHEMA = "nexus.merge_lane_binding.v1"
REBIND_SCHEMA = "nexus.owner_execution_lane_rebind.v1"
DIRECT_LANES = {"DIRECT_CANONICAL", "DIRECT_DELEGATED"}
ALL_LANES = DIRECT_LANES | {"GOVERNED"}
CONTRACT_KINDS = {"OWNER_INLINE", "TRACKED_TASK_CARD"}
START_MARKER = "<!-- NEXUS_MERGE_LANE_V1"
END_MARKER = "NEXUS_MERGE_LANE_V1 -->"
INTENT_START_MARKER = "<!-- NEXUS_ISSUE_INTENT_V1"
INTENT_END_MARKER = "NEXUS_ISSUE_INTENT_V1 -->"
ON_MERGE_KEEP_OPEN = "KEEP_OPEN"
ON_MERGE_CLOSE = "CLOSE"
VALID_ON_MERGE_ACTIONS = frozenset({ON_MERGE_KEEP_OPEN, ON_MERGE_CLOSE})
MERGE_INTENT_BINDING_SCHEMA = "nexus.merge_intent_binding.v1"
SUPPORTED_MERGE_METHODS = frozenset({"merge", "squash", "rebase"})
CLOSING_KEYWORD_FAMILIES = (
    "close",
    "closes",
    "closed",
    "fix",
    "fixes",
    "fixed",
    "resolve",
    "resolves",
    "resolved",
)
CLOSING_KEYWORD_PATTERN = re.compile(
    r"(?i)\b("
    + "|".join(CLOSING_KEYWORD_FAMILIES)
    + r")\s+(?:https?://github\.com/[^/\s]+/[^/\s]+/issues/|(?:\b[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+)?#)(\d+)\b"
)
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA64 = re.compile(r"^[0-9a-f]{64}$")
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
TASK_PATH = re.compile(r"^tasks/[A-Za-z0-9._/-]+\.md$")


class LaneBindingError(ValueError):
    pass


class IssueClosureIntentError(LaneBindingError):
    pass


def canonical_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _exact_dict(value: Any, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise LaneBindingError(f"{label}_MUST_BE_OBJECT")
    return dict(value)


def _exact_str(value: Any, label: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise LaneBindingError(f"{label}_INVALID")
    return value


def _exact_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise LaneBindingError(f"{label}_INVALID")
    return value


def _sha(value: Any, label: str, *, size: int) -> str:
    text = _exact_str(value, label)
    pattern = SHA40 if size == 40 else SHA64
    if not pattern.fullmatch(text):
        raise LaneBindingError(f"{label}_INVALID")
    return text


def _safe_id(value: Any, label: str) -> str:
    text = _exact_str(value, label)
    if not SAFE_ID.fullmatch(text):
        raise LaneBindingError(f"{label}_INVALID")
    return text


def _task_path(value: Any) -> str:
    text = _exact_str(value, "TASK_CARD_PATH")
    if not TASK_PATH.fullmatch(text) or ".." in Path(text).parts:
        raise LaneBindingError("TASK_CARD_PATH_INVALID")
    return text


def extract_binding(body: Any) -> dict[str, Any]:
    if type(body) is not str:
        raise LaneBindingError("PR_BODY_REQUIRED")
    if body.count(START_MARKER) != 1 or body.count(END_MARKER) != 1:
        raise LaneBindingError("EXACTLY_ONE_MERGE_LANE_BINDING_REQUIRED")
    start = body.index(START_MARKER) + len(START_MARKER)
    end = body.index(END_MARKER, start)
    payload = body[start:end].strip()
    if not payload:
        raise LaneBindingError("MERGE_LANE_BINDING_JSON_INVALID")
    try:
        value = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise LaneBindingError("MERGE_LANE_BINDING_JSON_INVALID") from exc
    return _exact_dict(value, "MERGE_LANE_BINDING")


def render_binding(binding: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(binding), ensure_ascii=False, indent=2, sort_keys=True)
    return f"{START_MARKER}\n{payload}\n{END_MARKER}"


def extract_closure_intents(body: Any) -> list[dict[str, Any]]:
    if type(body) is not str:
        return []
    count_start = body.count(INTENT_START_MARKER)
    count_end = body.count(INTENT_END_MARKER)
    if count_start != count_end:
        raise IssueClosureIntentError("MISMATCHED_ISSUE_INTENT_MARKERS")
    if count_start == 0:
        return []
    if count_start > 1:
        raise IssueClosureIntentError("MULTIPLE_ISSUE_INTENT_BLOCKS_FORBIDDEN")

    start = body.index(INTENT_START_MARKER) + len(INTENT_START_MARKER)
    end = body.index(INTENT_END_MARKER, start)
    raw = body[start:end].strip()
    if not raw:
        raise IssueClosureIntentError("EMPTY_ISSUE_INTENT_BLOCK")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IssueClosureIntentError("INVALID_ISSUE_INTENT_JSON") from exc

    raw_items = data if isinstance(data, list) else [data]
    normalized: list[dict[str, Any]] = []

    for item in raw_items:
        if not isinstance(item, Mapping):
            raise IssueClosureIntentError("INTENT_ITEM_MUST_BE_OBJECT")
        issue = item.get("issue") if "issue" in item else item.get("issue_number")
        if not isinstance(issue, int) or isinstance(issue, bool) or issue <= 0:
            raise IssueClosureIntentError("INTENT_ISSUE_NUMBER_INVALID")

        action = str(item.get("on_merge") or "").strip().upper()
        if action not in VALID_ON_MERGE_ACTIONS:
            raise IssueClosureIntentError(f"INVALID_ON_MERGE_ACTION: {action!r}")

        normalized.append({
            "issue_number": issue,
            "on_merge": action,
        })

    return normalized


def strip_markers(body: Any) -> str:
    if type(body) is not str:
        return ""
    text = body
    if INTENT_START_MARKER in text and INTENT_END_MARKER in text:
        start = text.index(INTENT_START_MARKER)
        end = text.index(INTENT_END_MARKER, start) + len(INTENT_END_MARKER)
        text = text[:start] + text[end:]
    if START_MARKER in text and END_MARKER in text:
        start = text.index(START_MARKER)
        end = text.index(END_MARKER, start) + len(END_MARKER)
        text = text[:start] + text[end:]
    return text


def find_closing_keyword_references(text: str) -> list[tuple[str, int]]:
    matches = CLOSING_KEYWORD_PATTERN.findall(text)
    return [(keyword.lower(), int(issue_str)) for keyword, issue_str in matches]


def validate_issue_closure_intent(body: Any) -> dict[str, Any]:
    intents = extract_closure_intents(body)
    cleaned_prose = strip_markers(body)
    detected_refs = find_closing_keyword_references(cleaned_prose)

    detected_by_issue: dict[int, list[str]] = {}
    for kw, num in detected_refs:
        detected_by_issue.setdefault(num, []).append(kw)

    intent_by_issue = {item["issue_number"]: item["on_merge"] for item in intents}

    untracked_issues = set(detected_by_issue.keys()) - set(intent_by_issue.keys())
    if untracked_issues:
        culprits = ", ".join(
            f"#{num} ({', '.join(detected_by_issue[num])})" for num in sorted(untracked_issues)
        )
        raise IssueClosureIntentError(
            f"UNINTENDED_CLOSING_KEYWORD_FOR_UNTRACKED_ISSUE: PR prose contains GitHub closing keywords targeting {culprits}. "
            "Declare intent in <!-- NEXUS_ISSUE_INTENT_V1 or rephrase using neutral prose (e.g. '#X remains open')."
        )

    for issue_num, action in intent_by_issue.items():
        if action == ON_MERGE_KEEP_OPEN:
            if issue_num in detected_by_issue:
                kws = ", ".join(detected_by_issue[issue_num])
                raise IssueClosureIntentError(
                    f"REJECTED_CLOSING_KEYWORD_FOR_KEEP_OPEN: PR prose contains closing keyword '{kws}' targeting #{issue_num}, "
                    f"which triggers GitHub auto-close even when negated (e.g. 'does not close #{issue_num}'). "
                    f"Use neutral prose such as '#{issue_num} remains open' instead."
                )
        elif action == ON_MERGE_CLOSE:
            if issue_num not in detected_by_issue:
                raise IssueClosureIntentError(
                    f"MISSING_EXPLICIT_CLOSING_DECLARATION: PR declared on_merge=CLOSE for #{issue_num}, "
                    f"but prose has no explicit closing keyword (e.g. 'Closes #{issue_num}')."
                )

    result: dict[str, Any] = {
        "schema": "nexus.issue_closure_intent.v1",
        "status": "PASS",
        "intents": intents,
        "detected_closing_references": [
            {"issue_number": num, "keyword": kw} for kw, num in detected_refs
        ],
        "claim_ceiling": "PR_ISSUE_CLOSURE_INTENT_VALIDATION_ONLY",
    }
    result["content_sha256"] = canonical_hash({
        k: v for k, v in result.items() if k != "content_sha256"
    })
    return result


def render_intent(intents: Sequence[Mapping[str, Any]] | Mapping[str, Any]) -> str:
    items = list(intents) if isinstance(intents, (list, tuple)) else [intents]
    payload = json.dumps(items, ensure_ascii=False, indent=2, sort_keys=True)
    return f"{INTENT_START_MARKER}\n{payload}\n{INTENT_END_MARKER}"


def validate_final_merge_intent_binding(
    *,
    pr_body: str | None,
    pr_number: int,
    head_sha: str,
    base_sha: str,
    expected_pr_number: int,
    expected_head_sha: str,
    expected_base_sha: str,
    merge_method: str = "squash",
    commit_title: str | None = None,
    commit_message: str | None = None,
) -> dict[str, Any]:
    if pr_body is None or not isinstance(pr_body, str) or not pr_body.strip():
        raise IssueClosureIntentError("PR_BODY_REQUIRED")
    if not isinstance(pr_number, int) or isinstance(pr_number, bool) or pr_number <= 0:
        raise IssueClosureIntentError("PR_NUMBER_INVALID")
    if (
        not isinstance(expected_pr_number, int)
        or isinstance(expected_pr_number, bool)
        or expected_pr_number <= 0
    ):
        raise IssueClosureIntentError("EXPECTED_PR_NUMBER_INVALID")
    if pr_number != expected_pr_number:
        raise IssueClosureIntentError(
            f"PR_NUMBER_MISMATCH: expected {expected_pr_number}, got {pr_number}"
        )

    if not isinstance(head_sha, str) or not isinstance(expected_head_sha, str):
        raise IssueClosureIntentError("HEAD_SHA_INVALID")
    if head_sha.strip().lower() != expected_head_sha.strip().lower():
        raise IssueClosureIntentError(
            f"HEAD_SHA_MISMATCH: expected {expected_head_sha}, got {head_sha}"
        )

    if not isinstance(base_sha, str) or not isinstance(expected_base_sha, str):
        raise IssueClosureIntentError("BASE_SHA_INVALID")
    if base_sha.strip().lower() != expected_base_sha.strip().lower():
        raise IssueClosureIntentError(
            f"BASE_SHA_MISMATCH: expected {expected_base_sha}, got {base_sha}"
        )

    norm_method = str(merge_method or "squash").strip().lower()
    if norm_method not in SUPPORTED_MERGE_METHODS:
        raise IssueClosureIntentError(f"UNSUPPORTED_MERGE_METHOD: {merge_method!r}")

    intent_result = validate_issue_closure_intent(pr_body)
    intents = intent_result.get("intents", [])

    final_fields_prose = f"{commit_title or ''}\n\n{commit_message or ''}"
    final_refs = find_closing_keyword_references(final_fields_prose)

    detected_in_final: dict[int, list[str]] = {}
    for kw, num in final_refs:
        detected_in_final.setdefault(num, []).append(kw)

    intent_by_issue = {item["issue_number"]: item["on_merge"] for item in intents}

    untracked_issues = set(detected_in_final.keys()) - set(intent_by_issue.keys())
    if untracked_issues:
        culprits = ", ".join(
            f"#{num} ({', '.join(detected_in_final[num])})" for num in sorted(untracked_issues)
        )
        raise IssueClosureIntentError(
            f"UNINTENDED_CLOSING_KEYWORD_FOR_UNTRACKED_ISSUE: Final merge fields contain GitHub closing keywords targeting {culprits}. "
            "Remove closing keywords or declare explicit intent in PR body."
        )

    for issue_num, action in intent_by_issue.items():
        if action == ON_MERGE_KEEP_OPEN:
            if issue_num in detected_in_final:
                kws = ", ".join(detected_in_final[issue_num])
                raise IssueClosureIntentError(
                    f"REJECTED_CLOSING_KEYWORD_FOR_KEEP_OPEN_IN_FINAL_MERGE_FIELDS: Final merge commit fields contain closing keyword '{kws}' targeting #{issue_num}, "
                    f"which contradicts declared KEEP_OPEN intent and would trigger GitHub auto-close."
                )

    result: dict[str, Any] = {
        "schema": MERGE_INTENT_BINDING_SCHEMA,
        "status": "PASS",
        "pr_number": pr_number,
        "head_sha": head_sha.strip().lower(),
        "base_sha": base_sha.strip().lower(),
        "merge_method": norm_method,
        "intents": intents,
        "detected_final_closing_references": [
            {"issue_number": num, "keyword": kw} for kw, num in final_refs
        ],
        "claim_ceiling": "PR_ISSUE_CLOSURE_INTENT_VALIDATION_ONLY",
    }
    result["content_sha256"] = canonical_hash({
        k: v for k, v in result.items() if k != "content_sha256"
    })
    return result


def _git_show(repo_root: Path, revision: str, path: str) -> bytes:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"{revision}:{path}"],
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise LaneBindingError("TASK_CARD_NOT_PRESENT_AT_EXACT_REVISION")
    return proc.stdout


def _card_references_issue(path: str, text: str, issue_number: int) -> bool:
    number = str(issue_number)
    if re.search(rf"(?:^|/)(?:github-)?issue-{number}(?:[-/.]|$)", path):
        return True
    if re.search(rf"(?m)^task_id:\s*`?(?:github-)?issue-{number}(?:[-_`]|\s*$)", text):
        return True
    for match in re.finditer(
        r"(?m)^(?:issue|issue_number|github_issue|source_issue)\s*:\s*(.+)$", text
    ):
        if re.search(rf"(?:^|[^0-9])#?{number}(?:[^0-9]|$)", match.group(1).replace("`", "")):
            return True
    return False


def _active_governed_cards_for_issues(
    repo_root: Path, base_sha: str, issue_numbers: Sequence[int]
) -> list[str]:
    """Return tracked GOVERNED Task Cards at ``base_sha`` that are bound to the Issues."""
    if not issue_numbers:
        return []
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "grep",
            "-l",
            "-E",
            r"^execution_lane:[[:space:]]*`?GOVERNED`?[[:space:]]*$",
            base_sha,
            "--",
            "tasks",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode not in (0, 1):
        raise LaneBindingError("GOVERNED_CARD_LOOKUP_FAILED")
    bound: list[str] = []
    for line in proc.stdout.splitlines():
        path = line.split(":", 1)[1] if line.startswith(f"{base_sha}:") else line
        text = _git_show(repo_root, base_sha, path).decode("utf-8", errors="replace")
        status = re.search(r"(?m)^status:\s*`?([A-Za-z_]+)", text)
        if status and status.group(1).upper().startswith(_TERMINAL_CARD_STATUS_PREFIXES):
            continue
        if any(_card_references_issue(path, text, number) for number in issue_numbers):
            bound.append(path)
    return sorted(bound)


def _candidate_commit_messages(repo_root: Path, *, base_sha: str, head_sha: str) -> str:
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "log",
            "--format=%B%x00",
            f"{base_sha}..{head_sha}",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise LaneBindingError("CANDIDATE_COMMIT_MESSAGES_UNAVAILABLE")
    return "\n\n".join(part.strip() for part in proc.stdout.split("\x00") if part.strip())


def _task_card_metadata(card: bytes) -> tuple[str | None, str | None, str | None]:
    try:
        text = card.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LaneBindingError("TASK_CARD_UTF8_INVALID") from exc
    task = re.search(r"(?m)^task_id:\s*\x60?([^\s\x60]+)\x60?\s*$", text)
    lane = re.search(r"(?m)^execution_lane:\s*\x60?([A-Z_]+)\x60?\s*$", text)
    attempt = re.search(r"(?m)^attempt_id:\s*\x60?([^\s\x60]+)\x60?\s*$", text)
    return (
        task.group(1) if task else None,
        lane.group(1) if lane else None,
        attempt.group(1) if attempt else None,
    )


def _validate_hash_field(payload: dict[str, Any], field: str) -> None:
    expected = _sha(payload.get(field), field.upper(), size=64)
    unsigned = dict(payload)
    unsigned.pop(field, None)
    if canonical_hash(unsigned) != expected:
        raise LaneBindingError(f"{field.upper()}_INVALID")


def _validate_owner(repository: str, owner_id: Any) -> str:
    owner = _exact_str(owner_id, "OWNER_ID")
    repository_owner = repository.split("/", 1)[0]
    if owner != repository_owner:
        raise LaneBindingError("OWNER_ID_REPOSITORY_OWNER_MISMATCH")
    return owner


def _validate_rebind(
    rebind_value: Any,
    *,
    repository: str,
    issue_number: int,
    task_id: str,
    attempt_id: str,
    task_card_path: str,
    task_card_sha256: str,
    pull_request_number: int,
    head_sha: str,
    requested_lane: str,
    owner_id: str,
) -> dict[str, Any]:
    rebind = _exact_dict(rebind_value, "OWNER_LANE_REBIND")
    required = {
        "schema",
        "repository",
        "issue_number",
        "task_id",
        "attempt_id",
        "task_card_path",
        "task_card_sha256",
        "pull_request_number",
        "expected_pr_head_sha",
        "from_lane",
        "to_lane",
        "owner_id",
        "owner_confirmation",
        "record_hash",
    }
    if set(rebind) != required:
        raise LaneBindingError("OWNER_LANE_REBIND_SCHEMA_FIELDS_INVALID")
    if rebind["schema"] != REBIND_SCHEMA:
        raise LaneBindingError("OWNER_LANE_REBIND_SCHEMA_INVALID")
    if rebind["from_lane"] != "GOVERNED" or rebind["to_lane"] != requested_lane:
        raise LaneBindingError("OWNER_LANE_REBIND_LANE_MISMATCH")
    if rebind["owner_confirmation"] is not True:
        raise LaneBindingError("OWNER_LANE_REBIND_OWNER_CONFIRMATION_REQUIRED")
    if (
        rebind["repository"] != repository
        or rebind["issue_number"] != issue_number
        or rebind["task_id"] != task_id
        or rebind["attempt_id"] != attempt_id
        or rebind["task_card_path"] != task_card_path
        or rebind["task_card_sha256"] != task_card_sha256
        or rebind["pull_request_number"] != pull_request_number
        or rebind["expected_pr_head_sha"] != head_sha
        or rebind["owner_id"] != owner_id
    ):
        raise LaneBindingError("OWNER_LANE_REBIND_SUBJECT_MISMATCH")
    _sha(rebind["expected_pr_head_sha"], "EXPECTED_PR_HEAD_SHA", size=40)
    _sha(rebind["task_card_sha256"], "TASK_CARD_SHA256", size=64)
    _safe_id(rebind["task_id"], "TASK_ID")
    _safe_id(rebind["attempt_id"], "ATTEMPT_ID")
    _task_path(rebind["task_card_path"])
    _validate_hash_field(rebind, "record_hash")
    return rebind


# ---------------------------------------------------------------------------
# Owner attestation for agent-authored pull requests (#1750 phase 2).
#
# An agent acting under its own GitHub identity may only get a PR through this
# gate with a grant the Owner signed on a device-bound key (Touch ID on the
# Owner's Mac).  The public keys and the agent identities are read from the
# exact base revision, so the PR under review cannot change either.
# ---------------------------------------------------------------------------
ATTESTATION_START_MARKER = "<!-- NEXUS_OWNER_ATTESTATION_V1"
ATTESTATION_END_MARKER = "NEXUS_OWNER_ATTESTATION_V1 -->"
ATTESTATION_SCHEMA = "nexus.owner_grant_attestation.v1"
SIGNING_KEYS_PATH = "governance/owner-signing-keys.json"
SIGNING_KEYS_SCHEMA = "nexus.owner_signing_keys.v1"
AGENT_IDENTITIES_PATH = "governance/agent-identities.json"
AGENT_IDENTITIES_SCHEMA = "nexus.agent_identities.v1"
ATTESTATION_MAX_LIFETIME = timedelta(days=7)
ATTESTATION_CLOCK_SKEW = timedelta(minutes=5)
TRUSTED_OPENSSL = Path("/usr/bin/openssl")
# Paths an attestation can never cover: the trust configuration itself, CI and
# the gate code that enforces it.
ATTESTATION_PROTECTED_PATTERNS = (
    "governance/**",
    ".github/**",
    "scripts/ops/trusted_*",
    "scripts/ops/owner_attestation.py",
    "scripts/ops/__init__.py",
    "scripts/__init__.py",
    "scripts/ops/pr_impact_gate.py",
    "scripts/ops/select_tests.py",
    "tools/owner-signer/**",
    "tasks/**",
    ".claude/**",
    "**/.claude/**",
    ".mcp.json",
    "**/.mcp.json",
    "AGENTS.md",
    "**/AGENTS.md",
    "CLAUDE.md",
    "**/CLAUDE.md",
    "MUSE_PROTO.md",
    "pyproject.toml",
    "uv.lock",
    "requirements/**",
    "GEMINI.md",
    "**/GEMINI.md",
    ".cursorrules",
    "**/.cursorrules",
    ".agents/**",
    "**/.agents/**",
    ".gemini/**",
    "**/.gemini/**",
    ".vscode/**",
    "**/.vscode/**",
    ".gitmodules",
    ".gitattributes",
    "**/.gitattributes",
    ".nexus-core/**",
    ".cargo/**",
    "conftest.py",
    "**/conftest.py",
    # Authority-bearing documents and the tests and test selection that guard
    # this gate (#1817 review).
    "docs/governance/**",
    "docs/testing/test_impact_map.md",
    ".nexus/test_impact_index.json",
    "tests/ops/test_owner_attestation_gate.py",
    "tests/ops/test_trusted_*",
)
ATTESTATION_ACTION = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
ATTESTATION_MAX_ACTIONS = 8
ATTESTATION_MAX_PATHS = 12
ATTESTATION_MAX_PATH_LENGTH = 120
_GITHUB_LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})(?:\[bot\])?$")
_PATH_PATTERN = re.compile(r"^[A-Za-z0-9._*?/-]{1,200}$")


def _glob_regex(pattern: str) -> re.Pattern[str]:
    if (
        not _PATH_PATTERN.fullmatch(pattern)
        or ".." in pattern.split("/")
        or pattern.startswith("/")
    ):
        raise LaneBindingError("ATTESTATION_PATH_PATTERN_INVALID")
    out = []
    index = 0
    while index < len(pattern):
        if pattern.startswith("**", index):
            out.append(".*")
            index += 2
        elif pattern[index] == "*":
            out.append("[^/]*")
            index += 1
        elif pattern[index] == "?":
            out.append("[^/]")
            index += 1
        else:
            out.append(re.escape(pattern[index]))
            index += 1
    regex = "".join(out)
    if pattern.endswith("/**"):
        # ``X/**`` also names the path ``X`` itself (a file or symlink at X).
        regex = regex[: -len("/.*")] + "(?:/.*)?"
    return re.compile(regex)


def _path_matches(path: str, patterns: Sequence[str], *, casefold: bool = False) -> bool:
    """Glob match; ``casefold`` compares case-insensitively (APFS checkouts)."""
    if casefold:
        path = path.casefold()
    return any(
        _glob_regex(pattern.casefold() if casefold else pattern).fullmatch(path)
        for pattern in patterns
    )


def _parse_utc(value: Any, label: str) -> datetime:
    text = _exact_str(value, label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise LaneBindingError(f"{label}_INVALID") from exc
    if parsed.tzinfo is None:
        raise LaneBindingError(f"{label}_TIMEZONE_REQUIRED")
    return parsed.astimezone(timezone.utc)


def canonical_attestation_bytes(payload: Mapping[str, Any]) -> bytes:
    """The exact bytes the Owner signs: compact, key-sorted UTF-8 JSON."""
    return json.dumps(
        dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def extract_attestation(body: Any) -> dict[str, Any] | None:
    text = body if isinstance(body, str) else ""
    starts = text.count(ATTESTATION_START_MARKER)
    if starts == 0:
        return None
    if starts != 1 or text.count(ATTESTATION_END_MARKER) != 1:
        raise LaneBindingError("ATTESTATION_MARKER_COUNT_INVALID")
    start = text.index(ATTESTATION_START_MARKER) + len(ATTESTATION_START_MARKER)
    end = text.index(ATTESTATION_END_MARKER)
    if end < start:
        raise LaneBindingError("ATTESTATION_MARKER_ORDER_INVALID")
    try:
        return _exact_dict(json.loads(text[start:end]), "ATTESTATION")
    except json.JSONDecodeError as exc:
        raise LaneBindingError("ATTESTATION_JSON_INVALID") from exc


def render_attestation(envelope: Mapping[str, Any]) -> str:
    return (
        f"{ATTESTATION_START_MARKER}\n"
        f"{json.dumps(dict(envelope), indent=2, sort_keys=True, ensure_ascii=False)}\n"
        f"{ATTESTATION_END_MARKER}"
    )


def _trusted_json(repo_root: Path, revision: str, path: str, label: str) -> dict[str, Any]:
    """Read trust configuration from the revision the gate itself runs from.

    A missing file is an error, never "not configured": the files ship with
    the gate, and removing them is an Owner change to a protected path.
    """
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "show", f"{revision}:{path}"],
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise LaneBindingError(f"{label}_MISSING")
    try:
        return _exact_dict(json.loads(proc.stdout.decode("utf-8")), label)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LaneBindingError(f"{label}_INVALID") from exc


def load_agent_identities(repo_root: Path, revision: str) -> frozenset[str]:
    # GitHub Apps appear in events as "<slug>[bot]" and must be listed that way.
    config = _trusted_json(repo_root, revision, AGENT_IDENTITIES_PATH, "AGENT_IDENTITIES")
    if config.get("schema") != AGENT_IDENTITIES_SCHEMA:
        raise LaneBindingError("AGENT_IDENTITIES_SCHEMA_INVALID")
    agents = config.get("agents")
    if not isinstance(agents, list) or not all(
        isinstance(item, str) and _GITHUB_LOGIN.fullmatch(item) for item in agents
    ):
        raise LaneBindingError("AGENT_IDENTITIES_INVALID")
    return frozenset(item.lower() for item in agents)


def load_owner_signing_keys(repo_root: Path, revision: str, owner_id: str) -> dict[str, str]:
    config = _trusted_json(repo_root, revision, SIGNING_KEYS_PATH, "OWNER_SIGNING_KEYS")
    if config.get("schema") != SIGNING_KEYS_SCHEMA or config.get("owner_id") != owner_id:
        raise LaneBindingError("OWNER_SIGNING_KEYS_SCHEMA_INVALID")
    keys = config.get("keys")
    if not isinstance(keys, list):
        raise LaneBindingError("OWNER_SIGNING_KEYS_INVALID")
    pinned: dict[str, str] = {}
    for entry in keys:
        item = _exact_dict(entry, "OWNER_SIGNING_KEY")
        pem = item.get("public_key_pem")
        if not isinstance(pem, str):
            raise LaneBindingError("OWNER_SIGNING_KEY_PEM_INVALID")
        key_id = _sha(item.get("key_id"), "OWNER_SIGNING_KEY_ID", size=64)
        if signing_key_id(pem) != key_id:
            raise LaneBindingError("OWNER_SIGNING_KEY_ID_MISMATCH")
        pinned[key_id] = pem
    return pinned


def _pem_der(pem: str) -> bytes:
    lines = [line.strip() for line in pem.strip().splitlines()]
    if (
        len(lines) < 3
        or lines[0] != "-----BEGIN PUBLIC KEY-----"
        or lines[-1] != "-----END PUBLIC KEY-----"
    ):
        raise LaneBindingError("OWNER_SIGNING_KEY_PEM_INVALID")
    try:
        return base64.b64decode("".join(lines[1:-1]), validate=True)
    except ValueError as exc:
        raise LaneBindingError("OWNER_SIGNING_KEY_PEM_INVALID") from exc


def signing_key_id(pem: str) -> str:
    """Key id: SHA-256 of the DER SubjectPublicKeyInfo."""
    return hashlib.sha256(_pem_der(pem)).hexdigest()


def _trusted_openssl() -> Path:
    try:
        info = TRUSTED_OPENSSL.stat()
    except OSError as exc:
        raise LaneBindingError("TRUSTED_OPENSSL_UNAVAILABLE") from exc
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != 0
        or info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)
    ):
        raise LaneBindingError("TRUSTED_OPENSSL_UNTRUSTED")
    return TRUSTED_OPENSSL


def verify_p256_signature(pem: str, message: bytes, signature_der: bytes) -> bool:
    """ECDSA P-256 / SHA-256 verification through the system OpenSSL binary."""
    openssl = _trusted_openssl()
    with tempfile.TemporaryDirectory() as raw:
        directory = Path(raw)
        key = directory / "key.pem"
        sig = directory / "sig.der"
        data = directory / "data.bin"
        key.write_text(pem.strip() + "\n", encoding="ascii")
        sig.write_bytes(signature_der)
        data.write_bytes(message)
        algorithm = subprocess.run(
            [str(openssl), "pkey", "-pubin", "-in", str(key), "-noout", "-text"],
            check=False,
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        )
        if algorithm.returncode != 0 or "prime256v1" not in algorithm.stdout:
            return False
        proc = subprocess.run(
            [
                str(openssl),
                "dgst",
                "-sha256",
                "-verify",
                str(key),
                "-signature",
                str(sig),
                str(data),
            ],
            check=False,
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        )
    return proc.returncode == 0 and proc.stdout.strip() == "Verified OK"


_SPECIAL_MODES = frozenset({"120000", "160000"})


def _diff_entries(repo_root: Path, left: str, right: str) -> dict[str, tuple[str, str]]:
    """Changed paths between two revisions mapped to their (old, new) modes."""
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "diff",
            "--raw",
            "--no-abbrev",
            "--no-renames",
            "-z",
            left,
            right,
        ],
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise LaneBindingError("ATTESTATION_CHANGED_PATHS_UNAVAILABLE")
    parts = proc.stdout.split(b"\0")
    entries: dict[str, tuple[str, str]] = {}
    index = 0
    while index + 1 < len(parts):
        meta = parts[index].decode("ascii", errors="replace").split()
        if len(meta) != 5 or not meta[0].startswith(":"):
            raise LaneBindingError("ATTESTATION_CHANGED_PATHS_UNAVAILABLE")
        path = parts[index + 1].decode("utf-8", errors="strict")
        entries[path] = (meta[0][1:], meta[1])
        index += 2
    return entries


def _tree_paths(repo_root: Path, revision: str) -> set[str]:
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "ls-tree", "-r", "-z", "--name-only", revision],
        check=False,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise LaneBindingError("ATTESTATION_CHANGED_PATHS_UNAVAILABLE")
    return {part.decode("utf-8", errors="replace") for part in proc.stdout.split(b"\0") if part}


def _reject_unsafe_paths(
    repo_root: Path,
    entries: Mapping[str, tuple[str, str]],
    trusted_revision: str,
    head_sha: str,
) -> None:
    """Refuse paths whose meaning differs between the gate and the Owner's Mac.

    The Owner's checkout is case-insensitive APFS, so a path that differs from
    a tracked one only in case, or any non-ASCII path (Unicode normalization),
    can land on a protected file there; symlinks and gitlinks redirect writes.
    """
    for path, (old_mode, new_mode) in entries.items():
        if not path.isascii():
            raise LaneBindingError(f"ATTESTATION_NON_ASCII_PATH:{ascii(path)}")
        if old_mode in _SPECIAL_MODES or new_mode in _SPECIAL_MODES:
            raise LaneBindingError(f"ATTESTATION_SYMLINK_OR_GITLINK:{path}")
    known: dict[str, set[str]] = {}
    for revision in (trusted_revision, head_sha):
        for tracked in _tree_paths(repo_root, revision):
            parts = tracked.split("/")
            for end in range(1, len(parts) + 1):
                prefix = "/".join(parts[:end])
                known.setdefault(prefix.casefold(), set()).add(prefix)
    for path in entries:
        parts = path.split("/")
        for end in range(1, len(parts) + 1):
            prefix = "/".join(parts[:end])
            if known.get(prefix.casefold(), {prefix}) - {prefix}:
                raise LaneBindingError(f"ATTESTATION_CASE_COLLISION_PATH:{path}")


def _changed_paths(
    repo_root: Path, base_sha: str, head_sha: str, trusted_revision: str
) -> list[str]:
    """Every path the head changes relative to the PR base *and* to current main.

    The event's ``base.sha`` can be older than main commits the head merged in;
    diffing against the merge-base with the trusted revision (main at the time
    of the check) also surfaces protected files such a merge would revert.
    """
    proc = subprocess.run(
        ["git", "-C", str(repo_root), "merge-base", trusted_revision, head_sha],
        check=False,
        capture_output=True,
        text=True,
    )
    merge_base = proc.stdout.strip()
    if proc.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", merge_base):
        raise LaneBindingError("ATTESTATION_MERGE_BASE_UNAVAILABLE")
    entries = _diff_entries(repo_root, base_sha, head_sha)
    entries.update(_diff_entries(repo_root, merge_base, head_sha))
    if not entries:
        raise LaneBindingError("ATTESTATION_CHANGED_PATHS_EMPTY")
    _reject_unsafe_paths(repo_root, entries, trusted_revision, head_sha)
    return sorted(entries)


def _bound_issue_numbers(body: Any, binding: Mapping[str, Any]) -> set[int]:
    issues: set[int] = set()
    if isinstance(binding.get("issue_number"), int):
        issues.add(binding["issue_number"])
    text = body if isinstance(body, str) else ""
    for match in re.finditer(r"<!--\s*NEXUS_CORE_ISSUE:\s*([1-9][0-9]*)\s*-->", text):
        issues.add(int(match.group(1)))
    return issues


def verify_owner_attestation(
    envelope: Mapping[str, Any],
    *,
    repository: str,
    owner_id: str,
    agent_login: str,
    bound_issues: set[int],
    changed_paths: Sequence[str],
    pinned_keys: Mapping[str, str],
    now: datetime,
) -> dict[str, Any]:
    """Check one Owner-signed grant against the exact PR it is attached to."""
    if set(envelope) != {"payload", "key_id", "signature"}:
        raise LaneBindingError("ATTESTATION_FIELDS_INVALID")
    if not pinned_keys:
        raise LaneBindingError("OWNER_SIGNING_KEY_NOT_CONFIGURED")
    key_id = _sha(envelope.get("key_id"), "ATTESTATION_KEY_ID", size=64)
    pem = pinned_keys.get(key_id)
    if pem is None:
        raise LaneBindingError("ATTESTATION_KEY_NOT_PINNED")
    try:
        signature = base64.b64decode(
            _exact_str(envelope.get("signature"), "ATTESTATION_SIGNATURE"), validate=True
        )
    except ValueError as exc:
        raise LaneBindingError("ATTESTATION_SIGNATURE_ENCODING_INVALID") from exc
    payload = _exact_dict(envelope.get("payload"), "ATTESTATION_PAYLOAD")
    if not verify_p256_signature(pem, canonical_attestation_bytes(payload), signature):
        raise LaneBindingError("ATTESTATION_SIGNATURE_INVALID")

    expected_fields = {
        "schema",
        "repository",
        "owner_id",
        "agent_login",
        "issue_number",
        "allowed_actions",
        "allowed_paths",
        "issued_at",
        "expires_at",
        "nonce",
    }
    if set(payload) != expected_fields or payload.get("schema") != ATTESTATION_SCHEMA:
        raise LaneBindingError("ATTESTATION_PAYLOAD_SCHEMA_INVALID")
    if _exact_str(payload.get("repository"), "ATTESTATION_REPOSITORY") != repository:
        raise LaneBindingError("ATTESTATION_REPOSITORY_MISMATCH")
    if _exact_str(payload.get("owner_id"), "ATTESTATION_OWNER_ID") != owner_id:
        raise LaneBindingError("ATTESTATION_OWNER_MISMATCH")
    if _exact_str(payload.get("agent_login"), "ATTESTATION_AGENT_LOGIN").lower() != (
        agent_login.lower()
    ):
        raise LaneBindingError("ATTESTATION_AGENT_MISMATCH")
    issue = _exact_int(payload.get("issue_number"), "ATTESTATION_ISSUE_NUMBER")
    if issue not in bound_issues:
        raise LaneBindingError("ATTESTATION_ISSUE_NOT_BOUND_TO_PR")
    actions = payload.get("allowed_actions")
    # The signer prompt shows these names verbatim, so anything it could not
    # show exactly (a non-string, a duplicate, an empty list) is refused.
    if (
        type(actions) is not list
        or not actions
        or len(actions) > ATTESTATION_MAX_ACTIONS
        or not all(type(a) is str and ATTESTATION_ACTION.fullmatch(a) for a in actions)
        or len(set(actions)) != len(actions)
    ):
        raise LaneBindingError("ATTESTATION_ACTIONS_INVALID")
    if "GITHUB_MERGE" not in actions:
        raise LaneBindingError("ATTESTATION_MERGE_NOT_GRANTED")
    patterns = payload.get("allowed_paths")
    if (
        not isinstance(patterns, list)
        or not patterns
        or len(patterns) > ATTESTATION_MAX_PATHS
        or not all(isinstance(p, str) and len(p) <= ATTESTATION_MAX_PATH_LENGTH for p in patterns)
    ):
        raise LaneBindingError("ATTESTATION_PATHS_INVALID")
    for pattern in patterns:
        _glob_regex(pattern)
        # A grant names a part of the tree; it never starts with a wildcard.
        if any(char in pattern.split("/", 1)[0] for char in "*?"):
            raise LaneBindingError("ATTESTATION_PATH_TOO_BROAD")
    _safe_id(payload.get("nonce"), "ATTESTATION_NONCE")
    issued_at = _parse_utc(payload.get("issued_at"), "ATTESTATION_ISSUED_AT")
    expires_at = _parse_utc(payload.get("expires_at"), "ATTESTATION_EXPIRES_AT")
    if expires_at <= issued_at or expires_at - issued_at > ATTESTATION_MAX_LIFETIME:
        raise LaneBindingError("ATTESTATION_LIFETIME_INVALID")
    if now + ATTESTATION_CLOCK_SKEW < issued_at:
        raise LaneBindingError("ATTESTATION_NOT_YET_VALID")
    if now >= expires_at:
        raise LaneBindingError("ATTESTATION_EXPIRED")
    for path in changed_paths:
        if _path_matches(path, ATTESTATION_PROTECTED_PATTERNS, casefold=True):
            raise LaneBindingError(f"ATTESTATION_PROTECTED_PATH:{path}")
        if not _path_matches(path, patterns):
            raise LaneBindingError(f"ATTESTATION_PATH_OUT_OF_SCOPE:{path}")
    return {
        "schema": "nexus.owner_attestation_check.v1",
        "status": "PASS",
        "key_id": key_id,
        "agent_login": agent_login,
        "issue_number": issue,
        "payload_sha256": hashlib.sha256(canonical_attestation_bytes(payload)).hexdigest(),
        "expires_at": expires_at.isoformat(),
        "changed_path_count": len(changed_paths),
    }


def validate_event(
    event: Mapping[str, Any],
    *,
    repo_root: Path,
    enforcement_start_pr_number: int = ENFORCEMENT_START_PR_NUMBER,
    legacy_pr_heads: Mapping[int, str] = LEGACY_PR_HEAD_ALLOWLIST,
    now: datetime | None = None,
) -> dict[str, Any]:
    result = _validate_lane_event(
        event,
        repo_root=repo_root,
        enforcement_start_pr_number=enforcement_start_pr_number,
        legacy_pr_heads=legacy_pr_heads,
    )
    root = _exact_dict(event, "EVENT")
    pr = _exact_dict(root.get("pull_request"), "PULL_REQUEST")
    base_sha = _sha(
        _exact_dict(pr.get("base"), "PULL_REQUEST_BASE").get("sha"), "BASE_SHA", size=40
    )
    head_sha = _sha(
        _exact_dict(pr.get("head"), "PULL_REQUEST_HEAD").get("sha"), "HEAD_SHA", size=40
    )
    # Trust configuration comes from the revision the gate runs from, never
    # from the PR's (possibly stale) base.
    trusted_revision = _sha(root.get("workflow_sha"), "TRUSTED_CONFIG_REVISION", size=40)
    agents = load_agent_identities(repo_root, trusted_revision)
    actors: set[str] = set()
    for holder in (pr.get("user"), root.get("sender")):
        if isinstance(holder, Mapping):
            login = holder.get("login")
            if isinstance(login, str):
                actors.add(login.lower())
    agent_actors = sorted(actors & agents)
    if not agent_actors:
        return result
    if len(agent_actors) != 1:
        raise LaneBindingError("ATTESTATION_AGENT_AMBIGUOUS")
    envelope = extract_attestation(pr.get("body"))
    if envelope is None:
        raise LaneBindingError("AGENT_PR_REQUIRES_OWNER_ATTESTATION")
    repository = _exact_str(
        _exact_dict(root.get("repository"), "REPOSITORY").get("full_name"), "REPOSITORY_FULL_NAME"
    )
    owner_id = repository.split("/", 1)[0]
    binding = extract_binding(pr.get("body"))
    attestation = verify_owner_attestation(
        envelope,
        repository=repository,
        owner_id=owner_id,
        agent_login=agent_actors[0],
        bound_issues=_bound_issue_numbers(pr.get("body"), binding),
        changed_paths=_changed_paths(repo_root, base_sha, head_sha, trusted_revision),
        pinned_keys=load_owner_signing_keys(repo_root, trusted_revision, owner_id),
        now=now or datetime.now(timezone.utc),
    )
    return {**result, "owner_attestation": attestation}


def approval_decision(
    event: Mapping[str, Any],
    *,
    repo_root: Path,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Decide whether the approver App may approve the PR's exact head.

    Unlike the per-event lane check, this never looks at who sent the event.
    The approver App reports the result as a check run on ``head.sha``; a new
    push has no such check, so the result can only ever vouch for the exact
    content an Owner-signed grant covers.
    """
    root = _exact_dict(event, "EVENT")
    if root.get("event_name") != "pull_request_target":
        raise LaneBindingError("PULL_REQUEST_TARGET_REQUIRED")
    repository = _exact_str(
        _exact_dict(root.get("repository"), "REPOSITORY").get("full_name"), "REPOSITORY_FULL_NAME"
    )
    owner_id = repository.split("/", 1)[0]
    pr = _exact_dict(root.get("pull_request"), "PULL_REQUEST")
    pr_number = _exact_int(pr.get("number"), "PULL_REQUEST_NUMBER")
    base_sha = _sha(
        _exact_dict(pr.get("base"), "PULL_REQUEST_BASE").get("sha"), "BASE_SHA", size=40
    )
    head_sha = _sha(
        _exact_dict(pr.get("head"), "PULL_REQUEST_HEAD").get("sha"), "HEAD_SHA", size=40
    )
    trusted_revision = _sha(root.get("workflow_sha"), "TRUSTED_CONFIG_REVISION", size=40)
    decision: dict[str, Any] = {
        "schema": "nexus.owner_attestation_approval.v1",
        "pull_request_number": pr_number,
        "head_sha": head_sha,
        "approve": False,
    }
    envelope = extract_attestation(pr.get("body"))
    if envelope is None:
        return {**decision, "reason": "NO_OWNER_ATTESTATION"}
    payload = _exact_dict(envelope.get("payload"), "ATTESTATION_PAYLOAD")
    agent_login = str(payload.get("agent_login") or "").lower()
    if agent_login not in load_agent_identities(repo_root, trusted_revision):
        return {**decision, "reason": "ATTESTATION_AGENT_NOT_REGISTERED"}
    author = pr.get("user")
    author_login = author.get("login") if isinstance(author, Mapping) else None
    if not isinstance(author_login, str) or author_login.lower() != agent_login:
        # Grants are visible in PR bodies; only the granted agent's own PRs qualify.
        return {**decision, "reason": "PR_NOT_AUTHORED_BY_GRANTED_AGENT"}
    binding = extract_binding(pr.get("body"))
    try:
        attestation = verify_owner_attestation(
            envelope,
            repository=repository,
            owner_id=owner_id,
            agent_login=agent_login,
            bound_issues=_bound_issue_numbers(pr.get("body"), binding),
            changed_paths=_changed_paths(repo_root, base_sha, head_sha, trusted_revision),
            pinned_keys=load_owner_signing_keys(repo_root, trusted_revision, owner_id),
            now=now or datetime.now(timezone.utc),
        )
    except LaneBindingError as exc:
        return {**decision, "reason": str(exc)}
    return {
        **decision,
        "approve": True,
        "reason": "OWNER_SIGNED_SCOPE_COVERS_HEAD",
        "owner_attestation": attestation,
    }


def _validate_lane_event(
    event: Mapping[str, Any],
    *,
    repo_root: Path,
    enforcement_start_pr_number: int = ENFORCEMENT_START_PR_NUMBER,
    legacy_pr_heads: Mapping[int, str] = LEGACY_PR_HEAD_ALLOWLIST,
) -> dict[str, Any]:
    root = _exact_dict(event, "EVENT")
    if root.get("event_name") != "pull_request_target":
        raise LaneBindingError("PULL_REQUEST_TARGET_REQUIRED")
    repository_obj = _exact_dict(root.get("repository"), "REPOSITORY")
    repository = _exact_str(repository_obj.get("full_name"), "REPOSITORY_FULL_NAME")
    pr = _exact_dict(root.get("pull_request"), "PULL_REQUEST")
    pr_number = _exact_int(pr.get("number"), "PULL_REQUEST_NUMBER")
    base = _exact_dict(pr.get("base"), "PULL_REQUEST_BASE")
    head = _exact_dict(pr.get("head"), "PULL_REQUEST_HEAD")
    base_sha = _sha(base.get("sha"), "BASE_SHA", size=40)
    head_sha = _sha(head.get("sha"), "HEAD_SHA", size=40)

    if pr_number < enforcement_start_pr_number and legacy_pr_heads.get(pr_number) == head_sha:
        return {
            "schema": "nexus.trusted_merge_lane_gate_result.v1",
            "status": "PASS",
            "reason": "PRE_ENFORCEMENT_PR_COMPATIBILITY",
            "pull_request_number": pr_number,
            "head_sha": head_sha,
        }

    intent_result = validate_issue_closure_intent(pr.get("body"))

    commit_title = pr.get("commit_title")
    if commit_title is None:
        commit_title = pr.get("title")
    commit_message = pr.get("commit_message")
    if commit_message is None:
        commit_message = _candidate_commit_messages(
            repo_root,
            base_sha=base_sha,
            head_sha=head_sha,
        )
    merge_method = pr.get("merge_method") or "squash"

    final_binding = validate_final_merge_intent_binding(
        pr_body=pr.get("body"),
        pr_number=pr_number,
        head_sha=head_sha,
        base_sha=base_sha,
        expected_pr_number=pr_number,
        expected_head_sha=head_sha,
        expected_base_sha=base_sha,
        merge_method=merge_method,
        commit_title=commit_title,
        commit_message=commit_message,
    )

    binding = extract_binding(pr.get("body"))
    if binding.get("schema") != BINDING_SCHEMA:
        raise LaneBindingError("MERGE_LANE_BINDING_SCHEMA_INVALID")
    required_binding_fields = {
        "schema",
        "execution_lane",
        "contract_kind",
        "owner_id",
        "issue_number",
        "task_id",
        "attempt_id",
        "task_card_path",
        "task_card_sha256",
        "owner_lane_rebind",
        "binding_hash",
    }
    if set(binding) != required_binding_fields:
        raise LaneBindingError("MERGE_LANE_BINDING_SCHEMA_FIELDS_INVALID")
    _validate_hash_field(binding, "binding_hash")

    lane = _exact_str(binding.get("execution_lane"), "EXECUTION_LANE")
    if lane not in ALL_LANES:
        raise LaneBindingError("EXECUTION_LANE_UNSUPPORTED")
    contract_kind = _exact_str(binding.get("contract_kind"), "CONTRACT_KIND")
    if contract_kind not in CONTRACT_KINDS:
        raise LaneBindingError("CONTRACT_KIND_UNSUPPORTED")
    owner_id = _validate_owner(repository, binding.get("owner_id"))

    if contract_kind == "OWNER_INLINE":
        if lane not in DIRECT_LANES:
            raise LaneBindingError("OWNER_INLINE_MUST_BE_DIRECT")
        for field in (
            "issue_number",
            "task_id",
            "attempt_id",
            "task_card_path",
            "task_card_sha256",
            "owner_lane_rebind",
        ):
            if binding[field] is not None:
                raise LaneBindingError("OWNER_INLINE_TRACKED_FIELDS_FORBIDDEN")
        closing_issues = [
            item["issue_number"]
            for item in intent_result.get("intents", [])
            if item.get("on_merge") == ON_MERGE_CLOSE
        ]
        # An Owner-inline DIRECT binding cannot silently replace a GOVERNED
        # Task Card that already owns the Issue this PR closes.
        if _active_governed_cards_for_issues(repo_root, base_sha, closing_issues):
            raise LaneBindingError("OWNER_INLINE_CANNOT_REPLACE_GOVERNED_TASK_CARD")
        return {
            "schema": "nexus.trusted_merge_lane_gate_result.v1",
            "status": "PASS",
            "reason": "GENUINE_DIRECT_OWNER_INLINE",
            "pull_request_number": pr_number,
            "head_sha": head_sha,
            "execution_lane": lane,
            "binding_hash": binding["binding_hash"],
            "issue_closure_intent": intent_result,
            "merge_intent_binding": final_binding,
        }

    issue_number = _exact_int(binding.get("issue_number"), "ISSUE_NUMBER")
    task_id = _safe_id(binding.get("task_id"), "TASK_ID")
    attempt_id = _safe_id(binding.get("attempt_id"), "ATTEMPT_ID")
    task_card_path = _task_path(binding.get("task_card_path"))
    task_card_sha256 = _sha(binding.get("task_card_sha256"), "TASK_CARD_SHA256", size=64)

    base_card = _git_show(repo_root, base_sha, task_card_path)
    head_card = _git_show(repo_root, head_sha, task_card_path)
    if base_card != head_card:
        raise LaneBindingError("TASK_CARD_CHANGED_DURING_MERGE_ATTEMPT")
    actual_card_hash = hashlib.sha256(base_card).hexdigest()
    if actual_card_hash != task_card_sha256:
        raise LaneBindingError("TASK_CARD_SHA256_MISMATCH")
    card_task_id, card_lane, card_attempt_id = _task_card_metadata(base_card)
    if card_task_id != task_id:
        raise LaneBindingError("TASK_CARD_TASK_ID_MISMATCH")
    if card_attempt_id is not None and card_attempt_id != attempt_id:
        raise LaneBindingError("TASK_CARD_ATTEMPT_ID_MISMATCH")

    if lane == "GOVERNED":
        if card_lane != "GOVERNED":
            raise LaneBindingError("GOVERNED_BINDING_REQUIRES_GOVERNED_CARD")
        if binding["owner_lane_rebind"] is not None:
            raise LaneBindingError("GOVERNED_BINDING_REBIND_FORBIDDEN")
        return {
            "schema": "nexus.trusted_merge_lane_gate_result.v1",
            "status": "PASS",
            "reason": "GOVERNED_LANE_UNCHANGED",
            "pull_request_number": pr_number,
            "head_sha": head_sha,
            "execution_lane": lane,
            "binding_hash": binding["binding_hash"],
            "issue_closure_intent": intent_result,
            "merge_intent_binding": final_binding,
        }

    if card_lane == lane:
        if binding["owner_lane_rebind"] is not None:
            raise LaneBindingError("DIRECT_ORIGIN_REBIND_FORBIDDEN")
        return {
            "schema": "nexus.trusted_merge_lane_gate_result.v1",
            "status": "PASS",
            "reason": "TRACKED_TASK_BEGAN_DIRECT",
            "pull_request_number": pr_number,
            "head_sha": head_sha,
            "execution_lane": lane,
            "binding_hash": binding["binding_hash"],
            "issue_closure_intent": intent_result,
            "merge_intent_binding": final_binding,
        }

    if card_lane != "GOVERNED":
        raise LaneBindingError("DIRECT_REBIND_REQUIRES_GOVERNED_CARD")
    _validate_rebind(
        binding["owner_lane_rebind"],
        repository=repository,
        issue_number=issue_number,
        task_id=task_id,
        attempt_id=attempt_id,
        task_card_path=task_card_path,
        task_card_sha256=task_card_sha256,
        pull_request_number=pr_number,
        head_sha=head_sha,
        requested_lane=lane,
        owner_id=owner_id,
    )
    sender = root.get("sender")
    if not isinstance(sender, Mapping) or sender.get("login") != owner_id:
        # The rebind record is an unkeyed self-hash; only the Owner acting on
        # the PR event can make it an Owner decision.
        raise LaneBindingError("OWNER_LANE_REBIND_SENDER_NOT_OWNER")
    return {
        "schema": "nexus.trusted_merge_lane_gate_result.v1",
        "status": "PASS",
        "reason": "OWNER_GOVERNED_TO_DIRECT_REBIND_VALID",
        "pull_request_number": pr_number,
        "head_sha": head_sha,
        "execution_lane": lane,
        "binding_hash": binding["binding_hash"],
        "issue_closure_intent": intent_result,
        "merge_intent_binding": final_binding,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--event-json", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--mode", choices=("gate", "approve"), default="gate")
    args = parser.parse_args()
    event = json.loads(Path(args.event_json).read_text(encoding="utf-8"))
    if args.mode == "approve":
        # Never raises into a red check: the approver only acts on approve=true.
        try:
            decision = approval_decision(event, repo_root=Path(args.repo_root))
        except LaneBindingError as exc:
            decision = {
                "schema": "nexus.owner_attestation_approval.v1",
                "approve": False,
                "reason": str(exc),
            }
        except Exception as exc:  # noqa: BLE001 - any failure is simply "not approved"
            decision = {
                "schema": "nexus.owner_attestation_approval.v1",
                "approve": False,
                "reason": f"APPROVAL_DECISION_ERROR:{type(exc).__name__}",
            }
        print(json.dumps(decision, sort_keys=True))
        return
    try:
        result = validate_event(event, repo_root=Path(args.repo_root))
    except LaneBindingError as exc:
        print(
            json.dumps(
                {
                    "schema": "nexus.trusted_merge_lane_gate_result.v1",
                    "status": "BLOCK",
                    "reason": str(exc),
                },
                sort_keys=True,
            )
        )
        raise SystemExit(1) from exc
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
