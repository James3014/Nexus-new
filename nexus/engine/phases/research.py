#!/usr/bin/env python3
import json
import subprocess
import os
import time
import logging
import shutil
from typing import Any, Dict
from nexus.engine.phases.base import BasePhaseHandler
from nexus.core.state_contracts import NexusState

logger = logging.getLogger(__name__)


class ResearchPhaseHandler(BasePhaseHandler):
    """
    🌐 Phase X: Research
    封裝外部研究調用與追蹤紀錄（chub 優先，失敗回退 felo）。
    """

    def __init__(self, project_root: Any, run_dir: Any):
        super().__init__(project_root, run_dir)

    def run(self, state: NexusState, context: Dict[str, Any]) -> Dict[str, Any]:
        task = str(context.get("task") or "").strip()
        logger.info("[Nexus:Phase-X] External Research for: %s", task or "<empty-task>")
        if not task:
            return {
                "findings": ["Empty research task."],
                "source": "INTERNAL",
                "status": "FAIL",
                "tokens_used": 0,
            }

        research_file = self.run_dir / "researchpack.json"
        if research_file.exists():
            logger.info("[X-Stage] Cache hit: loading local researchpack.")
            return json.loads(research_file.read_text())

        db = self._get_lancedb()
        table_name = "research_cache"
        cached_pack = self._load_lancedb_cache(db, table_name, task, research_file)
        if cached_pack:
            return cached_pack

        query = f"{task} (provide a concise summary only, limit to 300 words)"
        research_pack = self._run_external_research(query)

        if research_pack.get("status") != "SUCCESS":
            research_pack = {
                "findings": [
                    "External research unavailable, continue with internal reasoning."
                ],
                "source": research_pack.get("source", "INTERNAL"),
                "status": "FAIL",
                "tokens_used": research_pack.get("tokens_used", 0),
                "token_raw_model": 0,
                "token_fallback_est": research_pack.get("tokens_used", 0),
                "token_capture_status": "fallback_est",
                "error": research_pack.get("error"),
            }

        self._save_lancedb_cache(db, table_name, task, research_pack)
        research_file.write_text(json.dumps(research_pack, ensure_ascii=False))
        return research_pack

    def _run_external_research(self, query: str) -> Dict[str, Any]:
        provider = os.getenv("NEXUS_RESEARCH_PROVIDER", "auto").strip().lower()
        providers = []
        if provider in {"auto", "chub"}:
            providers.append("chub")
        if provider in {"auto", "felo"}:
            providers.append("felo")
        if provider not in {"auto", "chub", "felo"}:
            providers = ["felo"]

        failures = []
        for p in providers:
            if p == "chub":
                result = self._run_chub(query)
            else:
                result = self._run_felo(query)
            if result.get("status") == "SUCCESS":
                return result
            failures.append(f"{p}:{result.get('error', 'unknown')}")

        return {
            "findings": [],
            "source": "INTERNAL",
            "status": "FAIL",
            "tokens_used": 0,
            "error": "; ".join(failures),
        }

    def _run_chub(self, query: str) -> Dict[str, Any]:
        chub_bin = os.getenv("NEXUS_CHUB_BIN", "chub")
        if shutil.which(chub_bin) is None:
            return {
                "findings": [],
                "source": "chub",
                "status": "FAIL",
                "tokens_used": 0,
                "error": "chub_not_installed",
            }

        cmd = [
            chub_bin,
            "--json",
            "search",
            query,
            "--limit",
            os.getenv("NEXUS_CHUB_LIMIT", "5"),
        ]
        env = os.environ.copy()
        # Avoid EPERM on ~/.chub in restricted environments; keep cache under run_dir by default.
        chub_home = env.get("CHUB_HOME") or str(self.run_dir / ".chub")
        os.makedirs(chub_home, exist_ok=True)
        env["CHUB_HOME"] = chub_home

        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False, env=env
        )
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        if result.returncode != 0:
            return {
                "findings": [],
                "source": "chub",
                "status": "FAIL",
                "tokens_used": len(stdout) // 4,
                "error": stderr or f"exit_{result.returncode}",
            }
        try:
            payload = json.loads(stdout) if stdout else {}
            if isinstance(payload, dict) and payload.get("error"):
                return {
                    "findings": [],
                    "source": "chub",
                    "status": "FAIL",
                    "tokens_used": len(stdout) // 4,
                    "error": payload.get("error"),
                }
            findings = payload if isinstance(payload, list) else [payload]
            return {
                "findings": [
                    json.dumps(item, ensure_ascii=False) for item in findings[:5]
                ],
                "source": "chub",
                "status": "SUCCESS",
                "tokens_used": len(stdout) // 4 + 50,
                "token_raw_model": 0,
                "token_fallback_est": len(stdout) // 4 + 50,
                "token_capture_status": "fallback_est",
            }
        except Exception as exc:
            return {
                "findings": [],
                "source": "chub",
                "status": "FAIL",
                "tokens_used": 0,
                "error": f"json_parse_error:{exc}",
            }

    def _run_felo(self, query: str) -> Dict[str, Any]:
        cmd = ["npx", "-y", "@willh/felo-cli", "--json", query]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        if result.returncode != 0:
            return {
                "findings": [],
                "source": "Felo-CLI",
                "status": "FAIL",
                "tokens_used": len(stdout) // 4 + 50,
                "error": stderr or f"exit_{result.returncode}",
            }
        return {
            "findings": [stdout] if stdout else [],
            "source": "Felo-CLI",
            "status": "SUCCESS",
            "tokens_used": len(stdout) // 4 + 100,
            "token_raw_model": 0,
            "token_fallback_est": len(stdout) // 4 + 100,
            "token_capture_status": "fallback_est",
        }

    def _get_lancedb(self):
        try:
            import lancedb  # type: ignore

            db_path = os.path.expanduser("~/.openclaw/memory/lancedb-research")
            return lancedb.connect(db_path)
        except Exception as exc:
            logger.warning("[X-Stage] LanceDB unavailable: %s", exc)
            return None

    def _load_lancedb_cache(self, db, table_name: str, task: str, research_file):
        if db is None:
            return None
        try:
            tbl = db.open_table(table_name)
            cached = (
                tbl.to_pandas().query(f"task == '{task}'").to_dict(orient="records")
            )
            if cached:
                logger.info("[X-Stage] Found cached research in LanceDB.")
                res = json.loads(cached[0]["pack"])
                research_file.write_text(json.dumps(res, ensure_ascii=False))
                return res
        except Exception:
            return None
        return None

    def _save_lancedb_cache(
        self, db, table_name: str, task: str, research_pack: Dict[str, Any]
    ):
        if db is None:
            return
        try:
            data = [
                {
                    "task": task,
                    "pack": json.dumps(research_pack),
                    "timestamp": time.time(),
                }
            ]
            has_list_tables = hasattr(db, "list_tables")
            table_names = (
                set(db.list_tables()) if has_list_tables else set(db.table_names())
            )
            if table_name not in table_names:
                db.create_table(table_name, data=data)
            else:
                db.open_table(table_name).add(data)
        except Exception:
            return
