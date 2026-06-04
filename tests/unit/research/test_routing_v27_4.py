import unittest
from nexus.research.domain.route_planner import RoutePlanner

class TestRoutingV274(unittest.TestCase):
    def test_django_auto_classification(self):
        # 修正斷言以符合 RoutePlanner 的 django_migration 兼容邏輯
        receipt = RoutePlanner.plan_route("t1", "Update db_table for user profile")
        self.assertEqual(receipt.selected_route, "django_migration")
        self.assertIn("Django migration", receipt.rationale)
        
    def test_astropy_auto_classification(self):
        receipt = RoutePlanner.plan_route("t2", "Fix FITS header scaling")
        self.assertEqual(receipt.selected_route, "astropy")
        
    def test_fallback_logic(self):
        receipt = RoutePlanner.plan_route("t3", "unknown fix")
        self.assertEqual(receipt.selected_route, "general_repair")

    def test_manual_override(self):
        from nexus.research.domain.routing_receipt import RoutingReceipt
        r = RoutingReceipt('m1', 'django', 1.0, 'forced', manual_override=True)
        self.assertTrue(r.manual_override)

if __name__ == "__main__":
    unittest.main()
