import os
import subprocess
import json
import logging
from typing import Any, Dict, List, Optional
from pathlib import Path

logger = logging.getLogger("ContextAdapter")

class ContextAdapter:
    """
    🧬 Nexus Context Transport Adapter (v24.4)
    Provides a switchable context provider layer with lean-ctx integration.
    """
    def __init__(self, context_hub: Any):
        self.legacy_provider = context_hub
        self.provider_mode = os.environ.get("NEXUS_CONTEXT_PROVIDER", "legacy").lower()

    def __getattr__(self, name):
        """Forward unknown attributes to the legacy provider (ContextHub)."""
        return getattr(self.legacy_provider, name)

    def assemble_context(self, task_id: str, layers: List[int], budget: int = 4000, bayesian_params: Optional[Dict[str, Any]] = None) -> str:
        """🚀 Multi-provider context assembly with safe fallback."""
        if self.provider_mode == "leanctx":
            try:
                return self._call_leanctx("assemble_context", task_id=task_id, layers=layers, budget=budget)
            except Exception as e:
                logger.warning(f"LeanCtx failed: {e}. Falling back to legacy provider.")
        
        return self.legacy_provider.assemble_context(task_id, layers, budget, bayesian_params)

    def assemble_diag_pack(self, violations: List[Dict], summary: str) -> Dict[str, Any]:
        """🧬 Diagnostic pack with lean-ctx enrichment."""
        if self.provider_mode == "leanctx":
            try:
                lean_pack = self._call_leanctx_json("assemble_diag_pack", violations=violations, summary=summary)
                if lean_pack:
                    return lean_pack
            except Exception as e:
                logger.warning(f"LeanCtx diag_pack failed: {e}. Falling back.")
        
        return self.legacy_provider.assemble_diag_pack(violations, summary)

    def assemble_repair_pack(self, diagnosis: Any, reflections: List[Dict], research: Optional[Any] = None) -> Dict[str, Any]:
        """🧬 Repair pack with optional lean-ctx transport."""
        if self.provider_mode == "leanctx":
            try:
                # We only send essential data to lean-ctx to keep it non-authoritative for memory
                lean_pack = self._call_leanctx_json("assemble_repair_pack", 
                                                   summary=diagnosis.summary, 
                                                   hotspots=diagnosis.hotspots)
                if lean_pack:
                    # Merge with legacy for authoritative memory/router data
                    legacy_pack = self.legacy_provider.assemble_repair_pack(diagnosis, reflections, research)
                    legacy_pack.update(lean_pack)
                    return legacy_pack
            except Exception as e:
                logger.warning(f"LeanCtx repair_pack failed: {e}. Falling back.")

        return self.legacy_provider.assemble_repair_pack(diagnosis, reflections, research)

    def _call_leanctx(self, command: str, **kwargs) -> str:
        """Call lean-ctx subprocess and return stdout as string."""
        cmd = ["lean-ctx", command]
        for k, v in kwargs.items():
            # Filter out None values and ensure JSON strings for complex types
            val = v
            if val is None: continue
            if isinstance(val, (dict, list)):
                val = json.dumps(val)
            else:
                val = str(val)
            cmd.extend([f"--{k}", val])
        
        try:
            # P3: Real subprocess call with timeout and error handling
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return result.stdout.strip()
            raise RuntimeError(f"lean-ctx exited with {result.returncode}: {result.stderr}")
        except FileNotFoundError:
            raise RuntimeError("lean-ctx binary not found in PATH")
        except subprocess.TimeoutExpired:
            raise RuntimeError("lean-ctx call timed out after 5s")

    def _call_leanctx_json(self, command: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Call lean-ctx subprocess and parse output as JSON."""
        try:
            output = self._call_leanctx(command, **kwargs)
            return json.loads(output)
        except Exception as e:
            logger.error(f"Failed to parse lean-ctx output as JSON: {e}")
            return None
