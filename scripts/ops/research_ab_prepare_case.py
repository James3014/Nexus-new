#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def _write_case_deadlock_small(repo_root: Path) -> None:
    target = repo_root / "nexus/demo/bank_transfer_bench_ab_small.py"
    test_file = repo_root / "tests/demo/test_concurrency_bench_ab_small.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    test_file.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        """import time
import threading

class Account:
    def __init__(self, balance):
        self.balance = balance
        self.lock = threading.Lock()

def transfer(acc1, acc2, amount):
    with acc1.lock:
        time.sleep(0.01) # Simulate some IO or DB operation
        with acc2.lock:
            if acc1.balance >= amount:
                acc1.balance -= amount
                acc2.balance += amount
""",
        encoding="utf-8",
    )
    test_file.write_text(
        """import threading
from nexus.demo.bank_transfer_bench_ab_small import Account, transfer

def test_no_deadlock_small():
    acc1 = Account(100)
    acc2 = Account(100)
    def thread1():
        for _ in range(10):
            transfer(acc1, acc2, 5)
    def thread2():
        for _ in range(10):
            transfer(acc2, acc1, 5)
    t1 = threading.Thread(target=thread1, daemon=True)
    t2 = threading.Thread(target=thread2, daemon=True)
    t1.start()
    t2.start()
    t1.join(timeout=1.0)
    t2.join(timeout=1.0)
    assert not t1.is_alive(), "Deadlock detected in thread 1"
    assert not t2.is_alive(), "Deadlock detected in thread 2"
    assert acc1.balance + acc2.balance == 200
""",
        encoding="utf-8",
    )


def _write_case_deadlock_stress(repo_root: Path) -> None:
    target = repo_root / "nexus/demo/bank_transfer_bench_ab_stress.py"
    test_file = repo_root / "tests/demo/test_concurrency_bench_ab_stress.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    test_file.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        """import time
import threading

class Account:
    def __init__(self, balance):
        self.balance = balance
        self.lock = threading.Lock()

def transfer(acc1, acc2, amount):
    with acc1.lock:
        time.sleep(0.01) # Simulate some IO or DB operation
        with acc2.lock:
            if acc1.balance >= amount:
                acc1.balance -= amount
                acc2.balance += amount
""",
        encoding="utf-8",
    )
    test_file.write_text(
        """import threading
from nexus.demo.bank_transfer_bench_ab_stress import Account, transfer

def test_no_deadlock_stress():
    acc1 = Account(100)
    acc2 = Account(100)
    def thread1():
        for _ in range(50):
            transfer(acc1, acc2, 1)
    def thread2():
        for _ in range(50):
            transfer(acc2, acc1, 1)
    t1 = threading.Thread(target=thread1, daemon=True)
    t2 = threading.Thread(target=thread2, daemon=True)
    t1.start()
    t2.start()
    t1.join(timeout=2.0)
    t2.join(timeout=2.0)
    assert not t1.is_alive(), "Deadlock detected in thread 1"
    assert not t2.is_alive(), "Deadlock detected in thread 2"
    assert acc1.balance + acc2.balance == 200
""",
        encoding="utf-8",
    )


def _write_case_feature_discount(repo_root: Path) -> None:
    target = repo_root / "nexus/demo/feature_discount_engine.py"
    test_file = repo_root / "tests/demo/test_feature_discount_engine.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    test_file.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        """def calculate_discount(total, is_vip=False, coupon=None):
    discount = 0.0
    if total >= 100:
        discount += 0.10
    if coupon == "SAVE5":
        discount += 0.05
    # BUG: VIP tier not applied yet.
    final = total * (1.0 - discount)
    return round(final, 2)
""",
        encoding="utf-8",
    )
    test_file.write_text(
        """from nexus.demo.feature_discount_engine import calculate_discount

def test_base_discount_threshold():
    assert calculate_discount(120, is_vip=False, coupon=None) == 108.0

