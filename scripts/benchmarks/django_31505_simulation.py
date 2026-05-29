import threading
import time
import os
import shutil
from pathlib import Path
import uuid

class MockStorage:
    def __init__(self):
        self.files = {}
        self.disk_path = Path("./tmp_storage")
        self.disk_path.mkdir(exist_ok=True)

    def exists(self, name):
        return (self.disk_path / name).exists()

    def save(self, name, content):
        # 模擬耗時操作，擴大 Race Condition 視窗
        time.sleep(0.05)
        
        # Fixed implementation: 使用唯一識別碼避免覆蓋
        unique_name = f"{name}_{uuid.uuid4()}"
        with open(self.disk_path / unique_name, "w") as f:
            f.write(content)
        return unique_name

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
    
    t1 = threading.Thread(target=model.save, args=("report.txt", "content_A"))
    t2 = threading.Thread(target=model.save, args=("report.txt", "content_B"))
    
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    
    actual_on_disk = (storage.disk_path / "report.txt").read_text() if (storage.disk_path / "report.txt").exists() else "MISSING"
    print(f"\n🏁 [Final Audit] File on disk content: {actual_on_disk}")

def test_challenge():
    # 每次清理
    storage = MockStorage()
    if storage.disk_path.exists():
        shutil.rmtree(storage.disk_path)
    storage.disk_path.mkdir(exist_ok=True)
    
    model = DjangoModel(storage)
    
    t1 = threading.Thread(target=model.save, args=("report.txt", "content_A"))
    t2 = threading.Thread(target=model.save, args=("report.txt", "content_B"))
    
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    
    # 驗證：兩個檔案必須都被妥善保存，且都擁有獨一無二的檔名 (Injectivity - 單射性)
    files = list(storage.disk_path.glob("report*"))
    assert len(files) == 2, f"Race condition detected! Only {len(files)} files on disk: {[f.name for f in files]}"
    contents = {f.read_text() for f in files}
    assert contents == {"content_A", "content_B"}, f"Wrong file contents: {contents}"
    print("🎉 All assertions passed! Django #31505 SOTA Fix Verified!")

if __name__ == "__main__":
    run_challenge()