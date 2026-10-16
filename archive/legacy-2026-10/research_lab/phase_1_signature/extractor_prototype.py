import re
import hashlib
from dataclasses import dataclass

@dataclass
class FaultSignature:
    error_type: str
    file_path: str
    line_number: int
    message: str
    context_hash: str

class SignatureExtractor:
    @staticmethod
    def extract_from_text(text: str) -> list[FaultSignature]:
        signatures = []
        # Pattern 1: Python Traceback
        # File "path/to/file.py", line 123, in <module>
        # ErrorType: Message
        traceback_regex = re.compile(r'File \"(.*?)\", line (\d+), in (.*?)\n(.*?)\n(.*?): (.*)')
        matches = traceback_regex.findall(text)
        
        for match in matches:
            file_path, line, _, _, err_type, msg = match
            context_hash = hashlib.md5(f"{file_path}:{line}:{err_type}".encode()).hexdigest()
            signatures.append(FaultSignature(
                error_type=err_type,
                file_path=file_path,
                line_number=int(line),
                message=msg,
                context_hash=context_hash
            ))
            
        # Pattern 2: Generic 'No module named'
        mod_regex = re.compile(r"ModuleNotFoundError: No module named '(.*)'")
        mod_matches = mod_regex.findall(text)
        for mod in mod_matches:
            signatures.append(FaultSignature(
                error_type="ModuleNotFoundError",
                file_path="unknown",
                line_number=0,
                message=f"Missing module: {mod}",
                context_hash=hashlib.md5(f"missing:{mod}".encode()).hexdigest()
            ))
            
        return signatures

# --- Simulation / Research Tool ---
if __name__ == "__main__":
    sample_error = """
    Traceback (most recent call last):
      File "nexus/core/commander.py", line 42, in <module>
        import non_existent_pkg
    ModuleNotFoundError: No module named 'non_existent_pkg'
    """
    
    sigs = SignatureExtractor.extract_from_text(sample_error)
    print(f"Detected {len(sigs)} signatures:")
    for sig in sigs:
        print(f" - [{sig.error_type} at {sig.file_path}:L{sig.line_number}] {sig.message} (Hash: {sig.context_hash[:8]})")