def test_coupon_stack():
    assert calculate_discount(120, is_vip=False, coupon="SAVE5") == 102.0

def test_vip_bonus_discount():
    # VIP should receive extra 5% on top of threshold discount.
    assert calculate_discount(120, is_vip=True, coupon=None) == 102.0
""",
        encoding="utf-8",
    )


def _write_case_feature_rate_limiter(repo_root: Path) -> None:
    target = repo_root / "nexus/demo/feature_rate_limiter.py"
    test_file = repo_root / "tests/demo/test_feature_rate_limiter.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    test_file.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        """import time

class RateLimiter:
    def __init__(self, limit=2, window_sec=1.0):
        self.limit = limit
        self.window_sec = window_sec
        self.hits = []

    def allow(self):
        now = time.time()
        # BUG: no pruning of stale hits
        if len(self.hits) >= self.limit:
            return False
        self.hits.append(now)
        return True
""",
        encoding="utf-8",
    )
    test_file.write_text(
        """import time
from nexus.demo.feature_rate_limiter import RateLimiter

def test_rate_limiter_window_reset():
    rl = RateLimiter(limit=2, window_sec=0.05)
    assert rl.allow() is True
    assert rl.allow() is True
    assert rl.allow() is False
    time.sleep(0.06)
    # After window, one new request should be allowed.
    assert rl.allow() is True
""",
        encoding="utf-8",
    )


def _write_case_refactor_normalize_config(repo_root: Path) -> None:
    target = repo_root / "nexus/demo/refactor_normalize_config.py"
    test_file = repo_root / "tests/demo/test_refactor_normalize_config.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    test_file.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        """def normalize_hosts(hosts):
    out = []
    for h in hosts:
        if h:
            out.append(h.strip().lower())
    # BUG: duplicate entries are not removed and order is unstable for consumers.
    return out
""",
        encoding="utf-8",
    )
    test_file.write_text(
        """from nexus.demo.refactor_normalize_config import normalize_hosts

def test_normalize_hosts_dedup_and_sort():
    got = normalize_hosts([" API.local ", "db.local", "api.local", ""])
    assert got == ["api.local", "db.local"]
""",
        encoding="utf-8",
    )


def _write_case_refactor_parser_purity(repo_root: Path) -> None:
    target = repo_root / "nexus/demo/refactor_parser_purity.py"
    test_file = repo_root / "tests/demo/test_refactor_parser_purity.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    test_file.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        """def parse_pairs(items):
    # BUG: mutates caller list and mishandles whitespace-only entries.
    items[:] = [x for x in items if x]
    out = {}
    for it in items:
        if "=" not in it:
            continue
        k, v = it.split("=", 1)
        out[k] = v
    return out
""",
        encoding="utf-8",
    )
    test_file.write_text(
        """from nexus.demo.refactor_parser_purity import parse_pairs

def test_parse_pairs_no_input_mutation_and_trim():
    src = ["a=1", "  ", "b=2 "]
    out = parse_pairs(src)
    assert out == {"a": "1", "b": "2"}
    assert src == ["a=1", "  ", "b=2 "]
""",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare reproducible A/B benchmark case fixtures.")
    parser.add_argument(
        "--case",
        required=True,
        choices=[
            "deadlock-small",
            "deadlock-stress",
            "feature-discount",
            "feature-rate-limiter",
            "refactor-normalize-config",
            "refactor-parser-purity",
        ],
    )
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    writers = {
        "deadlock-small": _write_case_deadlock_small,
        "deadlock-stress": _write_case_deadlock_stress,
        "feature-discount": _write_case_feature_discount,
        "feature-rate-limiter": _write_case_feature_rate_limiter,
        "refactor-normalize-config": _write_case_refactor_normalize_config,
        "refactor-parser-purity": _write_case_refactor_parser_purity,
    }
    writers[args.case](repo_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
