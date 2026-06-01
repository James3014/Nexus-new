from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

KeywordExtractor = Callable[[str], list[str]]
AUTO_FLOW_HISTORY_RELATIVE_PATH = Path(".nexus") / "reports" / "research" / "auto-flow-history.json"


def auto_flow_history_path(repo_root: Path) -> Path:
    return (repo_root / AUTO_FLOW_HISTORY_RELATIVE_PATH).resolve()


def auto_flow_key(target_file: str, test_file: str) -> str:
    return f"{target_file}|{test_file}"


@dataclass(frozen=True)
class HistorySignalStore:
    """Bounded reader for route history memory signals."""

    repo_root: Path
    max_entries: int = 200
    max_bytes: int = 1_000_000
    keyword_extractor: KeywordExtractor | None = None

    def load_memory_signal(self, *, task_desc: str, task_type: str) -> dict[str, Any]:
        payload = self.load_payload()
        if not payload:
            return {"memory_hits": 0, "memory_hints": [], "processed_entries": 0}

        extract = self.keyword_extractor or _extract_keywords
        task_keywords = set(extract(task_desc))
        memory_hits = 0
        memory_hints: list[str] = []
        processed_entries = 0

        for item in self._iter_recent_items(payload):
            processed_entries += 1
            if str(item.get("status", "")) != "SUCCESS":
                continue
            hist_task = str(item.get("task_desc", ""))
            hist_type = str(item.get("task_type", ""))
            hist_keywords = set(extract(hist_task))
            keyword_overlap = len(task_keywords & hist_keywords)
            type_match = bool(task_type and hist_type and task_type == hist_type)
            if keyword_overlap >= 2 and (type_match or keyword_overlap >= 3):
                memory_hits += 1
                if str(item.get("flow", "")):
                    memory_hints.append(f"flow:{item['flow']}")
                if str(item.get("reason", "")):
                    memory_hints.append(f"reason:{item['reason']}")

        uniq_hints = list(dict.fromkeys(memory_hints))[:4]
        return {
            "memory_hits": memory_hits,
            "memory_hints": uniq_hints,
            "processed_entries": processed_entries,
        }

    def load_payload(self) -> dict[str, Any]:
        return self._read_history_payload(auto_flow_history_path(self.repo_root))

    def write_payload(self, payload: dict[str, Any]) -> None:
        history_path = auto_flow_history_path(self.repo_root)
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def recent_for(self, *, target_file: str, test_file: str) -> list[dict[str, Any]]:
        payload = self.load_payload()
        recent = payload.get(auto_flow_key(target_file, test_file), [])
        return list(recent) if isinstance(recent, list) else []

    def write_recent_for(
        self,
        *,
        target_file: str,
        test_file: str,
        recent: list[dict[str, Any]],
        max_items: int = 200,
    ) -> dict[str, Any]:
        payload = self.load_payload()
        payload[auto_flow_key(target_file, test_file)] = recent[-max(1, max_items) :]
        self.write_payload(payload)
        return payload

    def _read_history_payload(self, history_path: Path) -> dict[str, Any]:
        if not history_path.exists():
            return {}
        try:
            if history_path.stat().st_size > self.max_bytes:
                return {}
            payload = json.loads(history_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _iter_recent_items(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for entries in payload.values():
            if not isinstance(entries, list):
                continue
            for item in entries:
                if isinstance(item, dict):
                    items.append(item)
        if self.max_entries <= 0:
            return []
        return items[-self.max_entries :]


def _extract_keywords(text: str, *, limit: int = 12) -> list[str]:
    tokens = re.findall(r"[a-zA-Z_]{4,}", (text or "").lower())
    stop = {
        "fix",
        "with",
        "under",
        "from",
        "that",
        "this",
        "task",
        "mode",
        "flow",
        "test",
        "file",
        "when",
    }
    out: list[str] = []
    for token in tokens:
        if token in stop:
            continue
        if token not in out:
            out.append(token)
        if len(out) >= limit:
            break
    return out
