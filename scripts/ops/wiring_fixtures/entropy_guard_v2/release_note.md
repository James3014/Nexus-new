# Release 2.4.1

This release fixes the refund rounding bug in `pricing.py`: totals are now rounded half-up
to two decimals before tax, matching the invoice service. The `compute_total(items)` helper
keeps its signature; callers do not need to change.

Upgrade notes:

- Run `python -m pytest -q test_pricing.py` after upgrading.
- The cache key format `refund:v2:<order_id>` is unchanged.
- Rollback: redeploy 2.4.0 (commit 3f04473d) if invoices disagree.
