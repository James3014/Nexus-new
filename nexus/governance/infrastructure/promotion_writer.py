import os
import shutil
from typing import Any, Callable
from nexus.evaluation.contracts import PromotionReceipt

class PromotionWriter:
    """
    💾 Task: Rollback-safe transactional write (Infrastructure)
    職責: 實施「備份-寫入-清理」模式，確保晉升操作的原子性。
    """
    @staticmethod
    def transactional_write(target_path: str, content: str, write_op: Callable[[str, str], None]):
        backup_path = target_path + ".governance_bak"
        
        # 1. Backup
        if os.path.exists(target_path):
            shutil.copy2(target_path, backup_path)
            
        try:
            # 2. Write
            write_op(target_path, content)
            
            # 3. Commit (Remove backup)
            if os.path.exists(backup_path):
                os.remove(backup_path)
                
            print(f"✅ TRANSACTIONAL WRITE SUCCESS: {target_path}")
            
        except Exception as e:
            # 4. Rollback
            print(f"❌ WRITE FAILED. Rolling back {target_path}...")
            if os.path.exists(backup_path):
                shutil.move(backup_path, target_path)
            raise e
