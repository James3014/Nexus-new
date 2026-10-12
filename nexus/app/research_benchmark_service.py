"""ARCHIVED 2026-10-12: the constant-score research benchmark was retired.

Gladiator mode scored every case with a constant ``score=1.0`` and A/B mode wrote a
fixed all-1.0 summary without executing any case. ``run_benchmark`` now fails closed
with ``ARCHIVED_REASON``. The original lives on branch
``archive/2026-10-12-first-batch``; see ``ARCHIVED_2026-10-12.md``.
"""

from __future__ import annotations

from pathlib import Path

ARCHIVED_REASON = "archived_fake_benchmark_2026-10-12"


class ArchivedResearchBenchmarkError(RuntimeError):
    """Raised instead of writing a synthetic benchmark report."""

    reason = ARCHIVED_REASON

    def __init__(self) -> None:
        super().__init__(ARCHIVED_REASON)


class ResearchBenchmarkService:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def run_benchmark(
        self,
        mode,
        manifest_file,
        report_file,
        budget_limit,
        timeout_sec,
        max_wall_time_sec,
        ab_trials,
        ab_llm_mode,
        llm_baseline,
    ):
        raise ArchivedResearchBenchmarkError()
