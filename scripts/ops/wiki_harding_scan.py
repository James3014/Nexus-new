import os
import sys
from pathlib import Path

# Ensure we are using the .venv environment
repo_root = Path("/Users/jameschen/Workspace/nexus")
venv_packages = repo_root / ".venv" / "lib" / "python3.12" / "site-packages"
if str(venv_packages) not in sys.path:
    sys.path.insert(0, str(venv_packages))

try:
    from graphify.build import build
    from graphify.wiki import to_wiki
    import networkx as nx
    # We'll use a simplified ingest logic for the first pass
    print("🛡️ [Nexus:Wiki] Initiating Topology Hardening...")
    
    # 1. Simulate extraction (In a real scenario, this would call graphify.extract)
    # For now, we seed the graph with core file nodes to prove the routing
    G = nx.Graph()
    wiki_path = repo_root / "nexus_wiki_vault"
    
    # Simple file-to-node mapping
    for md_file in wiki_path.glob("**/*.md"):
        rel_path = md_file.relative_to(wiki_path)
        node_id = str(rel_path)
        G.add_node(node_id, label=md_file.stem, source_file=str(rel_path), community=1)
        
    # Cross-reference logic (simplified)
    for node in list(G.nodes()):
        content = (wiki_path / node).read_text(errors="ignore")
        if "[[" in content:
            # Found a wiki-link
            import re
            links = re.findall(r"\[\[(.*?)\]\]", content)
            for link in links:
                # Try to find target node
                for target in G.nodes():
                    if G.nodes[target]["label"] == link:
                        G.add_edge(node, target, relation="wiki-link", confidence="EXTRACTED")

    # 2. Export to Wiki Index
    output_dir = wiki_path / ".nexus" / "graph"
    communities = {1: list(G.nodes())}
    count = to_wiki(G, communities, output_dir)
    
    print(f"✅ [Nexus:Wiki] Hardening Complete. {count} articles generated at {output_dir}")
    print(f"📊 [Nexus:Wiki] Topology: {G.number_of_nodes()} nodes | {G.number_of_edges()} edges.")

except ImportError as e:
    print(f"❌ [Nexus:Wiki] Engine failure: {e}")
    sys.exit(1)
