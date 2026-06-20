import sys
from pathlib import Path
from nexus.services.local_heal.granular_localizer import GranularMethodLocalizer

repo_dir = Path(".nexus/workspaces/astropy")
desc = """
Traceback (most recent call last):
  File "test.py", line 11, in <module>
    c.prop
  File "/Users/dstansby/miniconda3/lib/python3.7/site-packages/astropy/coordinates/sky_coordinate.py", line 600, in __getattr__
    .format(self.__class__.__name__, attr))
AttributeError: 'custom_coord' object has no attribute 'prop'
"""
loc = GranularMethodLocalizer()
print("Starting rank_files...")
res = loc.rank_files(desc, repo_dir, search_symbols=["SkyCoord", "__getattr__"])
print(f"Found {len(res)} files.")
if res:
    print(res[0][1]['path'])
    bundle = loc.localize(res[0][1]['path'], res[0][1]['content'], desc)
    print("Bundle created. snippet length:", len(bundle.primary_snippet))
