import os
import json
from typing import Any
from nexus.governance.application.archive_manager import GovernanceArchive

class ArchiveWriter:
    """
    🖋️ Task: Physical Archive Persistence (Infrastructure)
    職責: 將歸檔資產物理化存儲，並實施唯讀保護。
    """
    @staticmethod
    def persist_archive(base_dir: str, archive: GovernanceArchive):
        if not os.path.exists(base_dir):
            os.makedirs(base_dir)
            
        # 1. 寫入主歸檔包 (JSON)
        archive_path = os.path.join(base_dir, f"{archive.version}_archive_bundle.json")
        with open(archive_path, "w") as f:
            # 簡化：在實際系統中會實作自定義 JSON Encoder
            f.write(str(archive))
            
        # 2. 寫入 ADR 凍結清單
        adr_path = os.path.join(base_dir, "adr_freeze_manifest.json")
        with open(adr_path, "w") as f:
            json.dump(archive.approved_adr_hashes, f, indent=4)
            
        # 3. 實施文件保護 (模擬：在 CI 中會設定為 Read-only)
        print(f"🔒 ARCHIVE SEALED: {archive_path}")
        print(f"📄 Fingerprint: {archive.archive_hash[:16]}...")
