from typing import Any, Dict, List, Optional, Tuple
import subprocess
import logging
import json

logger = logging.getLogger(__name__)

class TruthValidator:
    """
    ⚖️ Nexus 真值核驗器 (Phase G.0)
    強制物理應用層驗收，防止 Agent 透過「偽造進程存活」來達成虛假勝利。
    """
    
    @staticmethod
    def ping_endpoint(url: str, expected_status: int = 200) -> bool:
        """🎯 物理應用層 Ping (curl 真值)"""
        try:
            # -s (silent), -o /dev/null (no output), -w (output status)
            cmd = ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url]
            res = subprocess.run(cmd, capture_output=True, text=True)
            status = int(res.stdout.strip())
            logger.info(f"🧬 [Truth:Ping] {url} -> {status}")
            return status == expected_status
        except Exception:
            return False

    @staticmethod
    def validate_api_response(url: str, schema: Dict[str, Any]) -> bool:
        """🎯 驗收 API 回應內容真值 (JSON Schema 核對)"""
        try:
            res = subprocess.run(["curl", "-s", url], capture_output=True, text=True)
            data = json.loads(res.stdout)
            
            # 簡易 Schema 欄位比對 (v22 Spec 要求)
            for key, expected_type in schema.items():
                if key not in data:
                    logger.error(f"❌ [Truth:Schema] Missing key: {key}")
                    return False
                if not isinstance(data[key], expected_type):
                    logger.error(f"❌ [Truth:Schema] Type mismatch for {key}: {type(data[key])} != {expected_type}")
                    return False
            
            logger.info(f"✅ [Truth:Schema] URL {url} passed structure check.")
            return True
        except Exception as e:
            logger.error(f"❌ [Truth:Schema] Validation failed: {e}")
            return False

    @staticmethod
    def ping_database(db_type: str, dsn: str) -> bool:
        """🎯 物理資料庫通路核驗 (DB Ping)"""
        try:
            if db_type == "postgres":
                # 使用 pg_isready 核驗
                cmd = ["pg_isready", "-d", dsn]
                res = subprocess.run(cmd, capture_output=True, text=True)
                return res.returncode == 0
            elif db_type == "sqlite":
                # 核驗文件路徑是否存在
                return os.path.exists(dsn)
            return False
        except Exception as e:
            logger.error(f"❌ [Truth:DB] {db_type} ping failed: {e}")
            return False

if __name__ == "__main__":
    # 測試執行
    v = TruthValidator()
    print(f"Ping localhost:8000: {v.ping_endpoint('http://localhost:8000')}")
