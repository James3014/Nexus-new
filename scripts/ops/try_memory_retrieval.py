import sys
import json
import lancedb
sys.path.append('.')

def search_memory(query: str):
    db = lancedb.connect(".nexus/memory/memory_index.lancedb")
    tbl = db.open_table("memory_index")
    # Fetch random 3 records with no filter
    results = tbl.search().limit(3).to_pandas()
    
    print(f"\n🧠 [Deep Memory Retrieval] Sampling latest learned chunks:")
    for idx, row in results.iterrows():
        print(f"\n--- [Memory Fragment {idx+1}] ---")
        print(f"🔹 ID: {row['record_id']}")
        print(f"🔹 Type: {row['record_type']} | Phase: {row['phase']}")
        payload = json.loads(row['payload_json'])
        # just print first 200 chars of payload
        print(f"🔹 Insight / Content snippet: {str(payload)[:200]}...")

if __name__ == "__main__":
    search_memory("error")
