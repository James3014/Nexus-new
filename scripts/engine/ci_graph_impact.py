#!/usr/bin/env python3
import os
import json
import argparse
from pathlib import Path
from nx_impact import ImpactAnalyzer

class CIReportGenerator:
    def __init__(self, nodes_path, edges_path, template_path):
        self.analyzer = ImpactAnalyzer(nodes_path, edges_path)
        with open(template_path, "r", encoding="utf-8") as f:
            self.template = f.read()

    def generate_report(self, changed_files):
        impacted_nodes = []
        source_nodes = []
        
        # 1. Identity source nodes from changed files
        for cf in changed_files:
            for node_id, node in self.analyzer.nodes.items():
                if node["path"] == cf:
                    source_nodes.append(node)
                    impacted_nodes.extend(self.analyzer.find_impact(node["name"]))

        # 2. Build Mermaid
        mermaid_nodes = []
        mermaid_edges = []
        high_risk_sites = []
        
        for sn in source_nodes:
            mermaid_nodes.append(f'{sn["id"]}["{sn["name"]}"]:::source')
        
        for in_node in impacted_nodes:
            # Find the edge that led to this node
            for edge_to, edge_froms in self.analyzer.adj.items():
                if in_node["id"] in edge_froms:
                    # In our analyzer, adj[to] = [froms] where to is Schema, from is Actor
                    # So impact flows Schema -> Actor
                    mermaid_edges.append(f'{edge_to} --> {in_node["id"]}')

            # Identify High Risk (Fragility Check)
            if in_node["type"] == "UI_COMPONENT":
                high_risk_sites.append(in_node)

        # 3. Build Alerts
        fragility_alerts = ""
        for hr in high_risk_sites:
            fragility_alerts += f"> [!WARNING]\n> **Fragile Binding**: `{hr['name']}` directly consumes a backend schema. Any non-compatible change will break the UI.\n\n"

        # 4. Impact Table
        impact_table = ""
        for node in impacted_nodes:
            action = "Review Usage" if node["type"] != "UI_COMPONENT" else "**URGENT: Verify Binding**"
            impact_table += f"| {node['type']} | {node['name']} | `{node['path']}` | {action} |\n"

        # 5. Highlight high risk in Mermaid
        highlights = "\n    ".join([f"class {hr['id']} highRisk;" for hr in high_risk_sites])

        # Render Template
        report = self.template.format(
            pr_files_list="\n".join([f"- `{f}`" for f in changed_files]),
            mermaid_nodes="\n    ".join(list(set(mermaid_nodes))),
            mermaid_edges="\n    ".join(list(set(mermaid_edges))),
            high_risk_highlights=highlights,
            fragility_alerts=fragility_alerts if fragility_alerts else "✅ 無偵測到關鍵語義脆弱點。",
            impact_table_rows=impact_table
        )
        return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--files", required=True, help="Comma-separated list of changed files")
    parser.add_argument("--out", default="PR_IMPACT_REPORT.md")
    args = parser.parse_args()

    files = args.files.split(",")
    generator = CIReportGenerator(
        "skidiy_nodes.jsonl", 
        "skidiy_edges.jsonl", 
        "scripts/engine/templates/ci_graph_impact.md_template"
    )
    
    report = generator.generate_report(files)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"✅ Generated CI Impact Report: {args.out}")
