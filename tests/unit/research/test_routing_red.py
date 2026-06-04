import unittest
from nexus.research.domain.route_planner import RoutePlanner

class TestRouting(unittest.TestCase):
    def test_routing(self):
        receipt = RoutePlanner.plan_route("t1", "missing db_table")
        self.assertEqual(receipt.selected_route, "django_migration")
