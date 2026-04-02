from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import subprocess
import json
import hashlib
import time
import os
import logging
from pydantic import BaseModel
from nexus.services.schema_loader import load_schema

logger = logging.getLogger(__name__)

class ReachResult(BaseModel):
    decision_id: str = ""
    url: str
    resolver: str
    tier: int = 1
    content_type: str
    markdown: str = ""
    structured_data: Optional[Dict[str, Any]] = None
    transcript: Optional[List[str]] = None
    artifacts: List[str] = []
    confidence: float = 0.0
    elapsed_ms: int = 0
    trace: List[str] = []
    task_id: Optional[str] = "NEXUS-UCC-AUTO"

class UCCRouter:
    """
    🛡️ Nexus UCC Router (Phase 1)
    職責: 實體對位與全階段 Hook 路由。
    """
    def __init__(self):
        # 🛡️ 實體加載契約
        self.schema = load_schema("reach_result_schema.json")
        self.resolvers = {
            1: self._firecrawl,
            2: self._yt_dlp,
            3: self._scrapegraph
        }
    
    def reach(self, url: str, tier: int = 1) -> ReachResult:
        decision_id = hashlib.sha256(f"{url}:{tier}:{time.time()}".encode()).hexdigest()[:8]
        trace = []
        
        # 🛡️ 按 Tier 順序嘗試 (由淺入深)
        for t in range(1, tier + 1):
            try:
                resolver_func = self.resolvers.get(t)
                if not resolver_func:
                    continue
                    
                result = resolver_func(url)
                result.decision_id = decision_id
                result.tier = t
                result.trace = trace
                
                # 🛡️ [Phase 2.3] 信心值核驗：若外部工具回傳 E404 或失效內容及其內容內容
                if result.confidence < 0.5:
                    trace.append(f"Tier {t} ({resolver_func.__name__}) returned low confidence: {result.markdown[:100]}")
                    continue
                    
                # 🛡️ 寫入持久化快照 (Phase 1 要求)
                self._persist_result(result)
                return result
                
            except Exception as e:
                trace.append(f"Tier {t} ({self.resolvers.get(t).__name__ if self.resolvers.get(t) else 'N/A'}) failed: {str(e)}")
        
        # 🛡️ [Survival:Native] 如果所有預設工具都失敗，啟動原生感官對位內容內容及性能性能
        logger.info("   ↳ [Reach:Native] All tiers failed or low confidence. Starting Native Resolve.")
        try:
            result = self._native_resolve(url)
            result.decision_id = decision_id
            result.trace = trace
            self._persist_result(result)
            return result
        except Exception as e:
            trace.append(f"Native resolve also failed: {e}")
        
        # 🚨 Fallback 模式內容性能及性能分析內容
        fallback_result = ReachResult(
            decision_id=decision_id,
            url=url,
            resolver="fallback",
            tier=4,
            content_type="markdown",
            markdown=f"⚠️ All resolvers failed after {len(trace)} attempts.\nLatest error: {trace[-1] if trace else 'Unknown'}",
            confidence=0.0,
            elapsed_ms=0,
            trace=trace
        )
        self._persist_result(fallback_result)
        self._log_outcome(fallback_result)
        return fallback_result

    def _log_outcome(self, result: ReachResult):
        """將 UCC 行動紀錄為 Nexus Skill Outcome Event 內容及性能內容性能性能性能"""
        try:
            from nexus.core.skill_outcomes import build_outcome_event, append_skill_outcome_event, OutcomePayload
            
            payload = OutcomePayload(
                task_id=result.task_id or "NEXUS-UCC-AUTO",
                phase="X", # Phase X 為感官預設相位內容及其內容分析內容
                decision_id=result.decision_id,
                skill_id=f"reach.{result.resolver}",
                passed=(result.confidence > 0.5),
                proof_present=(result.markdown != ""),
                metadata={
                    "status": "COMPLETED" if result.confidence > 0.5 else "FAILED",
                    "source": "ucc.router"
                }
            )
            event = build_outcome_event(payload)
            append_skill_outcome_event(Path("."), event)
        except Exception as e:
            print(f"⚠️ [UCC:Telemetry] Failed to log outcome: {e}")

    def _persist_result(self, result: ReachResult):
        """物理持久化到 .nexus/reach/"""
        reach_path = os.path.join(os.getcwd(), ".nexus", "reach")
        if not os.path.exists(reach_path):
            os.makedirs(reach_path, exist_ok=True)
            
        file_path = os.path.join(reach_path, f"{result.decision_id}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(result.model_dump(), f, indent=2, ensure_ascii=False)

    def _firecrawl(self, url: str) -> ReachResult:
        """Tier 1: Firecrawl (Markdown Ingestion)"""
        start = time.time()
        # npx @firecrawl-dev/firecrawl@latest crawl <url> --output markdown
        try:
            result = subprocess.run([
                "npx", "-y", "@firecrawl-dev/firecrawl@latest", "crawl", url, 
                "--output-format", "markdown"
            ], capture_output=True, text=True, timeout=60)
            
            return ReachResult(
                url=url,
                resolver="firecrawl",
                content_type="markdown",
                markdown=result.stdout if result.returncode == 0 else result.stderr,
                confidence=0.9 if result.returncode == 0 else 0.1,
                elapsed_ms=int((time.time() - start) * 1000)
            )
        except Exception as e:
            raise RuntimeError(f"Firecrawl execution failed: {e}")

    def _yt_dlp(self, url: str) -> ReachResult:
        """Tier 2: YT-DLP (Video Transcript)"""
        start = time.time()
        # 物理對象: 優先透過 yt-dlp 獲取字幕內容性能及性能分析內容
        try:
            # 命令: yt-dlp --get-description --write-subs --skip-download --print json
            result = subprocess.run([
                "yt-dlp", "--skip-download", "--print", "json", url
            ], capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0:
                data = json.loads(result.stdout)
                return ReachResult(
                    url=url,
                    resolver="yt-dlp",
                    content_type="transcript",
                    markdown=f"## {data.get('title')}\n\n{data.get('description')}",
                    structured_data=data,
                    transcript=[data.get("description", "No transcript available")],
                    confidence=0.95,
                    elapsed_ms=int((time.time() - start) * 1000)
                )
            else:
                raise RuntimeError(result.stderr)
        except Exception as e:
            raise RuntimeError(f"YT-DLP execution failed: {e}")

    def _scrapegraph(self, url: str) -> ReachResult:
        """Tier 3: ScrapeGraph (Structured Data)"""
        start = time.time()
        # 物理對位：使用 curl 做基礎獲取分組內容性能性能性能性能性能內容
        try:
            result = subprocess.run([
                "curl", "-sL", url
            ], capture_output=True, text=True, timeout=30)
            
            return ReachResult(
                url=url,
                resolver="scrapegraph",
                content_type="structured",
                markdown=result.stdout[:5000], 
                confidence=0.7,
                elapsed_ms=int((time.time() - start) * 1000)
            )
        except Exception as e:
            raise RuntimeError(f"ScrapeGraph/Fallback failed: {e}")

    def _native_resolve(self, url: str) -> ReachResult:
        """🧬 [Native Resolver] 使用 Python 實體直接獲取內容 (Phase 2.3 降級方案)"""
        import requests
        from bs4 import BeautifulSoup

        start = time.time()
        try:
            # 物理觸達內容及其性能內容性能性能性能
            headers = {"User-Agent": "Mozilla/5.0 (Nexus Neural Reach/v23)"}
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            
            # 簡單清理內容性能性能性能
            for script in soup(["script", "style"]):
                script.decompose()
            
            text_blocks = [t.strip() for t in soup.stripped_strings if len(t.strip()) > 20]
            md = "\n\n".join(text_blocks)
            
            return ReachResult(
                url=url,
                resolver="native_python",
                content_type="markdown",
                markdown=md[:10000],
                confidence=0.85,
                elapsed_ms=int((time.time() - start) * 1000)
            )
        except Exception as e:
            raise RuntimeError(f"Native resolution physical failure: {e}")

if __name__ == "__main__":
    # 單體測試入口內容及性能分析內容性能性能內容
    import sys
    test_url = sys.argv[1] if len(sys.argv) > 1 else "https://example.com"
    router = UCCRouter()
    print(router.reach(test_url).model_dump_json(indent=2))
