import numpy as np
from astropy.table import Table, NdarrayMixin

# Create structured array
data = np.array([(1, 'a'), (2, 'b')], dtype=[('col1', 'i4'), ('col2', 'S1')])
t = Table([data], names=['data'])

print(f"Column type: {type(t['data'])}")
# In the current (buggy) version, this should be NdarrayMixin
if isinstance(t['data'], NdarrayMixin):
    print("REPRODUCED: Structured array converted to NdarrayMixin")
    exit(1)
else:
    print("NOT REPRODUCED: Structured array NOT converted to NdarrayMixin")
    exit(0)
