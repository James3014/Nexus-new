from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, TypedDict

SCHEMA = "owner_learning.current_state.v1"
CURRENT_HEADING = "## Current Learning State — bounded bootstrap projection"
PRIORITIES_HEADING = "### Current priority frontiers — maximum three"
DOMAIN_HEADING = "### Domain-level mastery view"
ALLOWED_LEVELS = {"UNASSESSED", "L0", "L1", "L2", "L3", "L4"}
EVENT_ID_RE = re.compile(r"^###\s+(LA-\d{8}-\d{3})\b", re.MULTILINE)


class LedgerContractError(ValueError):
    """Raised when the Owner Learning Ledger violates the projection contract."""


class DomainRecord(TypedDict):
    domain: str
    level: str
    evidence_boundary: str
    next_case: str


class Projection(TypedDict):
    schema: str
    source: str
    source_sha256: str
    priorities: list[str]
    domains: list[DomainRecord]


@dataclass(frozen=True)
class DomainState:
    domain: str
    level: str
    evidence_boundary: str
    next_case: str

    def as_dict(self) -> DomainRecord:
        return {
            "domain": self.domain,
            "level": self.level,
            "evidence_boundary": self.evidence_boundary,
            "next_case": self.next_case,
        }


def _find_unique_section(text: str, heading: str, next_prefix: str = "## ") -> str:
    occurrences = [m.start() for m in re.finditer(re.escape(heading), text)]
    if len(occurrences) != 1:
        raise LedgerContractError(f"expected exactly one {heading!r}; found {len(occurrences)}")
    start = occurrences[0]
    line_end = text.find("\n", start)
    if line_end == -1:
        return ""
    body_start = line_end + 1
    next_match = re.search(rf"(?m)^{re.escape(next_prefix)}(?!#)", text[body_start:])
    if next_match is None:
        return text[body_start:]
    return text[body_start : body_start + next_match.start()]


def _subsection(section: str, heading: str) -> str:
    occurrences = [m.start() for m in re.finditer(re.escape(heading), section)]
    if len(occurrences) != 1:
        raise LedgerContractError(
            f"expected exactly one {heading!r} inside Current Learning State; "
            f"found {len(occurrences)}"
        )
    start = occurrences[0]
    line_end = section.find("\n", start)
    if line_end == -1:
        return ""
    body_start = line_end + 1
    next_match = re.search(r"(?m)^###\s+", section[body_start:])
    if next_match is None:
        return section[body_start:]
    return section[body_start : body_start + next_match.start()]


def _parse_priorities(section: str) -> list[str]:
    body = _subsection(section, PRIORITIES_HEADING)
    priorities: list[str] = []
    for line in body.splitlines():
        match = re.match(r"^\s*(\d+)\.\s+\*\*(.+?)\*\*(?:\s+—\s+.*)?$", line)
        if match:
            priorities.append(match.group(2).strip())
    if not priorities:
        raise LedgerContractError("Current Learning State has no parsed priorities")
    if len(priorities) > 3:
        raise LedgerContractError(
            f"Current Learning State has {len(priorities)} priorities; maximum is 3"
        )
    return priorities


def _parse_markdown_row(line: str) -> list[str]:
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|")):
        return []
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _parse_domains(section: str) -> list[DomainState]:
    body = _subsection(section, DOMAIN_HEADING)
    rows: list[DomainState] = []
    for line in body.splitlines():
        cells = _parse_markdown_row(line)
        if len(cells) != 4:
            continue
        if cells[0] == "Architecture domain" or set(cells[0]) <= {"-", ":"}:
            continue
        if cells[1] not in ALLOWED_LEVELS:
            raise LedgerContractError(
                f"unsupported mastery level {cells[1]!r} for domain {cells[0]!r}"
            )
        rows.append(DomainState(*cells))
    if not rows:
        raise LedgerContractError("Current Learning State has no parsed architecture domains")
    names = [row.domain for row in rows]
    if len(names) != len(set(names)):
        raise LedgerContractError("Current Learning State contains duplicate domain rows")
    return rows


def _event_ids(text: str) -> list[str]:
    return EVENT_ID_RE.findall(text)


def _ensure_unique_event_ids(text: str) -> None:
    ids = _event_ids(text)
    duplicates = sorted({event_id for event_id in ids if ids.count(event_id) > 1})
    if duplicates:
        raise LedgerContractError("duplicate learning-event IDs: " + ", ".join(duplicates))


def build_projection(text: str, *, source: str) -> Projection:
    """Project reviewed Ledger state without inferring mastery from prose."""

    _ensure_unique_event_ids(text)
    current = _find_unique_section(text, CURRENT_HEADING)
    priorities = _parse_priorities(current)
    domains = _parse_domains(current)
    return {
        "schema": SCHEMA,
        "source": source,
        "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "priorities": priorities,
        "domains": [row.as_dict() for row in domains],
    }


def projection_json(text: str, *, source: str) -> str:
    return json.dumps(
        build_projection(text, source=source),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def load_projection(path: Path) -> Projection:
    text = path.read_text(encoding="utf-8")
    return build_projection(text, source=path.as_posix())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and project the reviewed bounded Current Learning State "
            "from the canonical Owner Learning Ledger. No mastery inference."
        )
    )
    parser.add_argument(
        "ledger",
        nargs="?",
        default="docs/learning/OWNER_ENGINEERING_LEARNING_LEDGER.md",
        help="Path to the canonical Owner Learning Ledger",
    )
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    path = Path(args.ledger)
    try:
        projection = load_projection(path)
    except (OSError, LedgerContractError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(
        json.dumps(
            {"ok": True, "projection": projection},
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
