#!/usr/bin/env bash
# L3-G: Daily hybrid regression benchmark — 12 tasks × 4 quadrants
set -euo pipefail

NEXUS_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT_DIR="${NEXUS_ROOT}/.nexus/bench/daily"
TASKS_FILE="${NEXUS_ROOT}/tasks/benchmark_12_swebench.json"
PYTHON="${NEXUS_ROOT}/.venv/bin/python3"

mkdir -p "${OUT_DIR}"

echo "[daily_hybrid_regression] with_nexus..."
"${PYTHON}" "${NEXUS_ROOT}/scripts/bench/capability_ab_runner.py" \
    --tasks "${TASKS_FILE}" \
    --quadrant with_nexus \
    --output "${OUT_DIR}/with_nexus.json" 2>&1

echo "[daily_hybrid_regression] bare..."
"${PYTHON}" "${NEXUS_ROOT}/scripts/bench/capability_ab_runner.py" \
    --tasks "${TASKS_FILE}" \
    --quadrant bare \
    --output "${OUT_DIR}/bare.json" 2>&1

echo "[daily_hybrid_regression] local_only_executed..."
"${PYTHON}" "${NEXUS_ROOT}/scripts/bench/capability_ab_runner.py" \
    --tasks "${TASKS_FILE}" \
    --quadrant local_only_executed \
    --output "${OUT_DIR}/local_only.json" 2>&1

echo "[daily_hybrid_regression] cloud_exhausted..."
"${PYTHON}" "${NEXUS_ROOT}/scripts/bench/capability_ab_runner.py" \
    --tasks "${TASKS_FILE}" \
    --quadrant cloud_exhausted \
    --output "${OUT_DIR}/cloud_exhausted.json" 2>&1

echo "[daily_hybrid_regression] generating daily_hybrid_score.json..."
# Aggregate all quadrant results into daily score
"${PYTHYN}" -c "
import json, sys
from pathlib import Path

out_dir = Path('${OUT_DIR}')
with_nexus = json.loads((out_dir / 'with_nexus.json').read_text())
bare = json.loads((out_dir / 'bare.json').read_text())
local_only = json.loads((out_dir / 'local_only.json').read_text())
cloud_exhausted = json.loads((out_dir / 'cloud_exhausted.json').read_text())

def score(rows):
    eligible = [r for r in rows if r.get('run_eligible', True)]
    solved = [r for r in eligible if r.get('status') == 'SUCCESS']
    return {'total': len(rows), 'eligible': len(eligible), 'solved': len(solved),
            'score': round(len(solved)/len(eligible), 4) if eligible else 0.0}

report = {
    'schema': 'nexus.daily_hybrid_score.v1',
    'timestamp': 1234567890,
    'quadrants': {
        'with_nexus': score(with_nexus.get('rows', [with_nexus])),
        'bare': score(bare.get('rows', [bare])),
        'local_only_executed': score(local_only.get('rows', [local_only])),
        'cloud_exhausted': score(cloud_exhausted.get('rows', [cloud_exhausted])),
    },
}
(out_dir / 'daily_hybrid_score.json').write_text(json.dumps(report, indent=2))
print('[daily_hybrid_regression] done')
" 2>&1
