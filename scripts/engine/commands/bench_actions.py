from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class EffortRoiRow:
    success_rate: float
    avg_duration_sec: float | None
    count: int


class EffortBenchmarkRunner(Protocol):
    def generate_effort_roi_report(self) -> Mapping[str, Mapping[str, Any]]:
        ...


RunnerFactory = Callable[[Path], EffortBenchmarkRunner]


def _default_runner_factory(repo_root: Path) -> EffortBenchmarkRunner:
    from nexus.engine.benchmark_runner import BenchmarkRunner

    return BenchmarkRunner(repo_root)


def get_effort_roi_report(
    repo_root: str | Path,
    *,
    runner_factory: RunnerFactory | None = None,
) -> dict[str, EffortRoiRow]:
    root = Path(repo_root)
    factory = runner_factory or _default_runner_factory
    report = factory(root).generate_effort_roi_report()
    return {
        str(level): EffortRoiRow(
            success_rate=float(data["success_rate"]),
            avg_duration_sec=(
                None if data.get("avg_duration_sec") is None else float(data["avg_duration_sec"])
            ),
            count=int(data["count"]),
        )
        for level, data in report.items()
    }


def render_effort_roi_report(report: Mapping[str, EffortRoiRow]) -> list[str]:
    lines = ["📈 [Nexus Effort ROI Report]"]
    for level, data in report.items():
        lines.extend(
            [
                "",
                f"[{level.upper()}]",
                f"  Success Rate: {data.success_rate:.2%}",
                (
                    "  Avg Duration: n/a"
                    if data.avg_duration_sec is None
                    else f"  Avg Duration: {data.avg_duration_sec:.1f}s"
                ),
                f"  Count       : {data.count}",
            ]
        )
    return lines
