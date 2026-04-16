#!/usr/bin/env python3
from __future__ import annotations
import argparse
import logging
from pathlib import Path
from nexus.app.learn_refresh_service import LearnRefreshService

REPO_ROOT = Path(__file__).resolve().parents[2]
LOG_FILE = REPO_ROOT / ".nexus" / "learn_refresh_daemon.log"

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

def main():
    parser = argparse.ArgumentParser(description="Nexus Learn Refresh Daemon")
    parser.add_argument("--topic", default="", help="Filter by topic")
    parser.add_argument("--interval-sec", type=int, default=3600, help="Interval between runs")
    parser.add_argument("--due-within-days", type=int, default=0)
    parser.add_argument("--pass-threshold", type=float, default=0.8)
    parser.add_argument("--question-count", type=int, default=5)
    parser.add_argument("--benchmark-manifest", help="Optional manifest for benchmark step")
    
    args = parser.parse_args()
    svc = LearnRefreshService(REPO_ROOT)
    svc.run_refresh_loop(
        topic=args.topic,
        interval_sec=args.interval_sec,
        due_within_days=args.due_within_days,
        pass_threshold=args.pass_threshold,
        question_count=args.question_count,
        benchmark_manifest=args.benchmark_manifest
    )

if __name__ == "__main__":
    main()
