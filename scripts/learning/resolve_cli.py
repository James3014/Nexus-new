import click
import json
import asyncio
from pathlib import Path
from typing import Any, Dict

from nexus.services.lesson_retrieval import retrieve_with_resolution


@click.group()
def cli():
    """🛡️ Nexus Lesson Resolution Management CLI"""
    pass


@cli.command()
@click.argument("task_desc", type=str)
@click.option("--diagnosis", type=str, help="JSON diagnosis data, e.g. '{\"category\": \"LOGIC\"}'")
@click.option("--workspace", type=click.Path(exists=True), default=".")
@click.option("--federated", is_flag=True, default=True, help="Include federated shared lessons")
def audit(task_desc, diagnosis, workspace, federated):
    """🔍 Audit lesson resolution for a given task and diagnosis."""
    repo_root = Path(workspace)
    diag_data = {}
    if diagnosis:
        try:
            diag_data = json.loads(diagnosis)
        except json.JSONDecodeError:
            click.echo("❌ Error: Invalid diagnosis JSON.")
            return

    click.echo(f"🌐 [Audit:Resolve] Identifying consensus for: \"{task_desc}\"")
    
    # Execute the resolution pipeline
    result = retrieve_with_resolution(
        repo_root, 
        task_desc, 
        diagnosis=diag_data, 
        use_federated=federated
    )
    
    # Render Output
    if result["status"] == "high_consensus":
        click.echo(f"✅ [High Consensus] Score: {result['consensus_score']:.2f}")
        click.echo(f"🔹 Best Lesson: {result['best_lesson_id']}")
        click.echo(f"🔹 Category: {result['best_lesson'].get('category')}")
        click.echo(f"🔹 Fix: {result['best_lesson'].get('corrective_action')}")
        
        click.echo("\n📊 Score Breakdown:")
        for k, v in result["score_breakdown"].items():
            click.echo(f"  - {k}: {v}")
            
        if result.get("alternatives"):
            click.echo(f"\n🌀 Alternatives Count: {len(result['alternatives'])}")
    else:
        click.echo(f"⚠️ [Low Consensus] Status: {result['status']}")
        click.echo(f"🔹 Reason: {result['prompt_context']}")
        
    # Output raw JSON for machine parsing
    # click.echo("\n" + json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    cli()
