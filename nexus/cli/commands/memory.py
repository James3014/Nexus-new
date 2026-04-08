import click
import json
import time
from pathlib import Path
from nexus.cli.utils import _get_service, REPO_ROOT

@click.group(name="memory")
def memory_group():
    """🛡️ 向量記憶體管理 (LanceDB)"""
    pass

@memory_group.command("rebuild")
@click.option("--workspace", default=".", help="Workspace root")
@click.option("--incremental", is_flag=True, help="Incremental upsert instead of full rebuild (v0.1: Full Only)")
def memory_rebuild(workspace: str, incremental: bool):
    """一鍵重建 LanceDB 向量索引 (P2-A/B)"""
    from nexus.services.memory_indexer import rebuild_memory_index
    result = rebuild_memory_index(Path(workspace))
    click.echo(json.dumps(result, indent=2))

@memory_group.command("stats")
@click.option("--workspace", default=".", help="Workspace root")
def memory_stats(workspace: str):
    """查看向量索引統計數據 (P2-B)"""
    from nexus.services.memory_indexer import connect_memory_db, TABLE_NAME
    import pandas as pd
    try:
        db = connect_memory_db(Path(workspace))
        table = db.open_table(TABLE_NAME)
        df = table.to_pandas()
        stats = df.groupby("record_type").size().to_dict()
        click.echo(json.dumps({
            "status": "ok", "total_records": len(df), "distribution": stats
        }, indent=2))
    except Exception as e:
        click.echo(json.dumps({"status": "error", "message": str(e)}, indent=2))

@memory_group.command("search")
@click.argument("query")
@click.option("--mode", type=click.Choice(["palace", "semantic", "dual"]), default="dual")
@click.option("--tenant", "tenant_id", default="default")
@click.option("--threshold", "min_palace_hit", default=0.8, type=float)
def memory_search(query: str, mode: str, tenant_id: str, min_palace_hit: float):
    """🚀 [Phase 32] 雙模語義/階層檢索入口"""
    from nexus.core.router import SkillsRouter
    router = SkillsRouter(str(REPO_ROOT))
    context = {"mode": mode, "tenant_id": tenant_id, "min_palace_hit": min_palace_hit, "active_domain": "undeclared"}
    t0 = time.perf_counter()
    result = router.memory_route(query, context)
    result["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))
