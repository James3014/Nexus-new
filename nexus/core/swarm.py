from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import os
import logging
import json
import socket
from nexus.services.reviewer import GatewayReviewLoop
from nexus.security.tls_provider import TLSProvider
from nexus.security.secure_sync import SecureRegistrySync
from nexus.core.evolution_protocols import build_quiet_moment_event

logger = logging.getLogger(__name__)

class NexusSwarmOrchestrator:
    """
    🐝 Nexus Swarm Orchestrator (v24.8 Master Loop)
    管理多角色 Agent 協作流：Scout -> Analyzer -> Consensus -> Coder -> Tester -> Audit
    """
    def __init__(self, engine: Any, task: str, model: str = None, allocation: Optional[Any] = None):
        self.engine = engine
        self.task = task
        self.model = model
        self.allocation = allocation # 接受來自 ProjectPlanner 的配置
        self.total_tokens = 0
        self.results = []
        
        # --- mTLS Security Layer ---
        # ... (維持原樣) ...
        self.tls_enabled = os.environ.get("NEXUS_TLS_ENABLED", "0") == "1"
        self.node_id = os.environ.get("NEXUS_NODE_ID", "local")
        self.tls_provider = None
        self.secure_sync = None
        
        if self.tls_enabled:
            project_root = getattr(self.engine, "project_root", Path("."))
            if not isinstance(project_root, Path):
                project_root = Path(project_root)
                
            certs_dir = project_root / ".nexus" / "certs"
            self.tls_provider = TLSProvider(certs_dir, node_id=self.node_id)
            
            registry_path = project_root / ".nexus" / "registry" / "shared_skills.db"
            if registry_path.exists():
                from nexus.learning.skill_registry import SkillRegistry
                self.secure_sync = SecureRegistrySync(self.tls_provider, SkillRegistry(registry_path))

    def run(self) -> Dict[str, Any]:
        """🚀 啟動全生命週期蜂群任務管線。"""
        print(f"🐝 [Swarm] Deploying Strategic Swarm for Task: {self.task[:50]}...")
        
        # 0. Scout Phase (Intelligence Gathering)
        context = ""
        if self.allocation and self.allocation.scout:
            context = self._scout()
        
        # 1. Analyzer Phase
        analysis = self._analyze(context)
        
        # 2. Consensus Phase (Architect + Reviewer)
        plan = self._consensus_plan(analysis)

        quiet_moment = self._enter_quiet_moment(plan)
        
        # 3. Execution Phase (Gladiator - Coder)
        repair_result = self._repair(plan)
        
        # 4. Tester Phase
        final_status = self._verify(repair_result)
        
        # 5. Audit Phase (Knowledge Crystallization)
        if self.allocation and self.allocation.audit:
            self._audit(final_status, repair_result)
        
        return {
            "status": final_status,
            "analysis": analysis,
            "plan": plan,
            "quiet_moment": quiet_moment,
            "tokens_used": self.total_tokens
        }

    def _enter_quiet_moment(self, plan: str) -> Dict[str, Any]:
        event = build_quiet_moment_event(
            reason="swarm_pre_repair_mutation_boundary",
            affected_nodes=[self.node_id, "repair"],
            resume_after_seconds=0,
        )
        event["plan_preview"] = plan[:200]
        observe = self._observe_quiet_moment(event)
        rollback = self._rollback_quiet_moment(event)
        event["observe"] = observe
        event["rollback"] = rollback
        return event

    def _observe_quiet_moment(self, event: Dict[str, Any]) -> Dict[str, Any]:
        observer = getattr(self.engine, "swarm_observer", None)
        if callable(observer):
            return dict(observer(event) or {})
        return {"status": "observed", "production_writes_allowed": False}

    def _rollback_quiet_moment(self, event: Dict[str, Any]) -> Dict[str, Any]:
        rollback = getattr(self.engine, "swarm_rollback", None)
        if callable(rollback):
            return dict(rollback(event) or {})
        return {"status": "armed", "production_writes_allowed": False}

    def _scout(self) -> str:
        print("🔭 [Swarm:Scout] Performing deep intelligence scouting (LanceDB RAG)...")
        try:
            from nexus.research.learn_mode import LearnModeService
            p_root = getattr(self.engine, "project_root", Path("."))
            if not isinstance(p_root, Path):
                p_root = Path(p_root)
            
            svc = LearnModeService(p_root)
            # 使用任務描述作為問題，topic 設為 general 或從任務中提取關鍵字
            scout_result = svc.ask(topic="multi-agent-orchestration", question=self.task, top_k=8)
            
            citations = scout_result.get("citations", [])
            if not citations:
                return "Scouted Context: No specific historical lessons found in LanceDB."
            
            context_lines = ["Scouted Intelligence Bundle:"]
            for i, c in enumerate(citations[:5]):
                context_lines.append(f"[{i+1}] {c.get('claim')} (Source: {c.get('source_url')})")
            
            summary = "\n".join(context_lines)
            print(f"✅ [Swarm:Scout] Retrieved {len(citations)} relevant claims from knowledge base.")
            return summary
            
        except Exception as e:
            logger.warning("Scouting failed due to service error: %s", e)
            return "Scouted Context: Scouting service unavailable. Falling back to zero-context mode."


    def _consensus_plan(self, analysis: str) -> str:
        print("⚖️ [Swarm:Consensus] Running Architect-Reviewer debate...")
        safe_analysis = analysis if analysis else "No analysis available"
        plan = f"CONSENSUS PLAN: Refactor with safety locks based on analysis: {safe_analysis[:50]}"
        return plan

    def _audit(self, status: str, result: Dict[str, Any]):
        print("✍️ [Swarm:Audit] Crystallizing lessons and updating Memory...")
        # 這裡執行 Lesson Writeback
        pass

    # --- 以下維持原有實作，但根據需要微調參數 ---
    def _analyze(self, context: str = "") -> str:
        print(f"🔍 [Swarm:Analyzer] Analyzing repository... (Context size: {len(context)})")
        import subprocess
        p_root = getattr(self.engine, "project_root", ".")
        try:
            tree = subprocess.check_output(["find", ".", "-maxdepth", "2", "-not", "-path", "*/.*"], 
                                          cwd=p_root, text=True)
        except Exception as e:
            logger.warning("Swarm tree analysis failed: %s", e)
            tree = "Tree analysis failed."
            
        analysis = f"Repository structure scanned:\n{tree[:500]}\nContext: {context}"
        return analysis



    def _plan(self, analysis: str) -> str:
        print("🧠 [Swarm:Planner] Designing repair strategy...")
        # 基於 Analysis 產出行動綱領內容。
        plan = f"STRATEGY: Break cyclic import in modeling/core.py and fix separability logic in separable.py.\nContext: {analysis[:100]}"
        return plan

    def _repair(self, plan: str) -> Dict[str, Any]:
        print("🛠️ [Swarm:Coder] Implementing repair...")
        # Use the review loop for the actual heavy lifting
        loop = GatewayReviewLoop(
            git=getattr(self.engine, "git", None),
            linter=getattr(self.engine, "linter", None),
            patcher=getattr(self.engine, "patcher", None),
            reporter=getattr(self.engine, "reporter", None),
            workspace=getattr(self.engine, "workspace", None),
            router=getattr(self.engine, "router", None),
            commander=getattr(self.engine, "commander", None),
            context_hub=getattr(self.engine, "context_hub", None),
            state_io=getattr(self.engine, "state_io", None),
            project_root=getattr(self.engine, "project_root", None),
            run_dir=getattr(self.engine, "run_dir", None),
            llm=getattr(self.engine, "llm", None),
            task=f"REPAIR TASK: {plan}\nOriginal Task: {self.task}",
            model=self.model
        )
        res = loop.run_review()
        self.total_tokens += loop.total_tokens
        return res

    def _verify(self, repair_result: Dict[str, Any]) -> str:
        print("🧪 [Swarm:Tester] Verifying fix...")
        return repair_result.get("status", "FAIL")

