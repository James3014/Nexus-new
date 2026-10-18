"""Trusted default-branch merge-lane binding gate for protected pull requests."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
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
CONTRACT_KINDS = {"OWNER_INLINE", "AGENT_INLINE", "TRACKED_TASK_CARD"}
INLINE_CONTRACT_KINDS = frozenset({"OWNER_INLINE", "AGENT_INLINE"})
# GitHub App bot accounts allowed to author AGENT_INLINE direct PRs. An App
# opens PRs as ``<slug>[bot]`` (``app/<slug>`` in the gh CLI). Since 2026-10-13
# agents act as this App, so they can no longer claim the Owner's identity.
AGENT_APP_LOGINS = frozenset({"james3014-nexus-agent[bot]"})
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
    # GitHub also accepts a colon after the keyword ("Fixes: #N") and the GH-N alias (#2589).
    + r")(?:\s*:\s*|\s+)(?:https?://github\.com/[^/\s]+/[^/\s]+/issues/|(?:\b[a-zA-Z0-9._-]+/[a-zA-Z0-9._-]+)?#|\bGH-)(\d+)\b"
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


def _blank_markers_keep_lines(body: Any) -> str:
    """``strip_markers`` with each removed block replaced by its newlines, so line
    numbers still match the PR body as written (#2589)."""
    if type(body) is not str:
        return ""
    text = body
    for start_marker, end_marker in (
        (INTENT_START_MARKER, INTENT_END_MARKER),
        (START_MARKER, END_MARKER),
    ):
        if start_marker in text and end_marker in text:
            start = text.index(start_marker)
            end = text.index(end_marker, start) + len(end_marker)
            text = text[:start] + "\n" * text[start:end].count("\n") + text[end:]
    return text


def _closing_keyword_location(text: str, issue: int, label: str) -> str:
    """Name the first line of ``text`` that closes ``issue`` (#2589)."""
    for index, line in enumerate(text.splitlines(), start=1):
        if any(num == issue for _kw, num in find_closing_keyword_references(line)):
            excerpt = " ".join(line.split())[:100]
            return f"{label} line {index}: '{excerpt}'"
    return label


def _final_fields_location(title: str, message: str, issue: int) -> str:
    if any(num == issue for _kw, num in find_closing_keyword_references(title)):
        return _closing_keyword_location(title, issue, "PR title")
    return _closing_keyword_location(message, issue, "commit messages")


def _closing_remedy(issue: int) -> str:
    return f"reword it to 'Refs #{issue}'"


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
        first = min(untracked_issues)
        where = _closing_keyword_location(_blank_markers_keep_lines(body), first, "PR body")
        culprits = ", ".join(
            f"#{num} ({', '.join(detected_by_issue[num])})" for num in sorted(untracked_issues)
        )
        raise IssueClosureIntentError(
            f"UNINTENDED_CLOSING_KEYWORD_FOR_UNTRACKED_ISSUE: {where} would close #{first}, "
            f"which has no NEXUS_ISSUE_INTENT_V1 entry; {_closing_remedy(first)}. "
            f"PR prose contains GitHub closing keywords targeting {culprits}. "
            "Declare intent in <!-- NEXUS_ISSUE_INTENT_V1 or rephrase using neutral prose (e.g. '#X remains open')."
        )

    for issue_num, action in intent_by_issue.items():
        if action == ON_MERGE_KEEP_OPEN:
            if issue_num in detected_by_issue:
                kws = ", ".join(detected_by_issue[issue_num])
                where = _closing_keyword_location(
                    _blank_markers_keep_lines(body), issue_num, "PR body"
                )
                raise IssueClosureIntentError(
                    f"REJECTED_CLOSING_KEYWORD_FOR_KEEP_OPEN: {where} would close #{issue_num} "
                    f"(intent KEEP_OPEN); {_closing_remedy(issue_num)}. PR prose contains closing keyword '{kws}' targeting #{issue_num}, "
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
        first = min(untracked_issues)
        where = _final_fields_location(commit_title or "", commit_message or "", first)
        culprits = ", ".join(
            f"#{num} ({', '.join(detected_in_final[num])})" for num in sorted(untracked_issues)
        )
        raise IssueClosureIntentError(
            f"UNINTENDED_CLOSING_KEYWORD_FOR_UNTRACKED_ISSUE: {where} would close #{first}, "
            f"which has no NEXUS_ISSUE_INTENT_V1 entry; {_closing_remedy(first)}. "
            f"Final merge fields contain GitHub closing keywords targeting {culprits}. "
            "Remove closing keywords or declare explicit intent in PR body."
        )

    for issue_num, action in intent_by_issue.items():
        if action == ON_MERGE_KEEP_OPEN:
            if issue_num in detected_in_final:
                kws = ", ".join(detected_in_final[issue_num])
                where = _final_fields_location(commit_title or "", commit_message or "", issue_num)
                raise IssueClosureIntentError(
                    f"REJECTED_CLOSING_KEYWORD_FOR_KEEP_OPEN_IN_FINAL_MERGE_FIELDS: {where} would close "
                    f"#{issue_num} (intent KEEP_OPEN); {_closing_remedy(issue_num)}. Final merge commit fields contain closing keyword '{kws}' targeting #{issue_num}, "
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


def _pull_request_author(pr: Mapping[str, Any]) -> tuple[str, bool]:
    """Return ``(login, is_app)`` for the PR author from the trusted event."""
    user = pr.get("user")
    if not isinstance(user, Mapping):
        raise LaneBindingError("PULL_REQUEST_AUTHOR_REQUIRED")
    login = _exact_str(user.get("login"), "PULL_REQUEST_AUTHOR_LOGIN")
    is_app = user.get("type") == "Bot" or login.endswith("[bot]") or login.startswith("app/")
    return login, is_app


def _author_identity(login: str, is_app: bool) -> str:
    if not is_app:
        return login
    if login.startswith("app/"):
        return login
    return "app/" + login.removesuffix("[bot]")


def _validate_inline_author(
    contract_kind: str, *, owner_id: str, author_login: str, author_is_app: bool
) -> None:
    if contract_kind == "OWNER_INLINE":
        # Only the Owner's own account may claim an Owner-inline binding; an
        # App/agent (or any other account) must not borrow the Owner identity.
        if author_is_app or author_login != owner_id:
            raise LaneBindingError("OWNER_INLINE_AUTHOR_MISMATCH")
        return
    agent_login = author_login
    if agent_login.startswith("app/"):
        agent_login = agent_login.removeprefix("app/") + "[bot]"
    if not author_is_app or agent_login not in AGENT_APP_LOGINS:
        raise LaneBindingError("AGENT_INLINE_AUTHOR_NOT_ALLOWLISTED_APP")


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


def validate_event(
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

    if contract_kind in INLINE_CONTRACT_KINDS:
        if lane not in DIRECT_LANES:
            raise LaneBindingError(f"{contract_kind}_MUST_BE_DIRECT")
        for field in (
            "issue_number",
            "task_id",
            "attempt_id",
            "task_card_path",
            "task_card_sha256",
            "owner_lane_rebind",
        ):
            if binding[field] is not None:
                raise LaneBindingError(f"{contract_kind}_TRACKED_FIELDS_FORBIDDEN")
        author_login, author_is_app = _pull_request_author(pr)
        _validate_inline_author(
            contract_kind,
            owner_id=owner_id,
            author_login=author_login,
            author_is_app=author_is_app,
        )
        closing_issues = [
            item["issue_number"]
            for item in intent_result.get("intents", [])
            if item.get("on_merge") == ON_MERGE_CLOSE
        ]
        # An inline DIRECT binding cannot silently replace a GOVERNED Task
        # Card that already owns the Issue this PR closes.
        if _active_governed_cards_for_issues(repo_root, base_sha, closing_issues):
            raise LaneBindingError(f"{contract_kind}_CANNOT_REPLACE_GOVERNED_TASK_CARD")
        return {
            "schema": "nexus.trusted_merge_lane_gate_result.v1",
            "status": "PASS",
            "reason": f"GENUINE_DIRECT_{contract_kind}",
            "pull_request_number": pr_number,
            "head_sha": head_sha,
            "execution_lane": lane,
            "contract_kind": contract_kind,
            "author_identity": _author_identity(author_login, author_is_app),
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
    args = parser.parse_args()
    event = json.loads(Path(args.event_json).read_text(encoding="utf-8"))
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
