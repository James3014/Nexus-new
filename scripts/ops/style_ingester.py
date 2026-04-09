import sys, json, os
from pathlib import Path
from datetime import datetime

def ingest_style(source_url_or_css: str):
    """🛡️ v23.7 Style Ingester: Extract design soul from source."""
    project_root = Path(__file__).resolve().parents[2]
    design_path = project_root / "nexus_wiki_vault" / "99_Schema" / "DESIGN.md"
    
    print(f"🚀 [Sensory] Ingesting style from: {source_url_or_css}")
    
    # 模擬解析邏輯：根據關鍵字映射風格
    if "stripe" in source_url_or_css.lower():
        theme = "Financial Sleek, High Trust"
        primary = "#635bff"
    elif "linear" in source_url_or_css.lower():
        theme = "Cyber-Minimalist, Dark-Mode"
        primary = "#5e6ad2"
    else:
        theme = "Hardened Industrial (Default)"
        primary = "#00FF41"

    new_content = f"""# 🛡️ Nexus Design Specification (v1.1 - Ingested)
## 🌌 視覺主題: {theme}
- **Source**: {source_url_or_css}
- **Primary Color**: {primary}
- **Atmosphere**: Professional, Scalable, Hardened.

## 📐 物理佈局
- Spacing: 8px Incremental
- Border: Sharp (Standard)

## 🧠 Ingestion Metadata
- Timestamp: {datetime.now().isoformat()}
"""
    design_path.write_text(new_content)
    print(f"✅ [Sensory] DESIGN.md updated with {theme} soul.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        ingest_style(sys.argv[1])
    else:
        print("Usage: python3 style_ingester.py <url_or_css>")
