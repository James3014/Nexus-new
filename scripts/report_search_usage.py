#!/usr/bin/env python3
import argparse
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path


LOG_PATH = Path.home() / ".muse_logs" / "brain_search_usage.jsonl"


def parse_iso(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser(description="Summarize brain_search_v2 usage logs")
    parser.add_argument("--days", type=int, default=7, help="lookback window in days")
    parser.add_argument("--top", type=int, default=20, help="top N files")
    args = parser.parse_args()

    if not LOG_PATH.exists():
        print(f"No log file: {LOG_PATH}")
        return

    since = datetime.now(timezone.utc) - timedelta(days=args.days)
    query_counter = Counter()
    source_counter = Counter()
    status_counter = Counter()
    elapsed = []
    total = 0

    with LOG_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            ts = parse_iso(str(row.get("ts", "")))
            if not ts or ts < since:
                continue
            total += 1
            query_counter[str(row.get("query", ""))] += 1
            status_counter[str(row.get("status", ""))] += 1
            try:
                elapsed.append(float(row.get("elapsed_ms", 0.0)))
            except Exception:
                pass
            for src in row.get("top_sources", []) or []:
                source_counter[str(src)] += 1

    if total == 0:
        print(f"No records in last {args.days} days.")
        return

    elapsed_sorted = sorted(elapsed)
    p50 = elapsed_sorted[len(elapsed_sorted) // 2] if elapsed_sorted else 0.0
    p95 = elapsed_sorted[min(len(elapsed_sorted) - 1, int(len(elapsed_sorted) * 0.95))] if elapsed_sorted else 0.0

    print(f"Window: last {args.days} days")
    print(f"Total searches: {total}")
    print(f"Latency p50/p95 (ms): {p50:.2f}/{p95:.2f}")
    print("\nTop status:")
    for k, v in status_counter.most_common(5):
        print(f"  {k}: {v}")

    print("\nTop queries:")
    for q, c in query_counter.most_common(min(args.top, 10)):
        print(f"  {c:>4}  {q}")

    print("\nTop files (most-hit):")
    for src, c in source_counter.most_common(args.top):
        print(f"  {c:>4}  {src}")


if __name__ == "__main__":
    main()
