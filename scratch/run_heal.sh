#!/bin/bash
export NEXUS_OLLAMA_MODEL="gemma4:12b"
export NEXUS_LOCAL_HEAL_ROOT_DIR="/Users/jameschen/workspace/astropy_12907"
export NEXUS_ASTROPY_LEGACY_PYTHON="/Users/jameschen/workspace/nexus/.venv_astropy_39/bin/python"

/Users/jameschen/workspace/nexus/.venv/bin/python -m benchmarking.swebench_lite.swe_local_heal \
  --task_manifest local-heal-113 \
  --limit 1 \
  --repro_script_file /Users/jameschen/workspace/astropy_12907/reproduce_bug.py \
  --output benchmarking/swebench_lite/predictions_local_heal_single.jsonl
