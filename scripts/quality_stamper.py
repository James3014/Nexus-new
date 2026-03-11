#!/usr/bin/env python3
# /// script
# dependencies = ["pathlib", "argparse"]
# ///
"""
🛡️ Muse-Core Quality Stamper
功能: 在檔案中注入 Codex 驗證印章與時間戳記。

Agent DX Metadata:
{
    "tool_name": "quality_stamper",
    "description": "Inject verifiable quality stamps and timestamps into files.",
    "version": "2.1.0-DX",
    "author": "Antigravity",
    "standard": "Agent-DX-v2"
}
"""

import os
import re
import json
import argparse
from datetime import datetime
from pathlib import Path

def stamp_file(file_path, version_tag):
    file_path = Path(file_path).resolve()
    if not file_path.exists():
        print(f"❌ Error: File {file_path} not found.")
        return False
        
    ts = datetime.now().strftime("%Y-%m-%d")
    stamp = f"# 🛡️ Codex-Verified: {version_tag} ({ts})\n"
    
    try:
        content = file_path.read_text(encoding="utf-8")
        # Check if already stamped
        if "🛡️ Codex-Verified:" in content:
            new_content = re.sub(r"# 🛡️ Codex-Verified:.*?\n", stamp, content)
        else:
            new_content = stamp + content
            
        file_path.write_text(new_content, encoding="utf-8")
        print(f"✅ Stamped {file_path.name} with {version_tag}")
        return True
    except Exception as e:
        print(f"❌ Failed to stamp {file_path.name}: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="🛡️ Muse-Core Quality Stamper")
    parser.add_argument("file", nargs="?", help="File to stamp")
    parser.add_argument("--tag", default="Codex-Auth-Lvl13-Final", help="Version or auth tag")
    parser.add_argument("--describe", action="store_true", help="Output JSON schema for introspection")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    
    args = parser.parse_args()
    
    if args.describe:
        schema = {
            "name": "quality_stamper",
            "description": "Inject verifiable quality stamps and timestamps into files.",
            "arguments": {
                "file": "Target file path.",
                "--tag": "Custom quality tag (default: Codex-Auth-Lvl13-Final)",
                "--describe": "Flag to output this schema.",
                "--json": "Flag for structured output."
            }
        }
        print(json.dumps(schema, indent=2, ensure_ascii=False))
        return

    if not args.file:
        print("❌ Error: Missing file argument.")
        return
        
    success = stamp_file(args.file, args.tag)
    if args.json:
        print(json.dumps({"success": success, "file": args.file}))

if __name__ == "__main__":
    main()
