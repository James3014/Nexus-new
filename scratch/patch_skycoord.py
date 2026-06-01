import re

file_path = "scratch/tmp_astropy_14096/astropy/coordinates/sky_coordinate.py"
content = open(file_path).read()

old_code = """            if not attr.startswith("_") and hasattr(self._sky_coord_frame, attr):
                return getattr(self._sky_coord_frame, attr)"""

new_code = """            if not attr.startswith("_"):
                try:
                    return getattr(self._sky_coord_frame, attr)
                except AttributeError as e:
                    if str(e).endswith(f"'{attr}'"):
                        pass
                    else:
                        raise"""

if old_code in content:
    open(file_path, "w").write(content.replace(old_code, new_code))
    print("Patched SkyCoord!")
else:
    print("Not found in SkyCoord")
