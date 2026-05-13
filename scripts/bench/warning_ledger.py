from __future__ import annotations

import re
import traceback
import warnings
import hashlib
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator


WARNING_LINE_RE = re.compile(r"(?P<location>[^:\n]+:\d+:\s*)?(?P<category>[A-Za-z]+Warning):\s*(?P<message>.+)")


@dataclass(frozen=True)
class WarningRecord:
    source: str
    category: str
    message: str
    line: str
    filename: str = ""
    lineno: int | None = None
    location: str = ""
    emitter: str = ""

    @property
    def source_resolved(self) -> bool:
        return bool(self.filename) and self.filename != "<unknown>" and self.lineno is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "category": self.category,
            "message": self.message,
            "line": self.line,
            "filename": self.filename,
            "lineno": self.lineno,
            "location": self.location,
            "emitter": self.emitter,
            "source_resolved": self.source_resolved,
        }


def _parse_location(location: str | None) -> tuple[str, int | None, str]:
    value = str(location or "").strip()
    if value.endswith(":"):
        value = value[:-1].strip()
    if not value:
        return "", None, ""
    filename, _, lineno_text = value.rpartition(":")
    try:
        lineno = int(lineno_text)
    except ValueError:
        return value, None, value
    return filename, lineno, f"{filename}:{lineno}"


def records_from_text(text: str, *, source: str) -> list[WarningRecord]:
    records: list[WarningRecord] = []
    offset = 0
    for line in str(text or "").splitlines():
        match = WARNING_LINE_RE.search(line)
        line_offset = offset
        offset += len(line) + 1
        if not match:
            continue
        filename, lineno, location = _parse_location(match.group("location"))
        clean_line = line.strip()
        records.append(
            WarningRecord(
                source=source,
                category=match.group("category"),
                message=match.group("message").strip(),
                line=clean_line,
                filename=filename,
                lineno=lineno,
                location=location,
                emitter=f"raw_stream:{line_offset}:{hashlib.sha256(clean_line.encode('utf-8')).hexdigest()}",
            )
        )
    return records


def records_from_warnings(caught: list[warnings.WarningMessage], *, source: str) -> list[WarningRecord]:
    records: list[WarningRecord] = []
    for item in caught:
        category = item.category.__name__
        message = str(item.message)
        filename = str(item.filename or "")
        lineno = int(item.lineno) if item.lineno is not None else None
        location = f"{filename}:{lineno}" if filename and lineno is not None else ""
        line = f"{location}: {category}: {message}" if location else f"{category}: {message}"
        records.append(
            WarningRecord(
                source=source,
                category=category,
                message=message,
                line=line,
                filename=filename,
                lineno=lineno,
                location=location,
            )
        )
    return records


def _caller_hint(stack: list[traceback.FrameSummary]) -> str:
    for frame in reversed(stack):
        filename = str(frame.filename or "")
        if not filename:
            continue
        if "/lib/python" in filename or "/site-packages/" in filename:
            continue
        if filename.endswith("/warnings.py") or filename.endswith("warnings.py"):
            continue
        if filename.endswith("/warning_ledger.py") or filename.endswith("warning_ledger.py"):
            continue
        return f"{filename}:{frame.lineno}:{frame.name}"
    return ""


def summarize(records: list[WarningRecord]) -> dict[str, Any]:
    lines = [record.line for record in records]
    sources = sorted({record.source for record in records if record.source})
    categories = sorted({record.category for record in records if record.category})
    unknown_count = sum(1 for record in records if not record.source or record.source == "unknown")
    unresolved_count = sum(1 for record in records if not record.source_resolved)
    source_resolved_rate = round((len(records) - unresolved_count) / len(records), 4) if records else 1.0
    locations = sorted({record.location for record in records if record.location})
    filenames = sorted({record.filename for record in records if record.filename})
    linenos = sorted({record.lineno for record in records if record.lineno is not None})
    emitters = sorted({record.emitter for record in records if record.emitter})
    return {
        "schema": "nexus_warning_ledger_v1",
        "warning_clean": not records,
        "warning_capture_status": "captured",
        "warning_capture_complete": unknown_count == 0,
        "warning_lines": lines,
        "warning_records": [record.as_dict() for record in records],
        "warning_locations": locations,
        "warning_filenames": filenames,
        "warning_linenos": linenos,
        "warning_emitters": emitters,
        "warning_source_resolved_rate": source_resolved_rate,
        "unresolved_warning_count": unresolved_count,
        "warning_sources": sources,
        "warning_categories": categories,
        "warning_reason_codes": [f"{record.source}:{record.category}" for record in records],
        "uncaptured_warning_count": unknown_count,
    }


