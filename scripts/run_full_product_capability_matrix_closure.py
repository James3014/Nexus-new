#!/usr/bin/env python3
"""P3: Build real 68-row capability matrix runner and persist runtime receipts."""

from __future__ import annotations

import os

from nexus.services.product_capability_closure_runner import (
    run_68_matrix_and_generate_receipt,
)


if __name__ == "__main__":
    os.environ["NEXUS_ARMOR_ALLOW_EPHEMERAL"] = "1"
    res = run_68_matrix_and_generate_receipt()
    print("Matrix pass count:", res.get("product_matrix_pass", 0))
    print("Final verdict:", res.get("final_verdict", "N/A"))
