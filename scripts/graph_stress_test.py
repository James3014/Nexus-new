#!/usr/bin/env python3
import time
import random
from collections import defaultdict, deque

def run_stress_test(num_nodes=5000, num_edges=10000):
    print(f"🏗️  Generating synthetic graph: {num_nodes} nodes, {num_edges} edges...")
    
    # 1. Create nodes
    nodes = [f"node_{i}" for i in range(num_nodes)]
    
    # 2. Create random edges (Impact flows forward)
    # To keep it realistic, we create a layered DAG
    adj = defaultdict(list)
    for _ in range(num_edges):
        u = random.randint(0, num_nodes - 2)
        v = random.randint(u + 1, num_nodes - 1) # Forward linking to guarantee DAG
        adj[nodes[u]].append(nodes[v])
    
    print("⚡ Starting Impact Query Stress Test (BFS)...")
    
    start_time = time.time()
    num_queries = 100
    
    for _ in range(num_queries):
        # Pick a random starting node
        start_node = random.choice(nodes[:100])
        
        # BFS Traversal
        visited = {start_node}
        queue = deque([start_node])
        while queue:
            curr = queue.popleft()
            for neighbor in adj[curr]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
                    
    end_time = time.time()
    avg_latency = ((end_time - start_time) / num_queries) * 1000 # in ms
    
    print(f"\n📊 Stress Test Results:")
    print(f"Total Nodes: {num_nodes}")
    print(f"Total Edges: {num_edges}")
    print(f"Avg Query Latency (P50): {avg_latency:.2f} ms")
    
    if avg_latency < 50:
        print("✅ PERFORMANCE TARGET MET (< 50ms)")
    else:
        print("❌ PERFORMANCE TARGET FAILED (> 50ms)")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--nodes", type=int, default=5000)
    parser.add_argument("--edges", type=int, default=10000)
    args = parser.parse_args()
    
    run_stress_test(args.nodes, args.edges)
