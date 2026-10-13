"""Offline Agy bench fixtures (#1932): a temp account pool, leases dir and quota snapshot.

Nothing here touches ``~/.nexus/agy-account-pool``: the pool is an in-memory
``AgyAccountPoolManager`` declared through ``NEXUS_AGY_BENCH_POOL_FIXTURE`` and the leases
directory, allocator lock and quota snapshot all live under ``tmp_path``.
"""

from __future__ import annotations

import json
import stat
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

FIVE_HOUR_OK = {"status": "known", "remaining_pct": 80.0, "reset_at": "2099-01-01T00:00:00Z"}
WEEKLY_OK = {"status": "known", "remaining_pct": 60.0, "reset_at": "2099-01-01T00:00:00Z"}
SPENT = {"status": "known", "remaining_pct": 0.0, "reset_at": "2099-01-01T00:00:00Z"}

# Fake agy: records argv + HOME, writes an Agy-shaped log to --log-file, and behaves per account
# HOME according to a JSON behaviour file ("ok", "quota_pre", "quota_after", "mismatch",
# "nolog", "fail").
FAKE_AGY = r"""#!{python}
import json, os, sys
argv = sys.argv[1:]
home = os.environ.get("HOME", "")
cfg = json.load(open({cfg!r}))
mode = cfg.get("by_home", {{}}).get(home, cfg.get("default", "ok"))
open({calls!r}, "a").write(json.dumps({{"argv": argv, "home": home, "mode": mode}}) + "\n")
model = argv[argv.index("--model") + 1] if "--model" in argv else "agy-default"
label = cfg.get("label", "Gemini 3.8 Flash (Medium)")
if mode == "mismatch":
    label = "Gemini 3.8 Flash (High)"
if "--log-file" in argv and mode != "nolog":
    with open(argv[argv.index("--log-file") + 1], "a") as log:
        log.write("I1013 01:00:00.000001       1 model_resolver.go:93] Resolving model %s\n" % model)
        log.write('I1013 01:00:00.000002       1 model_config_manager.go:327] '
                  'Propagating selected model override to backend: label="%s"\n' % label)
        log.write("I1013 01:00:00.000003       1 printmode.go:1] Created conversation "
                  "12345678-1234-1234-1234-123456789abc\n")
if mode == "quota_pre":
    sys.stderr.write("RESOURCE_EXHAUSTED: quota exceeded for this account")
    raise SystemExit(1)
if mode == "quota_after":
    print(json.dumps({{"status": "ERROR", "response": "partial answer",
                      "usage": {{"total_tokens": 500}}}}))
    sys.stderr.write("RESOURCE_EXHAUSTED: quota exceeded mid-stream")
    raise SystemExit(1)
if mode == "fail":
    sys.stderr.write("boom")
    raise SystemExit(7)
print(json.dumps({{"conversation_id": "c1", "status": "SUCCESS", "response": cfg["reply"],
                  "duration_seconds": 0.1, "num_turns": 1,
                  "usage": {{"input_tokens": 900, "output_tokens": 100, "total_tokens": 1000}}}}))
"""


@dataclass
class AgyBenchPool:
    root: Path
    accounts: list[str]
    homes: dict[str, Path] = field(default_factory=dict)
    exe: Path = Path()
    calls_log: Path = Path()
    behaviour: Path = Path()
    snapshot: Path = Path()
    fixture: Path = Path()
    leases_dir: Path = Path()

    def env(self, **extra: str) -> dict[str, str]:
        import os

        return {
            "PATH": os.environ.get("PATH", ""),
            "NEXUS_AGY_BIN": str(self.exe),
            "NEXUS_AGY_BENCH_POOL_FIXTURE": str(self.fixture),
            "NEXUS_AGY_QUOTA_SNAPSHOT": str(self.snapshot),
            "NEXUS_AGY_BENCH_POOL_WAIT_SECONDS": "0",
            **extra,
        }

    def set_behaviour(self, reply: str = "", *, default: str = "ok", **by_account: str) -> None:
        by_home = {str(self.homes[name]): mode for name, mode in by_account.items()}
        self.behaviour.write_text(
            json.dumps({"reply": reply, "default": default, "by_home": by_home}), encoding="utf-8"
        )

    def write_snapshot(
        self, groups_by_account: dict[str, dict[str, Any] | None], *, age_seconds: float = 0.0
    ) -> None:
        checked = (datetime.now(timezone.utc) - timedelta(seconds=age_seconds)).isoformat()
        rows = []
        for name, gemini in groups_by_account.items():
            row: dict[str, Any] = {"account": name, "ok": True, "checked_at": checked}
            row["groups"] = {} if gemini is None else {"Gemini Models": gemini}
            rows.append(row)
        self.snapshot.write_text(
            json.dumps({"checked_at": checked, "accounts": rows}), encoding="utf-8"
        )

    def calls(self) -> list[dict[str, Any]]:
        if not self.calls_log.exists():
            return []
        return [json.loads(line) for line in self.calls_log.read_text().splitlines()]

    def coordinator(self):
        from scripts.bench.agy_account_lease import build_bench_lease_coordinator

        coordinator, _source = build_bench_lease_coordinator({
            "NEXUS_AGY_BENCH_POOL_FIXTURE": str(self.fixture)
        })
        return coordinator

    def account_for_home(self, home: str) -> str:
        return next(name for name, path in self.homes.items() if str(path) == home)


@pytest.fixture
def agy_pool(tmp_path: Path) -> AgyBenchPool:
    root = tmp_path / "agy-pool"
    pool = AgyBenchPool(root=root, accounts=["acc-a", "acc-b", "acc-c"])
    for name in pool.accounts:
        home = root / "accounts" / name
        home.mkdir(parents=True)
        pool.homes[name] = home
    pool.leases_dir = root / "leases"
    pool.fixture = root / "pool.json"
    pool.fixture.write_text(
        json.dumps({
            "accounts": [{"alias": n, "home": str(h)} for n, h in pool.homes.items()],
            "leases_dir": str(pool.leases_dir),
            "allocator_lock_path": str(root / "allocator.lock"),
        }),
        encoding="utf-8",
    )
    pool.snapshot = root / "quota-snapshot.json"
    pool.write_snapshot({name: {"weekly": WEEKLY_OK, "5h": FIVE_HOUR_OK} for name in pool.accounts})
    pool.behaviour = root / "behaviour.json"
    pool.calls_log = root / "calls.jsonl"
    pool.exe = root / "bin" / "agy"
    pool.exe.parent.mkdir()
    pool.exe.write_text(
        FAKE_AGY.format(python=sys.executable, cfg=str(pool.behaviour), calls=str(pool.calls_log)),
        encoding="utf-8",
    )
    pool.exe.chmod(pool.exe.stat().st_mode | stat.S_IXUSR)
    pool.set_behaviour('{"status": "ok", "patch": "x = 1\\n"}')
    return pool
