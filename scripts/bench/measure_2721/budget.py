"""One spend ledger shared by every arm of a measurement (hard stop, #2721).

* The ledger file is required and shared: every runner (BARE, NEXUS, NOOP)
  passes the same ``--spend-ledger``; the cap is stored in the file on
  creation and a runner with a different cap is refused.
* A row is admitted under the lock together with a reservation (the most
  expensive row so far, at least ``min_reserve``), so parallel runners cannot
  jointly overshoot the cap.
* A row's charge is its reported ``total_cost_usd``.  When that is unknown (a
  killed or timed-out CLI never writes its final result) the row is charged
  its reservation and marked ``estimated``.
"""

from __future__ import annotations

import fcntl
import json
import os
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

DEFAULT_CAP_USD = 60.0


class BudgetExhausted(RuntimeError):
    pass


class BudgetConfigError(RuntimeError):
    pass


class SpendLedger:
    def __init__(self, path: Path, cap_usd: float = DEFAULT_CAP_USD, min_reserve: float = 0.5):
        self.path = Path(path)
        self.cap_usd = float(cap_usd)
        self.min_reserve = float(min_reserve)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        state = self._locked(lambda data: None)
        if abs(float(state["cap_usd"]) - self.cap_usd) > 1e-9:
            raise BudgetConfigError(f"ledger cap is {state['cap_usd']}, this runner was given {self.cap_usd}")

    def _locked(self, update: Optional[Callable[[dict[str, Any]], Any]] = None) -> dict[str, Any]:
        with open(self.path.with_suffix(".lock"), "a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if self.path.is_file():
                data = json.loads(self.path.read_text())
            else:
                data = {"cap_usd": self.cap_usd, "spent_usd": 0.0, "worst_row_usd": 0.0, "rows": 0,
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

    def finish_row(self, token: str, cost_usd: Any, *, unknown_attempts: int = 0) -> dict[str, Any]:
        """Release the reservation and charge the row.

        ``cost_usd`` None, or any ``unknown_attempts`` (a killed attempt whose
        cost was never reported), adds the reservation as an estimate.
        """

        def update(data: dict[str, Any]) -> dict[str, Any]:
            reserve = float(data["reservations"].pop(token, max(float(data["worst_row_usd"]), self.min_reserve)))
            known = cost_usd is not None and not unknown_attempts
            cost = float(cost_usd or 0.0) + (0.0 if known else reserve)
            data["spent_usd"] = round(float(data["spent_usd"]) + cost, 6)
            if known:
                data["worst_row_usd"] = max(float(data["worst_row_usd"]), cost)
            else:
                data["estimated_rows"] = int(data["estimated_rows"]) + 1
            data["rows"] = int(data["rows"]) + 1
            return {"charged_usd": cost, "estimated": not known}

        return self._locked(update)["_result"]
