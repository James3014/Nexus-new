import time
import json
import os
import argparse
from unittest.mock import MagicMock, patch
from nexus.core.context_adapter import ContextAdapter

def run_benchmark(num_iterations=5):
    """
    🎯 Task-2: Benchmark Artifact
    Compares legacy vs leanctx provider with synthetic inputs.
    Outputs JSON summary fields.
    """
    results = []
    
    # Mock legacy hub
    mock_hub = MagicMock()
    mock_hub.assemble_context.return_value = "X" * 1000 # 1KB synthetic context
    
    # Provider 1: Legacy
    with patch.dict(os.environ, {"NEXUS_CONTEXT_PROVIDER": "legacy"}):
        adapter = ContextAdapter(mock_hub)
        for i in range(num_iterations):
            start = time.perf_counter()
            adapter.assemble_context(f"task-{i}", [1, 2])
            end = time.perf_counter()
            results.append({
                "iteration": i,
                "provider": "legacy",
                "latency_ms": (end - start) * 1000,
                "status": "SUCCESS",
                "fallback_used": False
            })

    # Provider 2: LeanCtx (Simulated SUCCESS)
    with patch.dict(os.environ, {"NEXUS_CONTEXT_PROVIDER": "leanctx"}):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="Y" * 1000)
            adapter = ContextAdapter(mock_hub)
            for i in range(num_iterations):
                start = time.perf_counter()
                adapter.assemble_context(f"task-{i}", [1, 2])
                end = time.perf_counter()
                results.append({
                    "iteration": i,
                    "provider": "leanctx",
                    "latency_ms": (end - start) * 1000,
                    "status": "SUCCESS",
                    "fallback_used": False
                })

    # Provider 3: LeanCtx (Simulated FALLBACK)
    with patch.dict(os.environ, {"NEXUS_CONTEXT_PROVIDER": "leanctx"}):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="fail")
            adapter = ContextAdapter(mock_hub)
            for i in range(num_iterations):
                start = time.perf_counter()
                adapter.assemble_context(f"task-{i}", [1, 2])
                end = time.perf_counter()
                results.append({
                    "iteration": i,
                    "provider": "leanctx",
                    "latency_ms": (end - start) * 1000,
                    "status": "FALLBACK",
                    "fallback_used": True
                })

    print(json.dumps(results, indent=2))
    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=3)
    args = parser.parse_args()
    run_benchmark(args.iterations)
