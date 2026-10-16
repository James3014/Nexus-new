import re

file_path = "scratch/tmp_astropy_14096/astropy/coordinates/attributes.py"
content = open(file_path).read()

old_code = """    def __get__(self, instance, frame_cls=None):
        print(f"DEBUG: Attribute.__get__ called for {self.name}", flush=True)
        if instance is None:
            out = self.default
        else:
            out = getattr(instance, "_" + self.name, self.default)
            if out is None:
                out = getattr(instance, self.secondary_attribute, self.default)"""

new_code = """    def __get__(self, instance, frame_cls=None):
        if instance is None:
            out = self.default
        else:
            try:
                out = getattr(instance, "_" + self.name)
            except AttributeError as e:
                if str(e).endswith(f"'{'_' + self.name}'"):
                    if self.default is not None:
                        out = self.default
                    elif self.secondary_attribute:
                        try:
                            out = getattr(instance, self.secondary_attribute)
                        except AttributeError as e2:
                            if str(e2).endswith(f"'{self.secondary_attribute}'"):
                                out = self.default
                            else:
                                raise
                    else:
                        out = None
                else:
                    raise"""

if old_code in content:
    open(file_path, "w").write(content.replace(old_code, new_code))
    print("Patched!")
else:
    print("Not found")
