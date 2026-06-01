class A:
    def __getattr__(self, attr):
        raise AttributeError(f"A object has no attribute {attr}")

class B(A):
    @property
    def prop(self):
        return self.random_attr

b = B()
b.prop
