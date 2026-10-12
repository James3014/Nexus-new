import sys

from calc import add

if add(2, 3) != 5:
    sys.exit("add must return the sum")
print("repro-pass")
