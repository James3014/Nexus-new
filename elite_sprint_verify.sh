#!/bin/bash
# elite_sprint_verify.sh

echo "🚀 Phase 1: Docker 驗證"
docker run --rm nexus-elite-swe python -c "
import sympy, numpy, mpmath
print('✅ Elite env: sympy', sympy.__version__)
print('✅ mpmath dps:', mpmath.mp.dps)
"

echo "🚀 Phase 2: 零污染基準 (5題 sympy)"
/Users/jameschen/.local/bin/uv run --with mpmath --with datasets --with pandas --with requests \
  scripts/engine/nexus_cli.py --eval-mode nexus:benchmark \
  --framework swe-verified \
  --tasks 5 \
  --target "sympy__sympy-13091,sympy__sympy-13372,sympy__sympy-13480,sympy__sympy-12419,sympy__sympy-13551" \
  --output "sympy_elite_5.csv"

echo "📊 真相矩陣"
# 使用之前的 results.jsonl (已經自動轉向)
cat sympy_elite_5.jsonl | head -n 3
