import sys
import os
from pathlib import Path

sys.path.append(os.getcwd())

from nexus.services.local_heal.localizer import Localizer

def test_refinement():
    localizer = Localizer()
    file_path = "scratch/tmp_astropy_14096/astropy/coordinates/sky_coordinate.py"
    content = Path(file_path).read_text(errors="replace")
    query = "astropy-14096 in astropy/coordinates/sky_coordinate.py: Subclassed SkyCoord property raises misleading AttributeError. Non-existing attribute access inside a property should give attribute error for the original missing attribute, not for the property. Currently SkyCoord.__getattr__ raises a new AttributeError and shadows the original one."
    
    print(f"Original length: {len(content)}")
    refined = localizer.refine_by_functions(file_path, content, query)
    print(f"Refined length: {len(refined)}")
    print("Contains __getattr__?", "__getattr__" in refined)

if __name__ == "__main__":
    test_refinement()
