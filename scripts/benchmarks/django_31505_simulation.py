import threading
import time
import os
from pathlib import Path

class MockStorage:
    def __init__(self):
        self.files = {}
        self.disk_path = Path("./tmp_storage")
        self.disk_path.mkdir(exist_ok=True)

    def exists(self, name):
        return (self.disk_path / name).exists()

    def save(self, name, content):
        # v23 Formal Fix: 實作單射性 (Unique Filename)
        import uuid
        actual_name = name
        while self.exists(actual_name):
            stem = Path(name).stem
            suffix = Path(name).suffix
            actual_name = f"{stem}_{uuid.uuid4().hex[:8]}{suffix}"
        
        with open(self.disk_path / actual_name, "w") as f:
            f.write(content)
        return actual_name

        
        # 模擬耗時操作，擴大 Race Condition 視窗
        time.sleep(0.05)
        
        with open(self.disk_path / name, "w") as f:
            f.write(content)
        return name

class DjangoModel:
    def __init__(self, storage):
        self.lock = threading.Lock()
        self.storage = storage
        self.file_field = None

    def save(self, filename, content):
        # 模擬 Django 的 FileField 保存邏輯
        with self.lock:
            self.file_field = self.storage.save(filename, content)
        print(f"✅ [DB] Record saved with file reference: {self.file_field}")

def run_challenge():
    storage = MockStorage()
    model = DjangoModel(storage)
    
    # 模擬兩個並行 Request 同時保存同一個檔案名但不同內容
    t1 = threading.Thread(target=model.save, args=("report.txt", "content_A"))
    t2 = threading.Thread(target=model.save, args=("report.txt", "content_B"))
    
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    
    # 最終驗證：磁碟檔案與 DB 紀錄是否一致
    actual_on_disk = (storage.disk_path / "report.txt").read_text() if (storage.disk_path / "report.txt").exists() else "MISSING"
    print(f"\n🏁 [Final Audit] File on disk content: {actual_on_disk}")
    # 如果兩個 thread 都回報成功，但只有一個 content 在磁碟上，就是 Race Condition。
    # 在 Django 31505 中，這會導致 metadata 指向了一個被錯誤跳過或覆蓋的舊檔。

if __name__ == "__main__":
    run_challenge()
