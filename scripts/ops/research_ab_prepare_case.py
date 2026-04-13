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


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare reproducible A/B benchmark case fixtures.")
    parser.add_argument("--case", required=True, choices=["deadlock-small", "deadlock-stress"])
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    if args.case == "deadlock-small":
        _write_case_deadlock_small(repo_root)
    elif args.case == "deadlock-stress":
        _write_case_deadlock_stress(repo_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
