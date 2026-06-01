import re

file_path = "scratch/tmp_astropy_14096/astropy/coordinates/attributes.py"
content = open(file_path).read()

# Restore original first
import subprocess
subprocess.run("cd scratch/tmp_astropy_14096 && git checkout astropy/coordinates/attributes.py", shell=True)

content = open(file_path).read()

old_code = """    def __get__(self, instance, frame_cls=None):
        if instance is None:"""

new_code = """    def __get__(self, instance, frame_cls=None):
        try:
            if instance is None:"""

old_code_end = """        return out"""
new_code_end = """        return out
        except AttributeError as e:
            raise AttributeError(f"Attribute '{self.name}' not found: {e}") from e"""

open(file_path, "w").write(content.replace(old_code, new_code).replace(old_code_end, new_code_end))
