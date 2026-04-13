#!/bin/bash
# L1: 快速驗證層 (Fast Verification)
set -e
echo "🔍 Checking environment..."
uv run python -m pytest --version
echo "🚀 [L1] Running core fast tests..."
uv run python -m pytest tests/core tests/services/test_policy_gate.py -m "not slow" -q --maxfail=3
echo "✅ [L1] Fast tests passed."
