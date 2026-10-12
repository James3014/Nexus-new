"""ARCHIVED 2026-10-12: the random-number dual-core benchmark was retired.

The previous implementation produced ``health`` from ``random.uniform(90, 100)`` and
hallucination outcomes from ``random.random()`` without executing any task (issue
#1762). ``BenchmarkService.run`` now fails closed with ``ARCHIVED_REASON``. The
original lives on branch ``archive/2026-10-12-first-batch``; see
``ARCHIVED_2026-10-12.md``.
"""

from pathlib import Path
from typing import Any, Dict, Optional

ARCHIVED_REASON = "archived_fake_benchmark_2026-10-12"


class ArchivedBenchmarkError(RuntimeError):
    """Raised instead of returning synthetic benchmark numbers."""

    reason = ARCHIVED_REASON

    def __init__(self) -> None:
        super().__init__(ARCHIVED_REASON)


class BenchmarkService:
    """Fail-closed placeholder for the archived simulated benchmark."""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)

    def run(
        self,
        dataset: str,
        repeat: int,
        dual_core_physical: bool,
        ablation: bool,
        tasks_count: int = 10,
        output_csv: Optional[str] = None,
    ) -> Dict[str, Any]:
        raise ArchivedBenchmarkError()
