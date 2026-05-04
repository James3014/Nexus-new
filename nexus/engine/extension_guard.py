from pathlib import Path
from typing import List, Set

class ExtensionGuard:
    """🛡️ P0: Governance Hard Lock for file extensions.
    
    This module enforces the 'Physical Lock' strategy for V3 routing,
    ensuring that code files are barred from entering L1 (Green-Lane) governance.
    """
    
    CODE_EXTENSIONS: Set[str] = {
        '.py', '.js', '.rs', '.go', '.ts', '.c', '.cpp', '.h', 
        '.mjs', '.cjs', '.java', '.kt', '.swift', '.rb', '.php'
    }

    @classmethod
    def is_code_file(cls, file_path: str) -> bool:
        """Check if a file path belongs to code categories based on its extension."""
        return Path(file_path).suffix.lower() in cls.CODE_EXTENSIONS

    @classmethod
    def validate_l1_eligibility(cls, target_files: List[str]) -> bool:
        """
        🛡️ L1 綠色通道物理鎖。
        
        Rules:
        - If any file in target_files has a code extension, return False (ineligible for L1).
        - Otherwise, return True.
        
        Args:
            target_files: A list of file paths involved in the current task.
            
        Returns:
            bool: True if eligible for L1, False otherwise.
        """
        if not target_files:
            return True # No files to check, potentially a metadata-only task
            
        for f in target_files:
            if cls.is_code_file(f):
                return False
        return True
