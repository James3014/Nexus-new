# Hyper fixture

`pricing.py` divides the discount percent by 10 instead of 100; `test_pricing.py` is the
focused verifier. The audit runs a multi-candidate hyper sprint on the local channel: each
model candidate comes from the Workforce-admitted ollama worker (M5 tunnel) through the armored
local lane and is re-scored by the sprint with `pytest -q test_pricing.py`.
