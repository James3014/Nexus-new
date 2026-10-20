"""One spend ledger shared by every arm of a measurement (hard stop, #2721).

* The ledger file is required and shared: every runner (BARE, NEXUS, NOOP)
  passes the same ``--spend-ledger``; the cap is stored in the file on
  creation and a runner with a different cap is refused.
* A row is admitted under the lock together with a reservation (the most
  expensive row so far, at least ``max_row_usd``), so parallel runners cannot
  jointly overshoot the cap.
* A row's charge is its reported ``total_cost_usd``.  Each attempt whose cost
  is unknown (a killed or timed-out CLI never writes its final result) adds a
  conservative per-attempt ceiling (the reservation, at least ``max_row_usd``);
  the usage-priced estimate replaces it when larger.  Such rows are marked
  ``estimated`` and still raise ``worst_row_usd``.
"""

from __future__ import annotations

import fcntl
import json
import os
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

DEFAULT_CAP_USD = 60.0
DEFAULT_MAX_ROW_USD = 3.0


class BudgetExhausted(RuntimeError):
    pass


class BudgetConfigError(RuntimeError):
    pass


class SpendLedger:
    def __init__(self, path: Path, cap_usd: float = DEFAULT_CAP_USD, max_row_usd: float = DEFAULT_MAX_ROW_USD):
        self.path = Path(path)
        self.cap_usd = float(cap_usd)
        self.min_reserve = float(max_row_usd)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        state = self._locked(lambda data: None)
        for key, mine in (("cap_usd", self.cap_usd), ("max_row_usd", self.min_reserve)):
            if abs(float(state[key]) - mine) > 1e-9:
                raise BudgetConfigError(f"ledger {key} is {state[key]}, this runner was given {mine}")

    def _locked(self, update: Optional[Callable[[dict[str, Any]], Any]] = None) -> dict[str, Any]:
        with open(self.path.with_suffix(".lock"), "a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if self.path.is_file():
                data = json.loads(self.path.read_text())
            else:
                data = {"cap_usd": self.cap_usd, "max_row_usd": self.min_reserve, "spent_usd": 0.0, "worst_row_usd": 0.0, "rows": 0,
                        "estimated_rows": 0, "reservations": {}}
            result = update(data) if update is not None else None
            if update is not None:
                partial = self.path.with_suffix(f".{os.getpid()}.tmp")
                with open(partial, "w") as handle:
                    handle.write(json.dumps(data, sort_keys=True))
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(partial, self.path)
            data["_result"] = result
            return data

    def state(self) -> dict[str, Any]:
        return self._locked()

    def begin_row(self) -> str:
        """Admit one row and reserve its expected cost, atomically; raise when over the cap."""
        token = uuid.uuid4().hex

        def update(data: dict[str, Any]) -> None:
            reserve = max(float(data["worst_row_usd"]), self.min_reserve)
            pending = sum(float(v) for v in data["reservations"].values())
            if float(data["spent_usd"]) + pending + reserve > float(data["cap_usd"]):
                raise BudgetExhausted(
                    f"BUDGET_STOP: spent {data['spent_usd']:.4f} + reserved {pending:.4f} "
                    f"+ next {reserve:.4f} > cap {data['cap_usd']}"
                )
            data["reservations"][token] = reserve

        self._locked(update)
        return token

    def finish_row(self, token: str, cost_usd: Any, *, unknown_attempts: int = 0,
                   estimate_usd: float = 0.0) -> dict[str, Any]:
        """Release the reservation and charge the row.

        ``cost_usd`` is the known cost (None = nothing known).  Every unknown
        attempt (at least one when ``cost_usd`` is None) adds the per-attempt
        ceiling; ``estimate_usd`` (usage-priced unknown attempts) replaces
        that total when larger.
        """

        def update(data: dict[str, Any]) -> dict[str, Any]:
            reserve = max(float(data["reservations"].pop(token, 0.0)), float(data["worst_row_usd"]),
                          self.min_reserve)
            unknown = max(int(unknown_attempts), 1 if cost_usd is None else 0)
            known = unknown == 0
            cost = float(cost_usd or 0.0) + (0.0 if known else max(reserve * unknown, float(estimate_usd)))
            data["spent_usd"] = round(float(data["spent_usd"]) + cost, 6)
            data["worst_row_usd"] = max(float(data["worst_row_usd"]), cost)
            if not known:
                data["estimated_rows"] = int(data["estimated_rows"]) + 1
            data["rows"] = int(data["rows"]) + 1
            return {"charged_usd": cost, "estimated": not known}

        return self._locked(update)["_result"]
