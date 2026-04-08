#!/usr/bin/env bash
set -euo pipefail

cd .
round=0

while true; do
  round=$((round+1))
  echo "[baseline-cycle] round=${round} start $(date '+%Y-%m-%d %H:%M:%S')"

  uv run scripts/ops/ci_gate.py
  uv run scripts/nexus_cli.py nexus:benchmark --tasks 10 --output ci_benchmark.csv

  # Lightweight docs sync from latest benchmark snapshot.
  uv run python3 - <<'PY'
import csv, re
from pathlib import Path

idx = Path('docs/INDEX.md')
content = idx.read_text(encoding='utf-8')
rows = list(csv.DictReader(open('ci_benchmark.csv', encoding='utf-8')))
if not rows:
    raise SystemExit('empty ci_benchmark.csv')

succ = sum((r.get('status', '').upper() == 'PASS') for r in rows)
avg = sum(float(r.get('health') or 0) for r in rows) / len(rows)
key = [k for k in rows[0].keys() if 'capture_status' in k][0]
empty = sum(1 for r in rows if not (r.get(key) or '').strip())
raw = sum(int(r.get('token_raw_model') or 0) for r in rows)

snapshot = f"(PASS, {succ/len(rows)*100:.1f}, {avg:.1f}, empty={empty}, raw={raw})"
new_content = re.sub(r"Last Verified Snapshot: `.*`", f"Last Verified Snapshot: `{snapshot}`", content)
idx.write_text(new_content, encoding='utf-8')
print(f"docs sync snapshot={snapshot}")
PY

  echo "[baseline-cycle] round=${round} done"
  sleep 15
done
