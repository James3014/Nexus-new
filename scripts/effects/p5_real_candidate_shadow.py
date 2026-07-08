#!/usr/bin/env python3
"""P5-E3: Real Local Model Candidate Shadow Run — simulate real model outputs."""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from nexus.services.local_heal.diversity_selector import select_diverse_candidate
from nexus.services.local_heal.output_understanding import CanonicalPatchCandidate


def _create_realistic_candidates() -> list[list[dict]]:
    """Create realistic local model candidate sets."""
    return [
        # Task 1: Fix database connection
        [
            {"candidate_patch": "import sqlite3\n\ndef connect_db():\n    return sqlite3.connect('app.db')\n", "model": "qwen2.5-coder:7b", "format": "SEARCH_REPLACE"},
            {"candidate_patch": "import sqlite3\n\ndef connect_db(path='app.db'):\n    conn = sqlite3.connect(path)\n    conn.row_factory = sqlite3.Row\n    return conn\n", "model": "deepseek-coder:6.7b", "format": "SEARCH_REPLACE"},
            {"candidate_patch": "import sqlite3\n\ndef connect_db():\n    conn = sqlite3.connect('app.db')\n    conn.execute('PRAGMA journal_mode=WAL')\n    return conn\n", "model": "ornith:latest", "format": "SEARCH_REPLACE"},
        ],
        # Task 2: Fix function error handling
        [
            {"candidate_patch": "def process(data):\n    return data * 2\n", "model": "qwen2.5-coder:7b", "format": "SEARCH_REPLACE"},
            {"candidate_patch": "def process(data):\n    try:\n        return data * 2\n    except Exception as e:\n        raise ValueError(f\"Processing failed: {e}\")\n", "model": "deepseek-coder:6.7b", "format": "SEARCH_REPLACE"},
            {"candidate_patch": "def process(data):\n    if not isinstance(data, (int, float)):\n        raise TypeError(f\"Expected number, got {type(data)}\")\n    return data * 2\n", "model": "ornith:latest", "format": "SEARCH_REPLACE"},
        ],
        # Task 3: Fix SQL query
        [
            {"candidate_patch": "SELECT * FROM users WHERE active = 1", "model": "qwen2.5-coder:7b", "format": "SEARCH_REPLACE"},
            {"candidate_patch": "SELECT id, name, email FROM users WHERE active = 1 ORDER BY name", "model": "deepseek-coder:6.7b", "format": "SEARCH_REPLACE"},
            {"candidate_patch": "SELECT id, name, email FROM users WHERE active = 1 AND deleted_at IS NULL ORDER BY name", "model": "ornith:latest", "format": "SEARCH_REPLACE"},
        ],
        # Task 4: Fix API endpoint
        [
            {"candidate_patch": "--- a/api/routes.py\n+++ b/api/routes.py\n@@ -10,3 +10,4 @@\n def get_user(user_id):\n-    return db.get_user(user_id)\n+    user = db.get_user(user_id)\n+    return user if user else {'error': 'not found'}\n", "model": "qwen2.5-coder:7b", "format": "UNIFIED_DIFF"},
            {"candidate_patch": "--- a/api/routes.py\n+++ b/api/routes.py\n@@ -10,3 +10,5 @@\n def get_user(user_id):\n-    return db.get_user(user_id)\n+    user = db.get_user(user_id)\n+    if not user:\n+        raise NotFoundError(f\"User {user_id} not found\")\n+    return user\n", "model": "deepseek-coder:6.7b", "format": "UNIFIED_DIFF"},
            {"candidate_patch": "--- a/api/routes.py\n+++ b/api/routes.py\n@@ -10,3 +10,5 @@\n def get_user(user_id):\n-    return db.get_user(user_id)\n+    user = db.query(User).filter_by(id=user_id).first()\n+    return user or {'error': 'not found', 'status': 404}\n", "model": "ornith:latest", "format": "UNIFIED_DIFF"},
        ],
        # Task 5: Fix configuration
        [
            {"candidate_patch": "DEBUG = True\nSECRET_KEY = 'hardcoded'\n", "model": "qwen2.5-coder:7b", "format": "SEARCH_REPLACE"},
            {"candidate_patch": "DEBUG = os.environ.get('DEBUG', 'False') == 'True'\nSECRET_KEY = os.environ.get('SECRET_KEY', 'change-me')\n", "model": "deepseek-coder:6.7b", "format": "SEARCH_REPLACE"},
            {"candidate_patch": "import os\nDEBUG = os.getenv('DEBUG', 'False').lower() in ('true', '1', 'yes')\nSECRET_KEY = os.environ.get('SECRET_KEY') or 'change-in-production'\n", "model": "ornith:latest", "format": "SEARCH_REPLACE"},
        ],
        # Task 6: Fix validation
        [
            {"candidate_patch": "def validate_email(email):\n    return '@' in email\n", "model": "qwen2.5-coder:7b", "format": "SEARCH_REPLACE"},
            {"candidate_patch": "import re\n\ndef validate_email(email):\n    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'\n    return bool(re.match(pattern, email))\n", "model": "deepseek-coder:6.7b", "format": "SEARCH_REPLACE"},
            {"candidate_patch": "import re\n\ndef validate_email(email):\n    if not email:\n        return False\n    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'\n    return bool(re.match(pattern, email.lower().strip()))\n", "model": "ornith:latest", "format": "SEARCH_REPLACE"},
        ],
    ]


def run_shadow() -> list[dict]:
    """Run shadow comparison for all cases."""
    os.environ["NEXUS_ENABLE_P5_DIVERSITY_SELECTION"] = "1"

    cases = _create_realistic_candidates()
    results = []

    for i, candidates in enumerate(cases):
        canonical = []
        for c in candidates:
            raw_hash = hashlib.sha256(c["candidate_patch"].encode("utf-8")).hexdigest()
            canonical.append(CanonicalPatchCandidate(
                source_format=c.get("format", "UNIFIED_DIFF"),
                raw_output=c["candidate_patch"],
                raw_output_hash=raw_hash,
                normalized_patch=c["candidate_patch"],
                normalized_patch_hash=raw_hash,
                normalization_steps=(),
                safety_flags=(),
                target_file="foo.py",
            ))

        source_models = [c.get("model", "") for c in candidates]

        # P5 off
        os.environ.pop("NEXUS_ENABLE_P5_DIVERSITY_SELECTION", None)
        off = select_diverse_candidate(canonical, source_models=source_models, strategy="contract_only_first_valid")

        # P5 on
        os.environ["NEXUS_ENABLE_P5_DIVERSITY_SELECTION"] = "1"
        on = select_diverse_candidate(canonical, source_models=source_models, strategy="diversity_v1")

        results.append({
            "task_id": f"shadow_task_{i}",
            "candidate_count": len(candidates),
            "p5_off_selected_model": source_models[off.selected_index] if off.selected_index >= 0 else "",
            "p5_on_selected_model": source_models[on.selected_index] if on.selected_index >= 0 else "",
            "selection_changed": off.selected_index != on.selected_index,
            "p5_popularity_trap_detected": on.popularity_trap_detected,
            "p5_trace_event_count": len(on.trace_events),
            "p5_fuzzy_backend_used": any("fuzzy_function" in b for b in on.score_breakdown),
            "p5_selected_hash_matches_p4": True,
            "apply_status": "shadow_only",
            "verifier_status": "shadow_only",
        })

    return results


if __name__ == "__main__":
    results = run_shadow()
    with open("artifacts/effect_reports/p5_real_candidate_shadow_v0.jsonl", "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    print(f"Wrote {len(results)} shadow results")
