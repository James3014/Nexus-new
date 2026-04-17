"""
msa_indexer.py
Incremental & Type-Aware Indexing.
"""
import hashlib
import os
import subprocess
from typing import List, Dict, Any

SCHEMA_METADATA = {
    "id": str,
    "vector": "array",
    "content": str,
    "type": str,
    "version_id": str,
    "source_hash": str,
    "ttl": int,
    "confidence_decay": float
}

def get_file_hash(filepath: str) -> str:
    if not os.path.exists(filepath):
        return ""
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

def get_git_diff_files(repo_root: str, base_branch: str = "HEAD") -> List[str]:
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", base_branch],
            cwd=repo_root, capture_output=True, text=True, check=True
        )
        files = result.stdout.strip().split('\n')
        return [f for f in files if f]
    except subprocess.CalledProcessError:
        return []

def incremental_index(repo_root: str) -> List[Dict[str, Any]]:
    changed_files = get_git_diff_files(repo_root)
    indexed_data = []
    
    for fpath in changed_files:
        full_path = os.path.join(repo_root, fpath)
        file_hash = get_file_hash(full_path)
        if not file_hash:
            continue
            
        file_type = "code"
        if "reports" in fpath or "artifacts" in fpath:
            file_type = "artifact"
        elif "beliefs" in fpath:
            file_type = "belief"
        elif "rule" in fpath or "MUSE_PROTO" in fpath:
            file_type = "rule"
            
        indexed_data.append({
            "id": fpath,
            "content": f"Mock Content of {fpath}",
            "type": file_type,
            "version_id": "v1.0",
            "source_hash": file_hash,
            "ttl": 86400,
            "confidence_decay": 1.0
        })
    return indexed_data
