"""
P2-A: Memory Index Rebuild Utility
提供一鍵式教訓與運行數據向量化重建。
"""

import click
import json
import os
from pathlib import Path
from nexus.services.memory_indexer import rebuild_memory_index

@click.command()
@click.option("--workspace", type=click.Path(exists=True), default=".", help="Workspace root path")
@click.option("--verbose", is_flag=True, help="Show detailed ingest logs")
def main(workspace: str, verbose: bool):
    """🛡️ Nexus Memory Substrate: Rebuild LanceDB Index"""
    repo_root = Path(workspace)
    click.echo(f"🌐 [Memory:Index] Rebuilding vector substrate for {repo_root.name}...")
    
    try:
        # 執行重建
        result = rebuild_memory_index(repo_root)
        
        if result["status"] == "ok":
            click.echo(f"✅ [Memory:OK] Success! Processed {result['records_processed']} records.")
            click.echo(f"📌 [Memory:DB] {result['db_path']}")
        else:
            click.echo(f"❌ [Memory:Fail] {result.get('message', 'Unknown Error')}")
            
    except Exception as e:
        click.echo(f"❌ [Index:Fatal] Execution failed: {e}")

if __name__ == "__main__":
    main()
