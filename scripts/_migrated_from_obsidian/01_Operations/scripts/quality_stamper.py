#!/usr/bin/env python3
import sys, os, re
from datetime import datetime

def stamp_file(file_path, commit_id):
    if not os.path.exists(file_path): return
    ext = os.path.splitext(file_path)[1].lower()
    stamp_text = f"Codex-Verified: {commit_id} ({datetime.now().strftime('%Y-%m-%d')})"
    with open(file_path, "r", encoding="utf-8") as f: content = f.read()
    if ext == ".md":
        if content.startswith("---"):
            if "codex_verified:" in content: content = re.sub(r"codex_verified:.*", f"codex_verified: \"{stamp_text}\"", content)
            else: content = content.replace("---", f"---\ncodex_verified: \"{stamp_text}\"", 1)
        else: content = f"---\ncodex_verified: \"{stamp_text}\"\n---\n\n" + content
    elif ext in [".py", ".sh", ".js"]:
        sym = "#" if ext != ".js" else "//"
        stamp = f"{sym} 🛡️ {stamp_text}"
        lines = content.split("\n")
        new_lines = []
        found = False
        for line in lines:
            if "🛡️ Codex-Verified:" in line:
                new_lines.append(stamp)
                found = True
            else: new_lines.append(line)
        if not found:
            if lines and lines[0].startswith("#!"): new_lines.insert(1, stamp)
            else: new_lines.insert(0, stamp)
        content = "\n".join(new_lines)
    with open(file_path, "w", encoding="utf-8") as f: f.write(content)
    print(f"✅ Stamped: {file_path}")

if __name__ == "__main__":
    if len(sys.argv) >= 3: stamp_file(sys.argv[1], sys.argv[2])
