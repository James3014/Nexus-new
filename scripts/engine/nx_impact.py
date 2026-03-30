#!/usr/bin/env python3
import json
import argparse
from collections import defaultdict

class ImpactAnalyzer:
    def __init__(self, nodes_path, edges_path):
        self.nodes = {}
        with open(nodes_path, "r") as f:
            for line in f:
                n = json.loads(line)
                self.nodes[n["id"]] = n

        self.adj = defaultdict(list)
        with open(edges_path, "r") as f:
            for line in f:
                e = json.loads(line)
                self.adj[e["to"]].append(e["from"]) # Edge is from Actor -> Schema, so impact is Schema -> Actor

    def find_impact(self, start_node_name):
        # Find node ID by name
        start_id = None
        for node_id, node in self.nodes.items():
            if node["name"] == start_node_name:
                start_id = node_id
                break
        
        if not start_id:
            return f"❌ Node '{start_node_name}' not found in graph."

        # BFS to find impact
        impacted = []
        queue = [start_id]
        visited = {start_id}
        
        while queue:
            curr = queue.pop(0)
            for neighbor in self.adj[curr]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    impacted.append(self.nodes[neighbor])
                    queue.append(neighbor)
        
        return impacted

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True, help="Node name to query (e.g., questions)")
    parser.add_argument("--nodes", default="skidiy_nodes.jsonl")
    parser.add_argument("--edges", default="skidiy_edges.jsonl")
    args = parser.parse_args()

    analyzer = ImpactAnalyzer(args.nodes, args.edges)
    results = analyzer.find_impact(args.query)

    if isinstance(results, str):
        print(results)
    else:
        print(f"📊 Impact Analysis for '{args.query}':")
        print(f"Found {len(results)} impacted files/symbols.\n")
        # Group by type
        by_type = defaultdict(list)
        for r in results:
            by_type[r["type"]].append(r)

        for t, nodes in by_type.items():
            print(f"[{t}]")
            for n in nodes:
                print(f"  - {n['name']} ({n['path']})")
