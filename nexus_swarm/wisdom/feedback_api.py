# 🛡️ Nexus Wisdom Feedback API
# [ARCH-EVO: v23 WISDOM EDITION FEEDBACK]

import os
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from .online_learner import BayesianLearner

# 🛡️ Alignment with v22 Production Truth Sources
REPO_ROOT = Path(__file__).resolve().parents[2]
METRICS_DIR = REPO_ROOT / ".nexus" / "metrics"
FEEDBACK_LOG = METRICS_DIR / "feedback_events.jsonl"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WISDOM-FEEDBACK")

class FeedbackAPI:
    def __init__(self):
        os.makedirs(METRICS_DIR, exist_ok=True)
        self.learner = BayesianLearner(str(REPO_ROOT / "nexus_swarm" / "wisdom" / "learner_stats.json"))

    def submit_feedback(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        [Immutable Feedback Contract Enforcement]
        Required: task_id, pattern_id, actor, source, type
        """
        required_fields = ["task_id", "pattern_id", "actor", "source", "type"]
        for field in required_fields:
            if field not in payload:
                raise ValueError(f"Missing required field in feedback payload: {field}")

        # 🛡️ Add server-side timestamp to ensure immutable trace
        event = {
            **payload,
            "recorded_at": datetime.utcnow().isoformat(),
            "version": "v23.Phase2"
        }

        # 1. Archive to v22 Metrics (Evidence Chain)
        self._archive_to_metrics(event)

        # 2. Update Bayesian Learner
        update_res = self.learner.update_feedback(
            pattern_id=event["pattern_id"],
            feedback_type=event["type"],
            actor_role=event.get("actor_role", "human") # mapping actor info to role if needed
        )

        logger.info(f"✅ Feedback recorded for Task {event['task_id']} | Pattern {event['pattern_id']}")
        return {
            "status": "success",
            "event_id": event["task_id"],
            "update": update_res
        }

    def _archive_to_metrics(self, event: Dict[str, Any]):
        """寫入 v22 已定義的 metrics 真值來源，支援可審計性"""
        with open(FEEDBACK_LOG, "a") as f:
            f.write(json.dumps(event) + "\n")

if __name__ == "__main__":
    # Internal Integration Test
    api = FeedbackAPI()
    test_payload = {
        "task_id": "T-TEST-001",
        "pattern_id": "rust-lock-poison-22",
        "actor": "commander",
        "actor_role": "admin",
        "source": "cli_test",
        "type": "false_positive",
        "timestamp": datetime.utcnow().isoformat()
    }
    res = api.submit_feedback(test_payload)
    print(json.dumps(res, indent=2))
