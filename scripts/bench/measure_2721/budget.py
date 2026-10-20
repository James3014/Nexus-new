"""One spend ledger shared by every arm of a measurement (hard stop, #2721).

Spend comes from each row's ``total_cost_usd`` (the CLI's usage report).  A new
row may start only while ``spent + reserve`` stays within the cap, where the
reserve is the most expensive row seen so far (at least ``min_reserve``).
"""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from typing import Any

DEFAULT_CAP_USD = 60.0


class BudgetExhausted(RuntimeError):
    pass


class SpendLedger:
    def __init__(self, path: Path, cap_usd: float = DEFAULT_CAP_USD, min_reserve: float = 0.5):
        self.path = Path(path)
        self.cap_usd = float(cap_usd)
        self.min_reserve = float(min_reserve)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _locked(self, update: Any = None) -> dict[str, Any]:
        with open(self.path.with_suffix(".lock"), "a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data = json.loads(self.path.read_text()) if self.path.is_file() else {"spent_usd": 0.0, "worst_row_usd": 0.0,
                                                                                   "rows": 0}
            if update is not None:
                update(data)
                partial = self.path.with_suffix(f".{os.getpid()}.tmp")
                partial.write_text(json.dumps(data, sort_keys=True))
                os.replace(partial, self.path)
            return data

    def state(self) -> dict[str, Any]:
        return self._locked()

    def check_can_start(self) -> None:
        data = self.state()
        reserve = max(float(data["worst_row_usd"]), self.min_reserve)
        if float(data["spent_usd"]) + reserve > self.cap_usd:
            raise BudgetExhausted(f"BUDGET_STOP: spent {data['spent_usd']:.4f} of {self.cap_usd} (reserve {reserve:.4f})")

    def add(self, cost_usd: Any) -> dict[str, Any]:
        cost = float(cost_usd or 0.0)

        def update(data: dict[str, Any]) -> None:
            data["spent_usd"] = round(float(data["spent_usd"]) + cost, 6)
            data["worst_row_usd"] = max(float(data["worst_row_usd"]), cost)
            data["rows"] = int(data["rows"]) + 1

        return self._locked(update)
