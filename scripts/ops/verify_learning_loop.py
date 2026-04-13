import sys
import os
import lancedb
from typing import List
sys.path.append('.')

def check_learning_status():
    try:
        db = lancedb.connect(".nexus/memory/memory_index.lancedb")
        tables = db.list_tables()
        
        print("🔍 [Phase 1: Memory & Wisdom Storage check]")
        for t in tables:
            tbl = db.open_table(t)
            print(f"   ✅ Table '{t}' actively tracking {tbl.count_rows()} records.")
            
        print("\n🔍 [Phase 2: Example Active Retrievals (Semantic Search)]")
        if "wisdom_registry" in tables:
            print("   --- Wisdom Layer Sample ---")
            tbl = db.open_table("wisdom_registry")
            # Limit to 2 without vector search, just fetch latest
            results = tbl.search().limit(2).to_pandas()
            for _, row in results.iterrows():
                print(f"      - [Theme: {row.get('theme', 'N/A')}] Insights: {str(row.get('insights', ''))[:80]}...")
                
        if "memory_index" in tables:
            print("\n   --- Memory Index Sample ---")
            tbl = db.open_table("memory_index")
            # Fetch random 2 lessons
            results = tbl.search().limit(2).to_pandas()
            for _, row in results.iterrows():
                print(f"      - [Tag: {row.get('metadata', {}).get('tags', ['N/A'])}] Context: {str(row.get('text', ''))[:80]}...")
                
    except Exception as e:
        print(f"❌ Verification failed: {e}")

if __name__ == "__main__":
    check_learning_status()
