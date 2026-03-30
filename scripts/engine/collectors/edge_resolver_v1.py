#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path

class EdgeResolver:
    def __init__(self, repo_path, nodes_path):
        self.repo_path = Path(repo_path)
        self.nodes = []
        with open(nodes_path, "r") as f:
            for line in f:
                self.nodes.append(json.loads(line))
        self.edges = []

    def resolve_sources(self):
        """Link SYMBOL_ACTOR -> SCHEMA_ENTITY (SOURCES)"""
        # Focus on high-value tables first
        tables = [n for n in self.nodes if n["type"] == "SCHEMA_ENTITY" and len(n["name"]) > 5]
        pattern = "|".join([n["name"] for n in tables])
        
        print(f"🔍 Searching for tables: {pattern}")
        try:
            # Single pass grep for all patterns
            cmd = ["grep", "-Erl", pattern, str(self.repo_path)]
            output = subprocess.check_output(cmd).decode().splitlines()
            
            # Map files back to actors
            for file_path_abs in output:
                try:
                    file_rel = str(Path(file_path_abs).relative_to(self.repo_path))
                    for node in self.nodes:
                        if node["path"] == file_rel and node["type"] == "SYMBOL_ACTOR":
                            # Check which actual table name matches
                            with open(file_path_abs, "r", errors="ignore") as f:
                                content = f.read()
                                for table in tables:
                                    if table["name"] in content:
                                        self.edges.append({
                                            "from": node["id"],
                                            "to": table["id"],
                                            "type": "SOURCES"
                                        })
                except ValueError:
                    continue
        except subprocess.CalledProcessError:
            pass

    def resolve_consumes(self):
        """Link UI_COMPONENT -> SCHEMA_ENTITY/API (CONSUMES)"""
        uis = [n for n in self.nodes if n["type"] == "UI_COMPONENT"]
        tables = [n for n in self.nodes if n["type"] == "SCHEMA_ENTITY" and len(n["name"]) > 2]

        for ui in uis:
            ui_path = self.repo_path / ui["path"]
            with open(ui_path, "r", encoding="utf-8") as f:
                content = f.read()
                for table in tables:
                    if table["name"] in content:
                        self.edges.append({
                            "from": ui["id"],
                            "to": table["id"],
                            "type": "CONSUMES"
                        })

    def export_jsonl(self, output_path):
        with open(output_path, "w", encoding="utf-8") as f:
            for edge in self.edges:
                f.write(json.dumps(edge) + "\n")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--nodes", required=True)
    parser.add_argument("--out", default="nexus_graph_edges.jsonl")
    args = parser.parse_args()

    resolver = EdgeResolver(args.repo, args.nodes)
    print("🕸️  Resolving SOURCES links...")
    resolver.resolve_sources()
    print("📱 Resolving CONSUMES links...")
    resolver.resolve_consumes()
    resolver.export_jsonl(args.out)
    print(f"✅ Exported {len(resolver.edges)} edges to {args.out}")
