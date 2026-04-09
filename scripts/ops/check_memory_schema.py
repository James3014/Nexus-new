import sys
import lancedb
sys.path.append('.')

db = lancedb.connect(".nexus/memory/memory_index.lancedb")
for t in db.list_tables():
    tbl = db.open_table(t)
    df = tbl.search().limit(1).to_pandas()
    print(f"\n[{t}] Schema & Sample:")
    print(df.to_dict('records'))
