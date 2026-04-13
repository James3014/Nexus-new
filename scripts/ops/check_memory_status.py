import sys
sys.path.append('.')
import lancedb
from pathlib import Path
try:
    db = lancedb.connect(".nexus/memory/memory_index.lancedb")
    tables = db.list_tables()
    print(f"Tables: {tables}")
    for t in tables:
        tbl = db.open_table(t)
        print(f"Table '{t}' has {tbl.count_rows()} chunks/rows")
except Exception as e:
    print(f"Error accessing LanceDB: {e}")
