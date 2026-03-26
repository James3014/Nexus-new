#!/usr/bin/env python3
import os
import re
import json
import ast
from pathlib import Path
import subprocess

class NodeCollector:
    def __init__(self, repo_path):
        self.repo_path = Path(repo_path)
        self.nodes = []
        self.edges = []

    def add_node(self, node_type, name, path, attributes):
        node = {
            "id": f"{node_type}:{name}",
            "type": node_type,
            "name": name,
            "path": str(path.relative_to(self.repo_path)) if path else None,
            "attributes": attributes
        }
        self.nodes.append(node)
        return node["id"]

    def collect_sql_nodes(self):
        """Extract SCHEMA_ENTITY from SQL files."""
        sql_files = list(self.repo_path.rglob("*.sql"))
        for sql_file in sql_files:
            with open(sql_file, "r", encoding="utf-8") as f:
                content = f.read()
                # Simple regex for CREATE TABLE
                tables = re.findall(r"CREATE TABLE (\w+)", content, re.IGNORECASE)
                for table in tables:
                    self.add_node("SCHEMA_ENTITY", table, sql_file, {"engine": "PostgreSQL"})

    def collect_python_nodes(self):
        """Extract SYMBOL_ACTOR from Python files using AST."""
        py_files = list(self.repo_path.rglob("*.py"))
        for py_file in py_files:
            if "venv" in str(py_file) or "site-packages" in str(py_file):
                continue
            try:
                with open(py_file, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read())
                    for node in ast.walk(tree):
                        if isinstance(node, ast.ClassDef):
                            self.add_node("SYMBOL_ACTOR", f"{py_file.stem}.{node.name}", py_file, {"type": "class"})
                        elif isinstance(node, ast.FunctionDef):
                            self.add_node("SYMBOL_ACTOR", f"{py_file.stem}.{node.name}", py_file, {"type": "function"})
            except Exception as e:
                print(f"Error parsing {py_file}: {e}")

    def collect_js_nodes(self):
        """Extract UI_COMPONENT from JS files using simple grep."""
        js_files = list(self.repo_path.rglob("*.js"))
        for js_file in js_files:
            if "node_modules" in str(js_file):
                continue
            with open(js_file, "r", encoding="utf-8") as f:
                content = f.read()
                if "supabase" in content.lower() or "fetch" in content.lower():
                    self.add_node("UI_COMPONENT", js_file.name, js_file, {"framework": "Vanilla/Supabase"})

    def export_jsonl(self, output_path):
        with open(output_path, "w", encoding="utf-8") as f:
            for node in self.nodes:
                f.write(json.dumps(node) + "\n")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--out", default="nexus_graph_nodes.jsonl")
    args = parser.parse_args()

    collector = NodeCollector(args.repo)
    print(f"🚀 Collecting nodes from {args.repo}...")
    collector.collect_sql_nodes()
    collector.collect_python_nodes()
    collector.collect_js_nodes()
    collector.export_jsonl(args.out)
    print(f"✅ Exported {len(collector.nodes)} nodes to {args.out}")
