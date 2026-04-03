#!/usr/bin/env python3
"""Phase 1：按時間/大小切分歷史資料"""
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any

def slice_jsonl(input_path: Path, days: int = 30, max_mb: float = 1.0) -> List[str]:
    """切分 jsonl 檔案，按天數與大小"""
    if not input_path.exists():
        print(f"⚠️ Input path not found: {input_path}")
        return []

    slices = []
    chunk_size_mb = max_mb * 1024 * 1024  # MB → bytes
    
    with input_path.open() as f:
        lines = f.readlines()
    
    # 按時間切分（最後 N 天）
    cutoff_date = datetime.now() - timedelta(days=days)
    recent_lines = []
    for line in lines:
        try:
            record = json.loads(line)
            # Support both ISO format and potential missing timestamps (fallback)
            ts_str = record.get('timestamp', record.get('ts', ''))
            if ts_str:
                try:
                    # Robust ISO parsing
                    ts = datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
                    if ts >= cutoff_date:
                        recent_lines.append(line)
                except:
                    # Fallback if parsing fails but line exists
                    recent_lines.append(line)
            else:
                # No timestamp? Keep it for safety in 148K file.
                recent_lines.append(line)
        except (json.JSONDecodeError, ValueError):
            recent_lines.append(line)  # 保留無效行或格式不合行
    
    if not recent_lines:
        print(f"⚪ No recent data found within {days} days.")
        return []

    # 按大小切分
    current_chunk = []
    current_size = 0
    chunk_id = 0
    
    # 確保輸出目錄存在 (Relative to repo root: .nexus/eternal/slices)
    output_dir = Path(".nexus/eternal/slices")
    output_dir.mkdir(parents=True, exist_ok=True)

    for line in recent_lines:
        line_size = len(line.encode('utf-8'))
        if current_size + line_size > chunk_size_mb and current_chunk:
            slice_file = output_dir / f"{input_path.stem}-{cutoff_date.strftime('%Y%m%d')}-{chunk_id}.jsonl"
            slice_file.write_text(''.join(current_chunk))
            slices.append(str(slice_file))
            current_chunk = [line]
            current_size = line_size
            chunk_id += 1
        else:
            current_chunk.append(line)
            current_size += line_size
    
    # 最後一個 chunk
    if current_chunk:
        slice_file = output_dir / f"{input_path.stem}-{cutoff_date.strftime('%Y%m%d')}-{chunk_id}.jsonl"
        slice_file.write_text(''.join(current_chunk))
        slices.append(str(slice_file))
    
    # 寫入 slices manifest
    manifest_path = output_dir / "manifest.json"
    existing_manifest = {}
    if manifest_path.exists():
        try:
            existing_manifest = json.loads(manifest_path.read_text())
        except: pass
    
    new_entry = {
        "input_file": str(input_path),
        "slices": slices,
        "cutoff_date": cutoff_date.isoformat(),
        "total_slices": len(slices),
        "total_mb": sum(Path(s).stat().st_size / (1024*1024) for s in slices),
        "updated_at": datetime.now().isoformat()
    }
    
    # Update map
    if "sources" not in existing_manifest: existing_manifest["sources"] = {}
    existing_manifest["sources"][input_path.name] = new_entry
    manifest_path.write_text(json.dumps(existing_manifest, indent=2))
    
    return slices

if __name__ == "__main__":
    import sys
    # Default to policy memory
    file_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".nexus/knowledge/policymemory.jsonl")
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    slices = slice_jsonl(file_path, days=days)
    print(f"切分完成：{len(slices)} 個檔案")
    for s in slices:
        print(f"  - {s} ({Path(s).stat().st_size / (1024*1024):.2f} MB)")
