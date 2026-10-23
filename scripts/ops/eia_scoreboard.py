#!/usr/bin/env python3
"""Read-only scoreboard for External Intelligence Automation (EIA) runs.

Emits one record per automation run identity (one ``issue-<N>-<identity>.json``
state file) so the owner gets a report card: success rate, failing stage,
duration, models seen.  Standard library only; never writes to the state root.

Linking (automation state -> evidence):
  * effect id -> ``<repo>/intelligence/attempts/<effect>.json`` (semantic window)
    and ``<repo>/intelligence/requests/<effect>.json`` (revision, main sha).
  * semantic operation -> operations of kind ``semantic`` whose ``started_at``
    falls inside the intelligence attempt window.  Zero or several candidates
    are reported in ``link_notes`` instead of guessed.
  * fanout attempt -> ``fanout/attempts/*.json`` whose ``envelope_ref`` file name
    is the effect id; worker operation -> attempt ``operation_id``.
  * closure -> verifications / acceptance packets keyed by ``task_id``; attached
    only to the run that owns the task (publication task id, or the sole run of
    that task that reached closure).
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_STATE_ROOT = "~/Workspace/nexus-self-hosted-state/external-intelligence/state"
DEFAULT_FAILURE_LOG = "~/.local/share/nexus-open-swe-runtime/logs/opencli-failures.log"
STAGES = (
    "preflight",
    "semantic",
    "fanout_dispatch",
    "worker",
    "unit_verify",
    "whole_verify",
    "publication",
    "acceptance",
)
NOT_MEASURED = "NOT_MEASURED"
_LOG_HEAD = re.compile(r"^=== (\S+) rc=(\S+) cmd=(\S+)")
_LOG_CODE = re.compile(r"^\s+code:\s*(\S+)")
WINDOW_SLACK_SECONDS = 5.0


def _parse_ts(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Loader:
    """Tolerant read-only JSON loader that counts unreadable files."""

    def __init__(self) -> None:
        self.unreadable: list[str] = []

    def load(self, path: Path) -> dict[str, Any] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.unreadable.append(str(path))
            return None
        return value if isinstance(value, dict) else None

    def load_dir(self, directory: Path) -> list[tuple[Path, dict[str, Any]]]:
        rows: list[tuple[Path, dict[str, Any]]] = []
        if not directory.is_dir():
            return rows
        for path in sorted(directory.glob("*.json")):
            value = self.load(path)
            if value is not None:
                rows.append((path, value))
        return rows


def parse_failure_log(path: Path | None) -> list[dict[str, Any]]:
    """Parse ``=== <ts> rc=<n> cmd=<sub>`` entries and their error code."""
    if path is None or not path.is_file():
        return []
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for line in lines:
        head = _LOG_HEAD.match(line)
        if head:
            current = {
                "ts": _parse_ts(head.group(1)),
                "rc": head.group(2),
                "cmd": head.group(3),
                "code": "UNKNOWN",
            }
            entries.append(current)
            continue
        if current is not None and current["code"] == "UNKNOWN":
            code = _LOG_CODE.match(line)
            if code:
                current["code"] = code.group(1)
    return [e for e in entries if e["ts"] is not None]


def _models(receipts: list[dict[str, Any]]) -> tuple[set[str], int]:
    seen: set[str] = set()
    unmeasured = 0
    for receipt in receipts:
        revision = receipt.get("provider_model_revision")
        if isinstance(revision, str) and revision and revision != NOT_MEASURED:
            seen.add(revision)
        else:
            unmeasured += 1
    return seen, unmeasured


def _receipts(op: dict[str, Any]) -> list[dict[str, Any]]:
    rows = op.get("model_invocation_receipts")
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _verification_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    unit = [r for r in rows if r.get("scope") == "UNIT"]
    whole = [r for r in rows if r.get("scope") == "WHOLE_TASK"]
    failed_verifiers: list[str] = []
    failed_checks: list[str] = []
    for row in rows:
        failed_verifiers += [str(x) for x in _list(row.get("failed_verifier_ids"))]
        failed_checks += [str(x) for x in _list(row.get("failed_integrity_check_ids"))]
    return {
        "unit": [str(r.get("status")) for r in unit],
        "whole": [str(r.get("status")) for r in whole],
        "failed_verifiers": sorted(set(failed_verifiers)),
        "failed_checks": sorted(set(failed_checks)),
    }


def collect(
    state_root: Path, failure_log: Path | None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    loader = Loader()
    ops_rows = loader.load_dir(state_root / "open_swe_runtime" / "operations")
    ops_by_id = {str(v.get("operation_id") or p.stem): v for p, v in ops_rows}
    semantic_ops = [v for v in ops_by_id.values() if v.get("kind") == "semantic"]
    log_entries = parse_failure_log(failure_log)
    linked_ops: set[str] = set()

    runs: list[dict[str, Any]] = []
    automation_root = state_root / "automation"
    repo_dirs = (
        sorted(
            d for d in automation_root.iterdir() if d.is_dir() and d.name.startswith("James3014_")
        )
        if automation_root.is_dir()
        else []
    )
    # Automation directory names look like <owner>_<repo>; evidence dirs match.
    for repo_dir in repo_dirs:
        evidence = state_root / repo_dir.name
        attempts_i = {p.stem: v for p, v in loader.load_dir(evidence / "intelligence" / "attempts")}
        requests = {p.stem: v for p, v in loader.load_dir(evidence / "intelligence" / "requests")}
        fanout_attempts = [v for _, v in loader.load_dir(evidence / "fanout" / "attempts")]
        verifications = [v for _, v in loader.load_dir(evidence / "closure" / "verifications")]
        packets = [v for _, v in loader.load_dir(evidence / "closure" / "acceptance-packets")]
        state_rows = []
        for path, value in loader.load_dir(repo_dir):
            m = re.fullmatch(r"issue-(\d+)-([0-9a-f]+)", path.stem)
            if m and str(value.get("schema") or "").startswith(
                "nexus.external_intelligence_automation_state"
            ):
                state_rows.append((path, value, int(m.group(1)), m.group(2)))

        # task ownership of closure artifacts
        def task_of(value: dict[str, Any], attempts: list[dict[str, Any]]) -> str | None:
            pub = value.get("publication")
            if isinstance(pub, dict) and pub.get("task_id"):
                return str(pub["task_id"])
            for attempt in attempts:
                if attempt.get("task_id"):
                    return str(attempt["task_id"])
            return None

        def attempts_for(effect: str | None) -> list[dict[str, Any]]:
            if not effect:
                return []
            return [
                a for a in fanout_attempts if Path(str(a.get("envelope_ref", ""))).stem == effect
            ]

        prepared = []
        for path, value, issue, identity in state_rows:
            effect = value.get("intelligence_effect_id")
            effect = str(effect) if effect else None
            prepared.append((path, value, issue, identity, effect, attempts_for(effect)))
        closure_candidates: dict[str, list[str]] = {}
        for _, value, _, identity, _, atts in prepared:
            task = task_of(value, atts)
            if task and (
                value.get("closure_run_id")
                or str(value.get("prior_state", "")).startswith("CLOSURE")
            ):
                closure_candidates.setdefault(task, []).append(identity)

        for path, value, issue, identity, effect, atts in prepared:
            notes: list[str] = []
            request = requests.get(effect or "", {})
            raw_identity = request.get("identity")
            req_identity: dict[str, Any] = raw_identity if isinstance(raw_identity, dict) else {}
            intel = attempts_i.get(effect or "")
            task_id = task_of(value, atts)
            state = str(value.get("state") or "UNKNOWN")
            error = str(value.get("error") or "")
            events: list[float] = []

            # semantic operations (time-window link)
            sem_ops: list[dict[str, Any]] = []
            if intel:
                for key in ("prepared_at", "dispatching_at", "finished_at"):
                    ts = _parse_ts(intel.get(key))
                    if ts is not None:
                        events.append(ts)
                lo = _parse_ts(intel.get("dispatching_at") or intel.get("prepared_at"))
                hi = _parse_ts(intel.get("finished_at"))
                if lo is not None and hi is not None:
                    cands = [
                        o
                        for o in semantic_ops
                        if (s := _parse_ts(o.get("started_at"))) is not None
                        and lo - WINDOW_SLACK_SECONDS <= s <= hi + WINDOW_SLACK_SECONDS
                    ]
                    if len(cands) == 1:
                        sem_ops = cands
                    elif cands:
                        notes.append(
                            f"semantic_ops_ambiguous({len(cands)} candidates, none counted)"
                        )
                    else:
                        notes.append("semantic_op_not_found")
            elif effect:
                notes.append("intelligence_attempt_missing")

            # worker operations (explicit operation_id link)
            worker_ops: list[dict[str, Any]] = []
            for att in atts:
                op = ops_by_id.get(str(att.get("operation_id")))
                if op is not None:
                    worker_ops.append(op)
                else:
                    notes.append(f"worker_op_missing({str(att.get('operation_id'))[:8]})")
            for op in sem_ops + worker_ops:
                linked_ops.add(str(op.get("operation_id")))
                for key in ("started_at", "finished_at"):
                    ts = _parse_ts(op.get(key))
                    if ts is not None:
                        events.append(ts)

            # closure artifacts (task_id link, only for the owning run)
            owners = closure_candidates.get(task_id or "", [])
            closure_rows: list[dict[str, Any]] = []
            packet: dict[str, Any] | None = None
            if task_id and owners:
                if identity in owners:
                    closure_rows = [v for v in verifications if v.get("task_id") == task_id]
                    found = [p for p in packets if p.get("task_id") == task_id]
                    packet = found[0] if found else None
                elif str(value.get("prior_state", "")).startswith("CLOSURE"):
                    notes.append(f"closure_owner_ambiguous({len(owners)} runs share task)")
            ver = _verification_summary(closure_rows)

            # stage accounting
            done: set[str] = set()
            if effect or state == "COMPLETE":
                done.add("preflight")
            if intel and intel.get("state") == "COMPLETED":
                done.add("semantic")
            if atts:
                done.add("fanout_dispatch")
                if all(a.get("state") == "COMPLETED" for a in atts):
                    done.add("worker")
            if ver["unit"] and all(s == "PASS" for s in ver["unit"]):
                done.add("unit_verify")
            if ver["whole"] and all(s == "PASS" for s in ver["whole"]):
                done.add("whole_verify")
            pub_rec = value.get("publication_record")
            if isinstance(pub_rec, dict) and pub_rec.get("state") == "COMPLETED":
                done.add("publication")
            if packet is not None:
                done.add("acceptance")
            if state == "COMPLETE":
                done = set(STAGES)
            reached = next((s for s in reversed(STAGES) if s in done), None)
            failed_at = None
            if state != "COMPLETE":
                failed_at = next((s for s in STAGES if s not in done), None)
                if failed_at is None:
                    notes.append("not_complete_but_all_stages_evidenced")

            # failure detail
            detail = ""
            for op in sem_ops + worker_ops:
                if op.get("error"):
                    detail = str(op["error"])
            blocker = ""
            if error == "VERIFIER_NOT_AUTHORIZED" or ver["failed_verifiers"]:
                blocker = ",".join(ver["failed_verifiers"]) or "VERIFIER_NOT_AUTHORIZED"
            if ver["failed_checks"]:
                blocker = ",".join([blocker, *ver["failed_checks"]]).strip(",")

            receipts = [r for op in sem_ops + worker_ops for r in _receipts(op)]
            revisions, unmeasured = _models(receipts)
            repairs = sum(_int(op.get("repair_phase_count")) for op in worker_ops)
            core = sorted({
                str(op["core_binding_status"]) for op in worker_ops if op.get("core_binding_status")
            })
            diag = sorted({
                str(op["diagnosis_status"]) for op in worker_ops if op.get("diagnosis_status")
            })
            binding = (
                value.get("worker_binding") if isinstance(value.get("worker_binding"), dict) else {}
            )

            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = None
            first = min(events) if events else None
            ts_source = "evidence"
            if first is None:
                first = mtime
                ts_source = "state_file_mtime_only"
            last_candidates = [t for t in [*events, mtime] if t is not None]
            last = max(last_candidates) if last_candidates else None
            duration = (
                round(last - first, 1)
                if (last is not None and first is not None and ts_source == "evidence")
                else None
            )
            window_hits = Counter(
                e["code"]
                for e in log_entries
                if first is not None and last is not None and first <= e["ts"] <= last
            )

            runs.append({
                "issue": issue,
                "identity": identity,
                "revision": req_identity.get("revision"),
                "main_sha": req_identity.get("main_sha")
                or next(
                    (a.get("expected_base_sha") for a in atts if a.get("expected_base_sha")), None
                ),
                "task_id": task_id,
                "first_ts": _iso(first),
                "last_ts": _iso(last),
                "ts_source": ts_source,
                "duration_s": duration,
                "state": state,
                "prior_state": value.get("prior_state"),
                "reached": reached,
                "failed_at": failed_at,
                "reason": error,
                "detail": detail,
                "model_invocations": len(receipts),
                "model_revisions": sorted(revisions),
                "unmeasured_invocations": unmeasured,
                "configured_model": binding.get("model"),
                "repair_phases": repairs,
                "core_binding": core,
                "diagnosis": diag,
                "blocked_by": blocker,
                "verification": ver,
                "acceptance_gate": (packet or {}).get("current_gate"),
                "opencli_failures": sum(window_hits.values()),
                "opencli_failure_codes": dict(sorted(window_hits.items())),
                "link_notes": notes,
            })
    # ordinal run label per issue by first timestamp
    runs.sort(key=lambda r: (r["issue"], r["first_ts"] or "", r["identity"]))
    per_issue: Counter[int] = Counter()
    for run in runs:
        per_issue[run["issue"]] += 1
        m = re.search(r"-r(\d+)$", str(run["revision"] or ""))
        run["run"] = f"r{m.group(1)}" if m else f"r{per_issue[run['issue']]}"
    meta = {
        "unreadable_files": loader.unreadable,
        "unlinked_operations": len([o for o in ops_by_id if o not in linked_ops]),
        "operations_total": len(ops_by_id),
        "failure_log_entries": len(log_entries),
    }
    return runs, meta


def filter_since(runs: list[dict[str, Any]], since: str | None) -> list[dict[str, Any]]:
    if not since:
        return runs
    value = since if "T" in since else f"{since}T00:00:00"
    try:
        cut_dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        cut = None
    else:
        if cut_dt.tzinfo is None:
            cut_dt = cut_dt.replace(tzinfo=UTC)
        cut = cut_dt.timestamp()
    if cut is None:
        raise SystemExit(f"invalid --since value: {since}")
    kept = []
    for run in runs:
        ts = _parse_ts(run["first_ts"])
        if ts is not None and ts >= cut:
            kept.append(run)
    return kept


def _fmt_dur(seconds: float | None) -> str:
    if seconds is None:
        return "n/a"
    minutes, sec = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m" if hours else f"{minutes}m{sec:02d}s"


def render_markdown(runs: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    total = len(runs)
    complete = [r for r in runs if r["state"] == "COMPLETE"]
    durations = [r["duration_s"] for r in runs if r["duration_s"] is not None]
    out = ["# EIA scoreboard", ""]
    rate = f"{100 * len(complete) / total:.0f}%" if total else "n/a"
    out += [
        f"- runs: {total}",
        f"- completed: {len(complete)}",
        f"- success rate: {rate}",
        f"- median duration: {_fmt_dur(statistics.median(durations)) if durations else 'n/a'}"
        f" (over {len(durations)} runs with evidence timestamps)",
    ]
    models = Counter(m for r in runs for m in r["model_revisions"])
    out.append(
        "- models seen: "
        + (", ".join(f"{m} ({n} runs)" for m, n in sorted(models.items())) or "none")
    )
    unmeasured = sum(r["unmeasured_invocations"] for r in runs)
    out.append(f"- invocations without a measured model revision: {unmeasured}")
    out.append(
        f"- operations linked to no run: {meta['unlinked_operations']} of {meta['operations_total']}"
    )
    if meta["unreadable_files"]:
        out.append(f"- unreadable state files skipped: {len(meta['unreadable_files'])}")
    out += ["", "## Failures by stage", ""]
    by_stage = Counter(r["failed_at"] or "unknown" for r in runs if r["state"] != "COMPLETE")
    out += [f"- {k}: {v}" for k, v in sorted(by_stage.items())] or ["- none"]
    out += ["", "## Failures by reason", ""]
    by_reason = Counter(
        " / ".join(x for x in (r["reason"] or r["state"], r["detail"]) if x)
        for r in runs
        if r["state"] != "COMPLETE"
    )
    out += [f"- {k}: {v}" for k, v in sorted(by_reason.items())] or ["- none"]
    out += ["", "## Runs", ""]
    cols = [
        "issue",
        "run",
        "identity",
        "revision",
        "task",
        "first",
        "last",
        "dur",
        "state",
        "reached",
        "failed_at",
        "reason",
        "inv",
        "models",
        "repairs",
        "blocked_by",
        "opencli",
        "notes",
    ]
    out.append("| " + " | ".join(cols) + " |")
    out.append("|" + "|".join("---" for _ in cols) + "|")
    for r in runs:
        reason = " / ".join(x for x in (r["reason"], r["detail"]) if x)
        row = [
            f"#{r['issue']}",
            r["run"],
            r["identity"][:8],
            r["revision"] or "?",
            r["task_id"] or "?",
            r["first_ts"] or "?",
            r["last_ts"] or "?",
            _fmt_dur(r["duration_s"]),
            r["state"],
            r["reached"] or "-",
            r["failed_at"] or "-",
            reason or "-",
            str(r["model_invocations"]),
            ",".join(r["model_revisions"]) or "-",
            str(r["repair_phases"]),
            r["blocked_by"] or "-",
            str(r["opencli_failures"]),
            "; ".join(
                r["link_notes"] + (["no_event_timestamps"] if r["ts_source"] != "evidence" else [])
            )
            or "-",
        ]
        out.append("| " + " | ".join(c.replace("|", "/") for c in row) + " |")
    out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    parser.add_argument("--state-root", default=DEFAULT_STATE_ROOT)
    parser.add_argument("--failure-log", default=DEFAULT_FAILURE_LOG)
    parser.add_argument("--format", choices=("jsonl", "markdown"), default="markdown")
    parser.add_argument(
        "--since", help="only runs whose first timestamp >= this ISO date/time (UTC)"
    )
    args = parser.parse_args(argv)
    state_root = Path(args.state_root).expanduser()
    log = Path(args.failure_log).expanduser() if args.failure_log else None
    runs, meta = collect(state_root, log)
    runs = filter_since(runs, args.since)
    if args.format == "jsonl":
        for run in runs:
            sys.stdout.write(json.dumps(run, sort_keys=True) + "\n")
    else:
        sys.stdout.write(render_markdown(runs, meta))
    for bad in meta["unreadable_files"]:
        sys.stderr.write(f"warning: unreadable {bad}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
