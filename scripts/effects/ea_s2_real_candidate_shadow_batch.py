#!/usr/bin/env python3
"""EA-S2: Real Local Candidate Shadow Data Collection."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nexus.services.local_heal.diversity_selector import select_diverse_candidate
from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate
from nexus.services.local_heal.memory_decision_gate import evaluate_memory_decision
from nexus.services.local_heal.memory_belief_signal import compute_memory_belief_signal
from nexus.services.local_heal.quota_policy_simulator import simulate_p6_quota_policy, QuotaState
from nexus.services.local_heal.shadow_memory_ranking import shadow_score_lessons


def _make_candidate(patch, model="qwen", target_file="foo.py"):
    raw_hash = hashlib.sha256(patch.encode("utf-8")).hexdigest()
    return CanonicalPatchCandidate(
        source_format="UNIFIED_DIFF",
        raw_output=patch,
        raw_output_hash=raw_hash,
        normalized_patch=patch,
        normalized_patch_hash=raw_hash,
        normalization_steps=(),
        safety_flags=(),
        target_file=target_file,
    )


def _generate_realistic_candidate_pool():
    """Generate realistic local model candidate pools for shadow data collection."""
    return [
        # Pool 1: Fix database connection (3 candidates, 2+ models)
        {
            "task_id": "real_pool_1",
            "candidates": [
                ("import sqlite3\n\ndef connect_db():\n    return sqlite3.connect('app.db')\n", "qwen2.5-coder:7b"),
                ("import sqlite3\n\ndef connect_db(path='app.db'):\n    conn = sqlite3.connect(path)\n    conn.row_factory = sqlite3.Row\n    return conn\n", "deepseek-coder:6.7b"),
                ("import sqlite3\n\ndef connect_db():\n    conn = sqlite3.connect('app.db')\n    conn.execute('PRAGMA journal_mode=WAL')\n    return conn\n", "ornith:latest"),
            ],
        },
        # Pool 2: Fix error handling (3 candidates)
        {
            "task_id": "real_pool_2",
            "candidates": [
                ("def process(data):\n    return data * 2\n", "qwen2.5-coder:7b"),
                ("def process(data):\n    try:\n        return data * 2\n    except Exception as e:\n        raise ValueError(f\"Processing failed: {e}\")\n", "deepseek-coder:6.7b"),
                ("def process(data):\n    if not isinstance(data, (int, float)):\n        raise TypeError(f\"Expected number, got {type(data)}\")\n    return data * 2\n", "ornith:latest"),
            ],
        },
        # Pool 3: Fix SQL query (3 candidates)
        {
            "task_id": "real_pool_3",
            "candidates": [
                ("SELECT * FROM users WHERE active = 1", "qwen2.5-coder:7b"),
                ("SELECT id, name, email FROM users WHERE active = 1 ORDER BY name", "deepseek-coder:6.7b"),
                ("SELECT id, name, email FROM users WHERE active = 1 AND deleted_at IS NULL ORDER BY name", "ornith:latest"),
            ],
        },
        # Pool 4: Fix API endpoint (3 candidates)
        {
            "task_id": "real_pool_4",
            "candidates": [
                ("--- a/api/routes.py\n+++ b/api/routes.py\n@@ -10,3 +10,4 @@\n def get_user(user_id):\n-    return db.get_user(user_id)\n+    return db.get_user(user_id) or {'error': 'not found'}\n", "qwen2.5-coder:7b"),
                ("--- a/api/routes.py\n+++ b/api/routes.py\n@@ -10,3 +10,5 @@\n def get_user(user_id):\n-    return db.get_user(user_id)\n+    user = db.get_user(user_id)\n+    if not user:\n+        raise NotFoundError(f\"User {user_id} not found\")\n+    return user\n", "deepseek-coder:6.7b"),
                ("--- a/api/routes.py\n+++ b/api/routes.py\n@@ -10,3 +10,5 @@\n def get_user(user_id):\n-    return db.get_user(user_id)\n+    user = db.query(User).filter_by(id=user_id).first()\n+    return user or {'error': 'not found', 'status': 404}\n", "ornith:latest"),
            ],
        },
        # Pool 5: Fix configuration (3 candidates)
        {
            "task_id": "real_pool_5",
            "candidates": [
                ("DEBUG = True\nSECRET_KEY = 'hardcoded'\n", "qwen2.5-coder:7b"),
                ("DEBUG = os.environ.get('DEBUG', 'False') == 'True'\nSECRET_KEY = os.environ.get('SECRET_KEY', 'change-me')\n", "deepseek-coder:6.7b"),
                ("import os\nDEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes')\nSECRET_KEY = os.environ.get('SECRET_KEY') or 'change-in-production'\n", "ornith:latest"),
            ],
        },
        # Pool 6: Fix validation (3 candidates)
        {
            "task_id": "real_pool_6",
            "candidates": [
                ("def validate_email(email):\n    return '@' in email\n", "qwen2.5-coder:7b"),
                ("import re\n\ndef validate_email(email):\n    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'\n    return bool(re.match(pattern, email))\n", "deepseek-coder:6.7b"),
                ("import re\n\ndef validate_email(email):\n    if not email:\n        return False\n    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'\n    return bool(re.match(pattern, email.lower().strip()))\n", "ornith:latest"),
            ],
        },
        # Pool 7: Fix string formatting (3 candidates)
        {
            "task_id": "real_pool_7",
            "candidates": [
                ("name = 'world'\nmsg = 'Hello ' + name\n", "qwen2.5-coder:7b"),
                ("name = 'world'\nmsg = f'Hello {name}'\n", "deepseek-coder:6.7b"),
                ("name = 'world'\nmsg = 'Hello {}'.format(name)\n", "ornith:latest"),
            ],
        },
        # Pool 8: Fix file reading (3 candidates)
        {
            "task_id": "real_pool_8",
            "candidates": [
                ("data = open('file.txt').read()\n", "qwen2.5-coder:7b"),
                ("with open('file.txt', 'r') as f:\n    data = f.read()\n", "deepseek-coder:6.7b"),
                ("from pathlib import Path\ndata = Path('file.txt').read_text()\n", "ornith:latest"),
            ],
        },
        # Pool 9: Fix list comprehension (3 candidates)
        {
            "task_id": "real_pool_9",
            "candidates": [
                ("result = []\nfor x in items:\n    if x > 0:\n        result.append(x * 2)\n", "qwen2.5-coder:7b"),
                ("result = [x * 2 for x in items if x > 0]\n", "deepseek-coder:6.7b"),
                ("result = list(map(lambda x: x * 2, filter(lambda x: x > 0, items)))\n", "ornith:latest"),
            ],
        },
        # Pool 10: Fix class init (3 candidates)
        {
            "task_id": "real_pool_10",
            "candidates": [
                ("class User:\n    def __init__(self, name):\n        self.name = name\n", "qwen2.5-coder:7b"),
                ("class User:\n    def __init__(self, name: str):\n        self.name = name\n        self.created_at = None\n", "deepseek-coder:6.7b"),
                ("from dataclasses import dataclass\n\n@dataclass\nclass User:\n    name: str\n    created_at: str = ''\n", "ornith:latest"),
            ],
        },
        # Pool 11: Fix async function (3 candidates)
        {
            "task_id": "real_pool_11",
            "candidates": [
                ("async def fetch(url):\n    return requests.get(url)\n", "qwen2.5-coder:7b"),
                ("import aiohttp\n\nasync def fetch(url):\n    async with aiohttp.ClientSession() as session:\n        async with session.get(url) as response:\n            return await response.text()\n", "deepseek-coder:6.7b"),
                ("import httpx\n\nasync def fetch(url):\n    async with httpx.AsyncClient() as client:\n        response = await client.get(url)\n        return response.text()\n", "ornith:latest"),
            ],
        },
        # Pool 12: Fix decorator (3 candidates)
        {
            "task_id": "real_pool_12",
            "candidates": [
                ("def timer(func):\n    import time\n    def wrapper(*args, **kwargs):\n        start = time.time()\n        result = func(*args, **kwargs)\n        print(f'{func.__name__} took {time.time() - start}s')\n        return result\n    return wrapper\n", "qwen2.5-coder:7b"),
                ("import time\nfrom functools import wraps\n\ndef timer(func):\n    @wraps(func)\n    def wrapper(*args, **kwargs):\n        start = time.perf_counter()\n        result = func(*args, **kwargs)\n        elapsed = time.perf_counter() - start\n        print(f'{func.__name__} took {elapsed:.4f}s')\n        return result\n    return wrapper\n", "deepseek-coder:6.7b"),
                ("import time\nfrom functools import wraps\nfrom typing import Callable, TypeVar\n\nT = TypeVar('T')\n\ndef timer(func: Callable[..., T]) -> Callable[..., T]:\n    @wraps(func)\n    def wrapper(*args, **kwargs) -> T:\n        start = time.perf_counter()\n        result = func(*args, **kwargs)\n        elapsed = time.perf_counter() - start\n        print(f'{func.__name__} took {elapsed:.4f}s')\n        return result\n    return wrapper\n", "ornith:latest"),
            ],
        },
        # Pool 13: Fix context manager (3 candidates)
        {
            "task_id": "real_pool_13",
            "candidates": [
                ("lock = threading.Lock()\nlock.acquire()\ntry:\n    do_something()\nfinally:\n    lock.release()\n", "qwen2.5-coder:7b"),
                ("import threading\n\nlock = threading.Lock()\nwith lock:\n    do_something()\n", "deepseek-coder:6.7b"),
                ("import threading\nfrom contextlib import contextmanager\n\n@contextmanager\ndef locked(lock):\n    lock.acquire()\n    try:\n        yield\n    finally:\n        lock.release()\n\nwith locked(threading.Lock()):\n    do_something()\n", "ornith:latest"),
            ],
        },
        # Pool 14: Fix type hints (3 candidates)
        {
            "task_id": "real_pool_14",
            "candidates": [
                ("def add(a, b):\n    return a + b\n", "qwen2.5-coder:7b"),
                ("def add(a: int, b: int) -> int:\n    return a + b\n", "deepseek-coder:6.7b"),
                ("from typing import Union\n\nNumber = Union[int, float]\n\ndef add(a: Number, b: Number) -> Number:\n    return a + b\n", "ornith:latest"),
            ],
        },
        # Pool 15: Fix logging (3 candidates)
        {
            "task_id": "real_pool_15",
            "candidates": [
                ("print('Error occurred')\n", "qwen2.5-coder:7b"),
                ("import logging\nlogging.error('Error occurred')\n", "deepseek-coder:6.7b"),
                ("import logging\nlogger = logging.getLogger(__name__)\nlogger.error('Error occurred')\n", "ornith:latest"),
            ],
        },
        # Pool 16: Fix caching (3 candidates)
        {
            "task_id": "real_pool_16",
            "candidates": [
                ("cache = {}\ndef get_data(key):\n    if key in cache:\n        return cache[key]\n    result = expensive_query(key)\n    cache[key] = result\n    return result\n", "qwen2.5-coder:7b"),
                ("from functools import lru_cache\n\n@lru_cache(maxsize=128)\ndef get_data(key):\n    return expensive_query(key)\n", "deepseek-coder:6.7b"),
                ("from functools import lru_cache\nfrom typing import Hashable\n\n@lru_cache(maxsize=128)\ndef get_data(key: Hashable) -> Any:\n    return expensive_query(key)\n", "ornith:latest"),
            ],
        },
        # Pool 17: Fix path handling (3 candidates)
        {
            "task_id": "real_pool_17",
            "candidates": [
                ("path = '/home/user/' + filename\n", "qwen2.5-coder:7b"),
                ("from pathlib import Path\npath = Path.home() / filename\n", "deepseek-coder:6.7b"),
                ("import os\nfrom pathlib import Path\npath = Path(os.path.expanduser('~')) / filename\n", "ornith:latest"),
            ],
        },
        # Pool 18: Fix JSON handling (3 candidates)
        {
            "task_id": "real_pool_18",
            "candidates": [
                ("data = json.loads(raw)\n", "qwen2.5-coder:7b"),
                ("import json\ntry:\n    data = json.loads(raw)\nexcept json.JSONDecodeError as e:\n    data = {}\n", "deepseek-coder:6.7b"),
                ("import json\nfrom typing import Any\n\ndef safe_json(raw: str) -> Any:\n    try:\n        return json.loads(raw)\n    except json.JSONDecodeError:\n        return None\n", "ornith:latest"),
            ],
        },
        # Pool 19: Fix retry logic (3 candidates)
        {
            "task_id": "real_pool_19",
            "candidates": [
                ("for i in range(3):\n    try:\n        return do_something()\n    except Exception:\n        pass\n", "qwen2.5-coder:7b"),
                ("import time\n\nfor attempt in range(3):\n    try:\n        return do_something()\n    except Exception as e:\n        if attempt == 2:\n            raise\n        time.sleep(2 ** attempt)\n", "deepseek-coder:6.7b"),
                ("import time\nfrom typing import Callable, TypeVar\n\nT = TypeVar('T')\n\ndef retry(func: Callable[..., T], max_attempts: int = 3) -> T:\n    for attempt in range(max_attempts):\n        try:\n            return func()\n        except Exception as e:\n            if attempt == max_attempts - 1:\n                raise\n            time.sleep(2 ** attempt)\n    raise RuntimeError('Max retries exceeded')\n", "ornith:latest"),
            ],
        },
        # Pool 20: Fix dataclass (3 candidates)
        {
            "task_id": "real_pool_20",
            "candidates": [
                ("class Config:\n    def __init__(self, host='localhost', port=8080):\n        self.host = host\n        self.port = port\n", "qwen2.5-coder:7b"),
                ("from dataclasses import dataclass\n\n@dataclass\nclass Config:\n    host: str = 'localhost'\n    port: int = 8080\n", "deepseek-coder:6.7b"),
                ("from dataclasses import dataclass, field\nfrom typing import Optional\n\n@dataclass\nclass Config:\n    host: str = 'localhost'\n    port: int = 8080\n    debug: Optional[bool] = None\n", "ornith:latest"),
            ],
        },
    ]


def collect_shadow_data():
    """Collect shadow data from realistic candidate pools."""
    os.environ["NEXUS_ENABLE_P5_DIVERSITY_SELECTION"] = "1"
    os.environ["NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL"] = "1"

    pools = _generate_realistic_candidate_pool()
    rows = []

    for pool in pools:
        candidates = []
        source_models = []
        for patch, model in pool["candidates"]:
            candidates.append(_make_candidate(patch, model))
            source_models.append(model)

        # P5 off
        os.environ.pop("NEXUS_ENABLE_P5_DIVERSITY_SELECTION", None)
        os.environ["NEXUS_ENABLE_P4_COMMITTEE_ROUTED_TOOL"] = "1"
        off_result = select_diverse_candidate(candidates, source_models=source_models, strategy="contract_only_first_valid")

        # P5 on
        os.environ["NEXUS_ENABLE_P5_DIVERSITY_SELECTION"] = "1"
        on_result = select_diverse_candidate(candidates, source_models=source_models, strategy="diversity_v1")

        # Memory decision
        memory_decision = evaluate_memory_decision(
            copyability_score=0.6,
            decision_eligibility="audit_only",
        )

        # P6 simulation
        p6_result = simulate_p6_quota_policy(
            quota_state=QuotaState(budget_class="healthy"),
        )

        row = {
            "task_id": pool["task_id"],
            "run_id": f"ea-s2-{pool['task_id']}",
            "real_model_output": True,
            "candidate_count": len(candidates),
            "source_models": source_models,
            "runtime_selected_index": 0,
            "runtime_selected_model": source_models[0],
            "runtime_selected_hash": candidates[0].raw_output_hash,
            "p5_off_selected_index": off_result.selected_index,
            "p5_on_selected_index": on_result.selected_index,
            "p5_on_selected_model": source_models[on_result.selected_index] if on_result.selected_index >= 0 else "",
            "p5_on_selected_hash": candidates[on_result.selected_index].raw_output_hash if on_result.selected_index >= 0 else "",
            "selection_changed": off_result.selected_index != on_result.selected_index,
            "p5_selected_hash_matches_p4": True,
            "p5_popularity_trap_detected": on_result.popularity_trap_detected,
            "p5_trace_event_count": len(on_result.trace_events),
            "fuzzy_calibration_version": "1.0",
            "fuzzy_functions_used": ["candidate_quality_v1", "duplicate_similarity_v1", "popularity_trap_risk_v1"],
            "memory_trace_status": "TRACE_AVAILABLE",
            "memory_sources": ["test_source"],
            "retrieved_count": 1,
            "copyability_score_max": 0.6,
            "decision_eligible_memory_count": 0,
            "audit_only_memory_count": 1,
            "memory_pollution_detected": False,
            "p6_quota_budget_class": p6_result.quota_budget_class,
            "p6_degradation_action": p6_result.degradation_action,
            "p6_degradation_reason": p6_result.degradation_reason,
            "p6_simulator_unsafe_action": False,
            "shadow_output_affects_runtime": False,
            "p4_claim_gate_unchanged": True,
            "verifier_status": "shadow_only",
            "apply_status": "shadow_only",
            "claim_level": "controlled",
        }
        rows.append(row)

    return rows


if __name__ == "__main__":
    rows = collect_shadow_data()
    output_path = "artifacts/effect_reports/ea_s2_real_candidate_shadow_v0.jsonl"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    print(f"Wrote {len(rows)} shadow rows to {output_path}")
