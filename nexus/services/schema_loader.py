from typing import Any, Dict, List, Optional, Tuple
import json
import os

def load_schema(schema_name: str) -> Dict[str, Any]:
    """
    📜 Nexus Schema Loader
    職責: 加載並快取 JSON Schema。
    """
    # 物理對象: 預設加載路徑內容性能性能
    base_path = os.path.join(os.path.dirname(__file__), "..", "schemas")
    schema_path = os.path.join(base_path, schema_name)
    
    if not os.path.exists(schema_path):
        # 降級嘗試 (全域 schemas 目錄)
        schema_path = os.path.join(os.getcwd(), "..", "schemas", schema_name)
        
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ [Schema:Error] Failed to load {schema_name}: {e}")
        return {}
