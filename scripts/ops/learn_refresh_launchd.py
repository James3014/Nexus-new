#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
from nexus.app.learn_refresh_service import LearnRefreshService

def main():
    parser = argparse.ArgumentParser(description="Nexus Learn Refresh (Launchd Entry)")
    parser.add_argument("--topic", default="", help="Filter by topic")
    parser.add_argument("--due-within-days", type=int, default=0)
    parser.add_argument("--pass-threshold", type=float, default=0.8)
    parser.add_argument("--question-count", type=int, default=5)
    
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    svc = LearnRefreshService(repo_root)
    # Run once
    svc.run_refresh_loop(
        topic=args.topic,
        interval_sec=0, 
        due_within_days=args.due_within_days,
        pass_threshold=args.pass_threshold,
        question_count=args.question_count
    )

if __name__ == "__main__":
    main()
