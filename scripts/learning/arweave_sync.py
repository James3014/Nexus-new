#!/usr/bin/env python3
"""
Nexus Learning Sync CLI - Arweave 永久記憶同步
"""

import asyncio
import click
import json
import sys
from pathlib import Path

# Add repo root to sys.path
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nexus.services.arweave_uploader import (
    upload_lessons_to_arweave,
    download_lessons_from_arweave
)
from nexus.services.federated_lessons import sync_federated_lessons
from nexus.services.continuous_learning import load_jsonl


@click.group()
@click.pass_context
def cli(ctx):
    """🛡️ Nexus Learning Sync: Arweave Eternal Memory"""
    ctx.ensure_object(dict)
    pass


@cli.command()
@click.argument("workspace_root", type=click.Path(exists=True))
@click.option("--min-confidence", type=float, default=0.7)
@click.option("--wallet", type=click.Path(exists=True), help="Path to wallet.json")
@click.option("--tag", multiple=True, help="Extra tags in Key=Value format")
def upload(workspace_root: str, min_confidence: float, wallet: str, tag):
    """上傳高品質 lessons 到 Arweave"""
    repo_root = Path(workspace_root)
    wallet_path = Path(wallet) if wallet else None
    
    extra_tags = {}
    if tag:
        try:
            extra_tags = dict(t.split("=", 1) for t in tag)
        except ValueError:
            click.secho("❌ Invalid tag format. Use Key=Value.", fg="red")
            return

    click.echo(f"🚀 [Sync:Upload] Processing workspace: {repo_root.name}")
    
    result = asyncio.run(upload_lessons_to_arweave(
        repo_root, min_confidence,
        tags=extra_tags,
        wallet_key_path=wallet_path
    ))
    
    if result["status"] == "error":
        click.secho(f"🛑 [Sync:Error] {result['reason']}", fg="red")
    elif result["status"] == "skip":
        click.secho(f"⚪ [Sync:Skip] {result['reason']}", fg="yellow")
    else:
        click.secho(f"✅ [Sync:{result['status'].capitalize()}] TX ID: {result['tx_id']}", fg="green")
        click.echo(f"   Lessons: {result['lesson_count']}")
        if "gateway_url" in result:
            click.echo(f"   URL: {result['gateway_url']}")


@cli.command()
@click.argument("tx_id")
def download(tx_id: str):
    """從 Arweave 下載 lessons"""
    click.echo(f"📥 [Sync:Download] Fetching CID: {tx_id[:8]}...")
    lessons = asyncio.run(download_lessons_from_arweave(tx_id))
    if lessons:
        click.echo(json.dumps(lessons, ensure_ascii=False, indent=2))
    else:
        click.secho("❌ No lessons found or network error.", fg="red")


@cli.command()
@click.argument("workspace_root", type=click.Path(exists=True))
def status(workspace_root: str):
    """檢查本地 Arweave CID 狀態"""
    repo_root = Path(workspace_root)
    cid_file = repo_root / ".nexus" / "learning" / "arweave_cids.jsonl"
    if not cid_file.exists():
        click.echo("⚪ No Arweave sync history.")
        return
    
    cids = load_jsonl(cid_file)
    click.secho(f"📊 [Sync:Status] {repo_root.name} - Total: {len(cids)} sync events", bold=True)
    for cid in cids[-5:]:  # 最近 5 次
        click.echo(f"🔹 {cid['timestamp_utc']}: {cid['arweave_tx'][:16]}... ({cid['lesson_count']} lessons)")


@cli.command()
@click.argument("workspace_root", type=click.Path(exists=True))
@click.option("--min-confidence", type=float, default=0.7)
@click.option("--max-age", type=int, default=30)
@click.option("--max-entries", type=int, default=500)
def federated(workspace_root, min_confidence, max_age, max_entries):
    """🛡️ [Federated] P2P + Arweave 分散式經驗同步"""
    repo_root = Path(workspace_root)
    click.echo(f"🌐 [Sync:Federated] Initializing sync for {repo_root.name}...")
    
    result = asyncio.run(sync_federated_lessons(
        repo_root, 
        min_confidence=min_confidence, 
        max_age_days=max_age,
        max_cache_entries=max_entries
    ))
    
    click.echo(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    cli()
