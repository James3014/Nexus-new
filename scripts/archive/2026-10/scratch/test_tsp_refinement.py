import sys
import os
from pathlib import Path

# 確保能 import nexus 模組
sys.path.append(os.getcwd())

from nexus.services.local_heal.localizer import Localizer

def test_refinement():
    localizer = Localizer()
    file_path = "scratch/tmp_astropy_14096/astropy/coordinates/attributes.py"
    content = Path(file_path).read_text(errors="replace")
    query = "AttributeError in frame attributes should propagate correctly. When a property in a coordinate frame attribute raises AttributeError, it is currently shadowed by the attribute's own __get__"
    
    print(f"Original content length: {len(content)}")
    refined = localizer.refine_by_functions(file_path, content, query)
    print(f"Refined content length: {len(refined)}")
    print("\n--- REFINED HEAD ---")
    print("\n".join(refined.splitlines()[:50]))
    
if __name__ == "__main__":
    test_refinement()
