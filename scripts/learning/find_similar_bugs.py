"""
🛡️ Nexus Bug Lookup CLI: 利用 Traceback 搜尋相似成功修復 (P2-C)
"""

import click
import json
from pathlib import Path
from nexus.services.bug_fingerprint import get_repair_recommendations

@click.command()
@click.argument("workspace_root")
@click.argument("traceback")
@click.option("--top-k", default=5, help="Number of similar bugs to find")
def main(workspace_root: str, traceback: str, top_k: int):
    repo_root = Path(workspace_root)
    if not repo_root.exists():
        click.echo(json.dumps({"status": "error", "message": f"Path not found: {workspace_root}"}, indent=2))
        return

    diagnosis = {"traceback_snippet": traceback}
    result = get_repair_recommendations(repo_root, diagnosis)
    
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
