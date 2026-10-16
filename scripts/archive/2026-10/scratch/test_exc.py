import sys

class A:
    @property
    def prop(self):
        return self.random_attr

    def __getattr__(self, attr):
        exc_type, exc_val, exc_tb = sys.exc_info()
        if exc_val is not None:
            print("FOUND PREVIOUS EXCEPTION:", exc_val)
        raise AttributeError(f"A has no {attr}")

a = A()
try:
    a.prop
except Exception as e:
    print("CAUGHT:", e)
