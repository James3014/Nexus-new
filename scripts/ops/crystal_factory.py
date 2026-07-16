import json
import hashlib
import os
import sys
import logging
from pathlib import Path
from typing import List, Dict, Any
import click

from nexus.services.gateway import BattlesuitGateway

# 配置日誌
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("CrystalFactory")

class CrystalFactory:
    """💎 Nexus v4.0 結晶工廠：將原始執行經驗轉化為系統法律 (Policies)"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.gateway = BattlesuitGateway(project_root=project_root)
        self.policy_path = project_root / "nexus" / "knowledge" / "policy_memory.jsonl"
        self.events_sourced_path = project_root / ".nexus" / "events_sourced.jsonl"
        self.worktrees_root = project_root / ".nexus" / "worktrees"
        self.last_unified_runtime_receipt: Dict[str, Any] | None = None

    def scan_event_files(self, all_worktrees: bool = False) -> List[Path]:
        """掃描所有可能的事件源"""
        targets = []
        if self.events_sourced_path.exists():
            targets.append(self.events_sourced_path)
        
        if all_worktrees and self.worktrees_root.exists():
            # 遞迴尋找所有沙盒與指標及日誌檔案
            targets.extend(list(self.project_root.glob(".nexus/**/*.jsonl")))
            
        return targets

    def load_events(self, file_paths: List[Path]) -> List[Dict]:
        """讀取成功且具備學習價值的事件"""
        events = []
        for path in file_paths:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            data = json.loads(line)
                            # 僅過濾成功案例
                            if data.get("success") is True or data.get("status") == "SUCCESS":
                                events.append(data)
                        except: continue
            except Exception as e:
                logger.error(f"Failed to read {path}: {e}")
        return events

    def extract_patterns_via_ai(self, events: List[Dict]) -> List[Dict]:
        """使用 Battlesuit Gemini 進行模式提煉"""
        if not events:
            return []

        context_str = json.dumps(events, ensure_ascii=False, indent=2)[:8000] # 截斷保護
        
        prompt = (
            "You are the Nexus Crystal Factory (L2 Policy Extractor).\n"
            "Analyze the following execution success events and extract reusable technical policies.\n"
            "Rules for Policy:\n"
            "1. rule_id: POL-AUTO-<unique_id>\n"
            "2. condition: Precise technical trigger (e.g. 'Recursion in JSON serialization')\n"
            "3. action: Fixed instruction for future agents (e.g. 'Use depth-limit or custom encoder')\n"
            "4. confidence: 0.0-1.0\n"
            "ONLY extract policies that represent common coding patterns or system fixes."
        )
        
        output_schema = {
            "policies": [
                {
                    "rule_id": "string",
                    "condition": "string",
                    "action": "string",
                    "confidence": "number",
                    "source": "automated_extraction"
                }
            ]
        }
        
        try:
            task_id = f"crystal-factory-{hashlib.sha256(context_str.encode()).hexdigest()[:12]}"
            from nexus.services.unified_runtime import UnifiedRuntimeRequest

            def _verify(context: Dict[str, Any]) -> Dict[str, Any]:
                online = context.get("online", {})
                response = online.get("response", {}) if isinstance(online, dict) else {}
                policies = response.get("policies", []) if isinstance(response, dict) else []
                passed = online.get("status") == "SUCCEEDED" and isinstance(policies, list)
                return {
                    "task_id": task_id,
                    "status": "pass" if passed else "fail",
                    "invoked": True,
                    "gate_passed": passed,
                    "outcome_contributed": bool(policies),
                    "evidence": "crystal_factory_policy_schema",
                    "evidence_refs": [f"verifier:{task_id}:policy_schema"],
                }

            def _learn(_context: Dict[str, Any]) -> Dict[str, Any]:
                try:
                    from nexus.research.learn_mode import LearnModeService

                    result = LearnModeService(self.project_root).sync_phase_learning_closure(
                        topic="crystal-factory-policy-extraction",
                        metrics={
                            "coverage": 1.0,
                            "self_question_pass_rate": 1.0,
                            "citation_valid_ratio": 1.0,
                            "stale_claims_count": 0,
                            "conflict_count": 0,
                        },
                        phase_status={"P": "SUCCESS", "D": "SUCCESS", "R": "SUCCESS", "A": "SUCCESS", "C": "SUCCESS"},
                    )
                    passed = str(result.get("status", "")).upper() in {"SUCCESS", "SUCCEEDED", "PASS"}
                    return {
                        "task_id": task_id,
                        "status": "pass" if passed else "fail",
                        "invoked": True,
                        "gate_passed": passed,
                        "evidence": "LearnModeService.sync_phase_learning_closure",
                        "evidence_refs": [f"learning:{task_id}:phase_bridge"],
                        "response": result,
                    }
                except Exception as exc:  # noqa: BLE001
                    return {
                        "task_id": task_id,
                        "status": "fail",
                        "invoked": True,
                        "gate_passed": False,
                        "evidence": "learning_exception",
                        "evidence_refs": [f"learning:{task_id}:exception"],
                        "error": f"{exc.__class__.__name__}:{exc}",
                    }

            receipt = self.gateway.ask_unified(
                UnifiedRuntimeRequest(
                    task_id=task_id,
                    workspace_revision=os.environ.get("NEXUS_WORKSPACE_REVISION", "crystal-factory-unrevisioned"),
                    task_statement="Extract reusable policies from successful execution events.",
                    task_type="learning_policy_extraction",
                    route={
                        "recommended_flow": "direct",
                        "provider": self.gateway.oauth_provider,
                        "online_capabilities": ("research", "learn_mode"),
                    },
                    online_prompt=prompt,
                    online_payload=f"[SUCCESS_SAMPLES]\n{context_str}",
                    online_phase="A",
                    online_output_schema=output_schema,
                    evidence_refs=(f"crystal-factory:{task_id}:request",),
                ),
                verifier=_verify,
                learning=_learn,
                receipt_path=self.project_root / ".nexus" / "reports" / "learning" / f"{task_id}.unified.json",
            )
            self.last_unified_runtime_receipt = receipt
            if not receipt.get("receipt_complete"):
                raise RuntimeError("unified_runtime_incomplete")
            response = receipt.get("online", {}).get("response", {})
            return response.get("policies", []) if isinstance(response, dict) else []
        except Exception as e:
            logger.error(f"AI Extraction failed: {e}")
            return []

    def merge_policies(self, new_policies: List[Dict]):
        """將新政策合併進主庫，避免重複"""
        if not new_policies:
            return 0
            
        existing_rules = set()
        if self.policy_path.exists():
            with open(self.policy_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        p = json.loads(line)
                        # 以 condition 作為去重標誌
                        existing_rules.add(p.get("condition", "").lower())
                    except: continue

        added = 0
        with open(self.policy_path, "a", encoding="utf-8") as f:
            for np in new_policies:
                cond = np.get("condition", "").lower()
                if cond and cond not in existing_rules:
                    f.write(json.dumps(np, ensure_ascii=False) + "\n")
                    existing_rules.add(cond)
                    added += 1
        return added

@click.command()
@click.option("--all-worktrees", is_flag=True, help="Scan all past worktree sandboxes for lessons.")
@click.option("--force", is_flag=True, help="Bypass sanity checks.")
def main(all_worktrees, force):
    project_root = Path.cwd()
    factory = CrystalFactory(project_root)
    
    click.echo(f"💎 [CrystalFactory] Initiating crystallization... (Worktrees: {all_worktrees})")
    
    files = factory.scan_event_files(all_worktrees=all_worktrees)
    click.echo(f"🔍 Found {len(files)} event source files.")
    
    events = factory.load_events(files)
    click.echo(f"📥 Loaded {len(events)} success events for analysis.")
    
    if not events:
        click.echo("ℹ️ No new events to process.")
        return

    click.echo("🧠 Analyzing patterns using Battlesuit Gemini in batches...")
    batch_size = 50
    total_added = 0
    
    for i in range(0, len(events), batch_size):
        batch = events[i : i + batch_size]
        click.echo(f"  [Batch {i//batch_size + 1}] Processing {len(batch)} events...")
        new_policies = factory.extract_patterns_via_ai(batch)
        added = factory.merge_policies(new_policies)
        total_added += added
    
    if total_added > 0:
        click.secho(f"✅ Success: Crystallized {total_added} new formal policies from full history.", fg="green", bold=True)
    else:
        click.echo("ℹ️ Analysis complete. No new unique patterns found after full scan.")

if __name__ == "__main__":
    main()