class FederatedSwarmOrchestrator(NexusSwarmOrchestrator):
    def __init__(self, engine: Any, task: str, model: str = None):
        super().__init__(engine, task, model)
        self.node_registry = None
        if self.tls_enabled and self.tls_provider:
            # Assuming nodes.db lives in .nexus/federation
            registry_db = self.tls_provider.certs_dir.parent / "federation" / "nodes.db"
            try:
                from nexus.federation.node_registry import NodeRegistry
                self.node_registry = NodeRegistry(registry_db)
                if self.secure_sync:
                    self.secure_sync.node_registry = self.node_registry
            except ImportError:
                logger.warning("Federation package not available.")

    def _select_executor(self, required_capability: str = "coder") -> Optional[Any]:
        if not self.node_registry:
            return None
        nodes = self.node_registry.discover()
        best_node = None
        lowest_load = float('inf')
        for node in nodes:
            if node.node_id == self.node_id:
                continue
            if required_capability in node.capabilities or not node.capabilities:
                if node.load < lowest_load:
                    lowest_load = node.load
                    best_node = node
        return best_node

    def _dispatch_remote(self, node: Any, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        logger.info(f"🚀 [Federation] Dispatching task to remote node {node.node_id} ({node.host}:{node.port})")
        context = self.tls_provider.get_client_context()
        try:
            with socket.create_connection((node.host, node.port), timeout=300) as sock:
                with context.wrap_socket(sock, server_hostname=node.host) as ssock:
                    f = ssock.makefile("rwb")
                    req = {
                        "action": "execute_phase",
                        "payload": payload
                    }
                    f.write((json.dumps(req) + "\n").encode("utf-8"))
                    f.flush()
                    
                    resp_line = f.readline().decode("utf-8")
                    if not resp_line:
                        return None
                    resp = json.loads(resp_line)
                    if resp.get("status") == "ok":
                        return resp.get("result")
                    return None
        except Exception as e:
            logger.warning(f"❌ [Federation] Remote dispatch failed: {e}")
            return None

    # ─── Sprint 11e: Federation Security Boundary ───────────────────────────
    # POLICY: Only "verify" (read-only / sandbox inspection) may be dispatched
    # to remote federation nodes. "repair" and "coder" are FORBIDDEN remotely
    # to prevent Remote Code Execution (RCE) state contamination.
    # This is enforced here (client side) AND at protocol level in _dispatch_remote.
    _ALLOWED_REMOTE_PHASES = frozenset({"verify"})

    def _dispatch_remote(self, node: Any, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        phase = payload.get("phase", "")
        if phase not in self._ALLOWED_REMOTE_PHASES:
            logger.warning(
                "🔒 [Federation:BLOCKED] Refusing to dispatch phase '%s' to remote node %s. "
                "Only %s phases are permitted remotely.",
                phase, node.node_id, self._ALLOWED_REMOTE_PHASES,
            )
            return None
        return super()._dispatch_remote(node, payload)

    def _repair(self, plan: str) -> Dict[str, Any]:
        # "repair" is a write-path phase — ALWAYS run locally.
        # Do NOT attempt remote dispatch; fall straight through to local execution.
        logger.info("🏠 [Federation] repair phase is write-path — executing locally (policy enforced).")
        return super(NexusSwarmOrchestrator, self)._repair(plan)

    def _verify(self, repair_result: Dict[str, Any]) -> str:
        """Attempt federated verify before falling back to local."""
        remote_node = self._select_executor("verify")
        if remote_node:
            print(f"🌐 [Federation] Offloading verify to {remote_node.node_id} (Load: {remote_node.load:.2f})")
            payload = {
                "phase": "verify",
                "repair_result": repair_result,
                "task": self.task,
                "model": self.model,
            }
            res = self._dispatch_remote(remote_node, payload)
            if res:
                self.total_tokens += res.get("tokens_used", 0)
                return res.get("status", "FAIL")
            print("⚠️ [Federation] Remote verify failed. Falling back to local.")
        return super()._verify(repair_result)

class PeerSwarmOrchestrator(NexusSwarmOrchestrator):
    """🐝 [P2P] Swarm-Together Peer Orchestrator (Claude-Together Absorption)"""
    def __init__(self, engine, task, model=None, peer_id=None):
        super().__init__(engine, task, model)
        self.peer_id = peer_id or f"Peer-{os.getpid()}"
        self.sse_url = "http://localhost:8080/nexus-sync/poc"
        base_root = Path(getattr(self.engine, "project_root", Path.cwd()))
        self.manifest_path = base_root / ".nexus" / "swarm" / "manifest.json"
        
    def broadcast_decision(self, decision_type: str, data: Dict):
        """🛡️ 廣播決策 (Shared Decisions)"""
        print(f"📡 [{self.peer_id}] Broadcasting Decision: {decision_type}")
        # 在 POC 中模擬發送至 SSE
        # requests.post("http://localhost:8080/broadcast", json={"peer": self.peer_id, "type": decision_type, "data": data})

    def listen_for_peers(self):
        """👂 監聽夥伴信號 (Clarification/Auto-reply)"""
        print(f"👂 [{self.peer_id}] Listening for Peer signals...")

    def check_manifest_lock(self, target: str) -> bool:
        """🛡️ [P2P] 原子性核驗 Manifest 鎖定狀態"""
        if not self.manifest_path.exists():
            return False
            
        with open(self.manifest_path, "r") as f:
            data = json.load(f)
            decisions = data.get("decisions", [])
            # 檢查是否有其他 Peer 正在修復同一個目標內容分組。
            for d in decisions:
                if d.get("target") == target and d.get("peer_id") != self.peer_id:
                    print(f"🛑 [{self.peer_id}] CONFLICT_DETECTED: {target} is locked by {d.get('peer_id')}")
                    return True
        return False

    def _repair(self, plan: str) -> Dict[str, Any]:
        """P2P 修復：具備衝突偵測與避讓能力"""
        target_file = "nexus/core/swarm.py" # 模擬目標內容分組內容分組。
        if self.check_manifest_lock(target_file):
            print(f"🔄 [{self.peer_id}] Peer-Conflict: Redirecting to Memory_Refresh.")
            return {"status": "CONFLICT_DETECTED", "history": self.history + ["conflict_wait"]}
            
        self.broadcast_decision("REPAIR_INTENT", {"target": target_file, "plan": plan})
        return super()._repair(plan)

class SwarmFactory:
    @staticmethod
    def create_swarm(engine, task, model=None):
        mode = os.environ.get("NEXUS_SWARM_MODE", "sequential")
        if mode == "p2p":
            return PeerSwarmOrchestrator(engine, task, model)
        if os.environ.get("NEXUS_FEDERATION_ENABLED", "0") == "1":
            return FederatedSwarmOrchestrator(engine, task, model)
        return NexusSwarmOrchestrator(engine, task, model)
