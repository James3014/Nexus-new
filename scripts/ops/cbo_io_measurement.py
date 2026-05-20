from __future__ import annotations

import argparse
import builtins
import json
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch

from nexus.app import research_flow_service
from nexus.research.findings_memory import FindingsCard, FindingsMemoryStore
from nexus.research.findings_vector_sync import NoopFindingsVectorSync


def measure_cbo_io(*, output_path: Path | None = None) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="nexus-cbo-io-") as tmp:
        repo_root = Path(tmp)
        _seed_fixture(repo_root)
        baseline = _measure_sample(repo_root)
        changed = _measure_sample(repo_root)

    report = {
        "schema": "nexus.cbo_io_measurement.v1",
        "status": "PASS",
        "claim_class": "OBSERVATION_ONLY",
        "sample_size": 2,
        "baseline": baseline,
        "changed": changed,
        "delta_claim_allowed": False,
        "limitations": [
            "Baseline and changed samples are both measured on the current code revision.",
            "This harness validates I/O visibility and report shape; it does not claim performance improvement.",
        ],
    }
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def _seed_fixture(repo_root: Path) -> None:
    docs = repo_root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "race.md").write_text(
        "Fix websocket timeout race in coordinator path.\nClaim verification required.\n",
        encoding="utf-8",
    )
    history_path = repo_root / ".nexus" / "reports" / "research" / "auto-flow-history.json"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        json.dumps(
            {
                "flow:hyper": [
                    {
                        "flow": "hyper_sprint",
                        "status": "SUCCESS",
                        "reason": "stage1_pass",
                        "task_type": "bug",
                        "task_desc": "fix websocket timeout race in coordinator",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def _measure_sample(repo_root: Path) -> dict[str, Any]:
    with _io_counter() as counter:
        started_at = time.perf_counter()
        route = research_flow_service.build_route(
            repo_root=repo_root,
            task_desc="fix websocket timeout race in orchestrator",
            task_type="bug",
            candidate_count=1,
            root_cause_confidence=0.9,
            findings_query="websocket timeout race",
            target_file="demo.py",
        )
        store = FindingsMemoryStore(repo_root, vector_sync=NoopFindingsVectorSync())
        write_path = store.write(
            FindingsCard(
                id="cboio",
                title="CBO IO observation",
                kind="knowledge",
                body="Observation-only card for CBO I/O harness.",
            )
        )
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 4)

    return {
        "wall_ms": elapsed_ms,
        "file_reads": counter["reads"],
        "file_writes": counter["writes"],
        "route_flow": route.get("recommended_flow"),
        "memory_hits": route.get("route_features", {}).get("memory_hits", 0),
        "findings_write_path_present": bool(write_path),
    }


@contextmanager
def _io_counter() -> Iterator[dict[str, int]]:
    counts = {"reads": 0, "writes": 0}
    original_open = builtins.open
    original_read_text = Path.read_text
    original_write_text = Path.write_text

    def counted_open(file, mode="r", *args, **kwargs):
        if any(flag in str(mode) for flag in ("w", "a", "+")):
            counts["writes"] += 1
        else:
            counts["reads"] += 1
        return original_open(file, mode, *args, **kwargs)

    def counted_read_text(self: Path, *args, **kwargs):
        counts["reads"] += 1
        return original_read_text(self, *args, **kwargs)

    def counted_write_text(self: Path, *args, **kwargs):
        counts["writes"] += 1
        return original_write_text(self, *args, **kwargs)

    with patch("builtins.open", counted_open), patch.object(Path, "read_text", counted_read_text), patch.object(
        Path, "write_text", counted_write_text
    ):
        yield counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Run observation-only CBO I/O measurement harness.")
    parser.add_argument("--output", type=Path, default=Path("docs/reports/NEXUS_CBO_IO_MEASUREMENT_2026-05-20.json"))
    args = parser.parse_args()
    report = measure_cbo_io(output_path=args.output)
    print(json.dumps({"status": report["status"], "output": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
