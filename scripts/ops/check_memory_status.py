import sys
sys.path.append('.')
import lancedb
from pathlib import Path
try:
    from nexus.services.lancedb_roots import MEMORY_INDEX, resolve_lancedb_root

    db = lancedb.connect(str(resolve_lancedb_root(MEMORY_INDEX, Path("."), honor_env=False)))
    tables = db.list_tables()
    print(f"Tables: {tables}")
    for t in tables:
        tbl = db.open_table(t)
        print(f"Table '{t}' has {tbl.count_rows()} chunks/rows")
except Exception as e:
    print(f"Error accessing LanceDB: {e}")
