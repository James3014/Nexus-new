import sys

from target import gates_target

if gates_target() != "verified":
    sys.exit(1)
print("wiring-gates-verifier-pass")
