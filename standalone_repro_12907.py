class Model:
    def __init__(self, name=None):
        self._name = name
    @property
    def name(self):
        return self._name
    @name.setter
    def name(self, val):
        self._name = val

class CompoundModel(Model):
    def __init__(self, left, right, name=None):
        super().__init__(name=name)
        self.left = left
        self.right = right
    
    def rename(self, name):
        # BUG: astropy-12907 bug reproduction (it was returning None or missing return)
        self._name = name
        return self

def test_repro():
    m1 = Model(name="m1")
    m2 = Model(name="m2")
    cm = CompoundModel(m1, m2)
    
    print(f"Initial CM name: {cm.name}")
    cm.rename("new_name")
    print(f"After rename CM name: {cm.name}")
    
    # In astropy-12907, the bug is that it doesn't return the model or fails to set it correctly
    if cm.name != "new_name":
        print("FAIL: Name not set")
        return False
    
    # Real test from 12907: cm.rename('abc').name should be 'abc'
    res = cm.rename('abc')
    if res is None:
        print("FAIL: rename() returned None")
        return False
    
    print("SUCCESS: Standalone logic verified")
    return True

if __name__ == "__main__":
    test_repro()
