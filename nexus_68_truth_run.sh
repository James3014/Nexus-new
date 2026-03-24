#!/bin/bash
# nexus_68_truth_run.sh (Param-Order-Sync-V2)

echo "🚀 啟動真實 68% 終極考！ (Anti-Phantom Version)"

# Step 1: 環境鎖定與驗證
echo "🔍 [Step 1] Config Verify..."
uv run scripts/engine/nexus_cli.py \
  --eval-mode \
  --guard-phantom \
  --guard-recursion \
  nexus:debug --strict

# Step 2: 啟動 20 題科學王者專項測試
echo "📊 [Step 2] Science Swarm Benchmark (n=20)..."
uv run --with datasets --with pandas --with requests scripts/engine/nexus_cli.py \
  --eval-mode \
  --guard-phantom \
  --guard-recursion \
  nexus:benchmark \
  --framework swe-verified \
  --tasks 20 \
  --repos "sympy numpy astropy pytorch scipy" \
  --model claude-4.5-math \
  --strict-proof \
  --output real_68_challenge.jsonl

# Step 3: 真相矩陣計算
echo "📊 [Step 3] Computing Truth Matrix..."
python3 scripts/engine/compute_truth_scores.py real_68_challenge.jsonl

# Step 4: 真相矩陣統計
echo "🧠 [Step 4] Truth Matrix Result..."
if [ -f "real_68_challenge.jsonl" ]; then
  uv run --with pandas compute_truth_scores.py real_68_challenge.jsonl
else
  echo "❌ Error: real_68_challenge.jsonl not found."
fi
```