def annotate_row(row: dict[str, Any], records: list[WarningRecord], *, append: bool = False) -> dict[str, Any]:
    if append:
        existing_source = str((row.get("warning_sources") or ["existing"])[0] if row.get("warning_sources") else "existing")
        existing = [*records_from_text("\n".join(row.get("warning_lines") or []), source=existing_source)]
        records = existing + records
    summary = summarize(records)
    row["warning_ledger"] = summary
    row["warning_clean"] = summary["warning_clean"]
    row["warning_capture_status"] = summary["warning_capture_status"]
    row["warning_capture_complete"] = summary["warning_capture_complete"]
    row["warning_lines"] = summary["warning_lines"]
    row["warning_records"] = summary["warning_records"]
    row["warning_locations"] = summary["warning_locations"]
    row["warning_filenames"] = summary["warning_filenames"]
    row["warning_linenos"] = summary["warning_linenos"]
    row["warning_emitters"] = summary["warning_emitters"]
    row["warning_source_resolved_rate"] = summary["warning_source_resolved_rate"]
    row["unresolved_warning_count"] = summary["unresolved_warning_count"]
    row["warning_sources"] = summary["warning_sources"]
    row["warning_categories"] = summary["warning_categories"]
    row["warning_reason_codes"] = summary["warning_reason_codes"]
    row["uncaptured_warning_count"] = summary["uncaptured_warning_count"]
    return row


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    row_count = len(rows)
    captured_rows = [row for row in rows if str(row.get("warning_capture_status") or "") == "captured"]
    dirty_rows = [row for row in rows if bool(row.get("warning_lines")) or bool(row.get("uncaptured_warning_count"))]
    incomplete_rows = [row for row in rows if row.get("warning_capture_complete") is False]
    unresolved_count = sum(int(row.get("unresolved_warning_count", 0) or 0) for row in rows)
    warning_count = sum(len(row.get("warning_lines") or []) for row in rows)
    source_resolved_rate = round((warning_count - unresolved_count) / warning_count, 4) if warning_count else 1.0
    return {
        "schema": "nexus_warning_ledger_bundle_v1",
        "row_count": row_count,
        "captured_row_count": len(captured_rows),
        "warning_clean_row_count": row_count - len(dirty_rows),
        "warning_dirty_row_count": len(dirty_rows),
        "warning_capture_completeness": round(len(captured_rows) / row_count, 4) if row_count else 1.0,
        "uncaptured_warning_count": sum(int(row.get("uncaptured_warning_count", 0) or 0) for row in rows),
        "unresolved_warning_count": unresolved_count,
        "warning_source_resolved_rate": source_resolved_rate,
        "warning_lines": [line for row in rows for line in (row.get("warning_lines") or [])],
        "warning_records": [record for row in rows for record in (row.get("warning_records") or [])],
        "warning_locations": sorted({location for row in rows for location in (row.get("warning_locations") or [])}),
        "warning_filenames": sorted({filename for row in rows for filename in (row.get("warning_filenames") or [])}),
        "warning_linenos": sorted({lineno for row in rows for lineno in (row.get("warning_linenos") or [])}),
        "warning_emitters": sorted({emitter for row in rows for emitter in (row.get("warning_emitters") or [])}),
        "warning_sources": sorted({source for row in rows for source in (row.get("warning_sources") or [])}),
        "warning_categories": sorted({category for row in rows for category in (row.get("warning_categories") or [])}),
        "incomplete_row_count": len(incomplete_rows),
        "warning_clean": not dirty_rows and not incomplete_rows,
    }


@contextmanager
def capture_python_warnings(*, source: str) -> Iterator[list[WarningRecord]]:
    records: list[WarningRecord] = []
    with warnings.catch_warnings():
        def capture_showwarning(
            message: warnings.WarningMessage | Warning | str,
            category: type[Warning],
            filename: str,
            lineno: int,
            file: Any = None,
            line: str | None = None,
        ) -> None:
            category_name = category.__name__
            text = str(message)
            location = f"{filename}:{lineno}" if filename and lineno is not None else ""
            records.append(
                WarningRecord(
                    source=source,
                    category=category_name,
                    message=text,
                    line=f"{location}: {category_name}: {text}" if location else f"{category_name}: {text}",
                    filename=str(filename or ""),
                    lineno=int(lineno) if lineno is not None else None,
                    location=location,
                    emitter=_caller_hint(traceback.extract_stack(limit=16)),
                )
            )

        warnings.showwarning = capture_showwarning
        warnings.simplefilter("always")
        yield records
