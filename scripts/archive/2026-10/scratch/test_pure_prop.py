class A:
    def __getattr__(self, name):
        raise AttributeError(f"A has no {name}")

class B(A):
    @property
    def prop(self):
        return self.random_attr

b = B()
try:
    b.prop
except Exception as e:
    print("Caught:", repr(e))
