import sys
import lancedb
sys.path.append('.')

from nexus.services.lancedb_roots import MEMORY_INDEX, resolve_lancedb_root  # noqa: E402

db = lancedb.connect(str(resolve_lancedb_root(MEMORY_INDEX, ".", honor_env=False)))
for t in db.list_tables():
    tbl = db.open_table(t)
    df = tbl.search().limit(1).to_pandas()
    print(f"\n[{t}] Schema & Sample:")
    print(df.to_dict('records'))
