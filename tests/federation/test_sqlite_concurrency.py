import pytest
import sqlite3
import threading
import time
from pathlib import Path
from nexus.federation.node_registry import NodeRegistry, NodeRecord

def test_concurrency_without_timeout(tmp_path: Path) -> None:
    db_path = tmp_path / "stuck.db"
    
    # 事先在主線程建立好資料表，避免 "no such table" 錯誤
    conn_init = sqlite3.connect(str(db_path))
    conn_init.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER PRIMARY KEY)")
    conn_init.commit()
    conn_init.close()
    
    # 故意在背景線程中開啟獨佔的事務 (EXCLUSIVE Transaction)，並持有 0.5 秒不放
    def hold_lock():
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("BEGIN EXCLUSIVE TRANSACTION")
        conn.execute("INSERT INTO test DEFAULT VALUES")
        time.sleep(0.5)
        conn.commit()
        conn.close()

    t = threading.Thread(target=hold_lock)
    t.start()
    
    # 主線程稍微等待以確保背景線程拿到了寫鎖
    time.sleep(0.1)
    
    # 主線程嘗試進行連線且無 timeout，此時嘗試寫入應當立即拋出 Database Locked 異常
    conn2_zero_timeout = sqlite3.connect(str(db_path), timeout=0)
    with pytest.raises(sqlite3.OperationalError) as excinfo:
        conn2_zero_timeout.execute("INSERT INTO test DEFAULT VALUES")
    assert "locked" in str(excinfo.value)
    conn2_zero_timeout.close()
    
    t.join()

def test_concurrency_with_timeout(tmp_path: Path) -> None:
    db_path = tmp_path / "safe.db"
    registry = NodeRegistry(db_path) # 這將使用我們升級後的 NodeRegistry，自帶高超時 timeout

    # 模擬 5 個線程同時高頻寫入 node_registry 心跳與註冊
    errors = []
    
    def worker(worker_id: int):
        try:
            for i in range(10):
                node = NodeRecord(
                    node_id=f"node-{worker_id}-{i}",
                    host="localhost",
                    port=8000 + worker_id,
                    status="ONLINE",
                    last_heartbeat=time.time(),
                    load=0.1,
                    capabilities=["cpu"]
                )
                registry.register(node)
                registry.heartbeat(f"node-{worker_id}-{i}", load=0.2)
                time.sleep(0.01)
        except Exception as e:
            errors.append(e)

    threads = []
    for i in range(5):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    # 驗證在超時排隊的WAL硬化下，所有併發寫入都能成功，沒有拋出 database locked 錯誤
    assert len(errors) == 0, f"Concurrent database operations failed with: {errors}"
