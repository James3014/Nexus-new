import astropy.coordinates as coord
import sys

class custom_coord(coord.SkyCoord):
    @property
    def prop(self):
        return self.random_attr

def test_repro():
    print("🚀 Running reproduction for astropy-14096...")
    try:
        c = custom_coord('00h42m30s', '+41d12m00s', frame='icrs')
        c.prop
    except AttributeError as e:
        msg = str(e)
        print(f"Captured AttributeError: {msg}")
        if "random_attr" in msg:
            print("🟢 SUCCESS: Error message is correct. Bug is fixed or not present.")
            return 0
        else:
            print("🔴 BUG REPRODUCED: Error message is still misleading (mentions 'prop' instead of 'random_attr').")
            return 1
    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 2
    return 0

if __name__ == "__main__":
    sys.exit(test_repro())
