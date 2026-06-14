"""Failure Memory Bank: cache and retrieve past repair failures to avoid repeating mistakes."""
import json
from pathlib import Path
from typing import List, Dict, Any
from collections import Counter

EVENTS_PATH = Path(".nexus/metrics/skill_outcome_events.jsonl")
MAX_FAILURES = 20  # Max failures to inject into prompt


def load_failure_patterns(project_root: Path, limit: int = MAX_FAILURES) -> List[str]:
    """Load recent failure patterns from outcome events."""
    events_file = project_root / EVENTS_PATH
    if not events_file.exists():
        return []
    
    failures = []
    try:
        with events_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                    if event.get("fail") and event.get("phase") == "R":
                        reason = event.get("status", "") or event.get("error", "")
                        if reason and reason not in ("", "unknown"):
                            failures.append(reason)
                except json.JSONDecodeError:
                    continue
    except Exception:
        return []
    
    # Count and return most common failure patterns
    counter = Counter(failures)
    return [f"{reason} (x{count})" for reason, count in counter.most_common(limit)]


def build_failure_context(project_root: Path) -> str:
    """Build failure context string for prompt injection."""
    patterns = load_failure_patterns(project_root)
    if not patterns:
        return ""
    
    lines = ["[PAST FAILURES - DO NOT REPEAT]"]
    for p in patterns:
        lines.append(f"- {p}")
    return "\n".join(lines)
