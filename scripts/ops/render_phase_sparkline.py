#!/usr/bin/env python3
import json
import argparse
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

def render_sparkline(values):
    # ASCII Sparkline: [ ▂▃▄▅▆▇█]
    chars = " ▂▃▄▅▆▇█"
    if not values:
        return ""
    val_list = [float(v) for v in values]
    mn, mx = min(val_list), max(val_list)
    if mn == mx:
        return chars[len(chars)//2] * len(val_list)
    
    out = []
    for v in val_list:
        idx = int((v - mn) / (mx - mn) * (len(chars) - 1))
        out.append(chars[idx])
    return "".join(out)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--window", type=int, default=10)
    args = parser.parse_args()
    
    project_root = Path.cwd()
    data_file = project_root / ".nexus" / "learning_velocity.json"
    if not data_file.exists():
        print(f"❌ {data_file} not found.")
        sys.exit(1)
        
    data = json.loads(data_file.read_text(encoding="utf-8"))
    history = data.get("history", [])
    if not history:
        print("❌ No history to render.")
        sys.exit(0) # Not a failure, but nothing to do
        
    sparkline = render_sparkline(history[-args.window:])
    
    # Update docs/EXEC_LIVE_STATUS.md
    status_file = project_root / "docs" / "EXEC_LIVE_STATUS.md"
    if status_file.exists():
        content = status_file.read_text(encoding="utf-8")
        trend_header = "### Learning Velocity Trend"
        new_entry = f"{trend_header}\n\n`[{sparkline}]` (v={data.get('current',0.0):+.2f})\n"
        
        if trend_header in content:
           # Update existing: match from header until the next header or end of file
           import re
           # Improved regex: match header, optional spaces, and the sparkline line.
           # We use a pattern that matches the specific line format we expect.
           pattern = r"### Learning Velocity Trend\s+`\[.*?\]` \(v=.*?\)\n?"
           if re.search(pattern, content):
               content = re.sub(pattern, new_entry, content)
           else:
               # Fallback if format changed: match until next header or end
               content = re.sub(rf"{trend_header}\s+.*?(?=\n#|$)", new_entry, content, flags=re.DOTALL)
        else:
           # Append
           content += f"\n\n{new_entry}"
        
        status_file.write_text(content, encoding="utf-8")
        print(f"✅ Rendered sparkline [{sparkline}] to docs")

if __name__ == "__main__":
    main()
