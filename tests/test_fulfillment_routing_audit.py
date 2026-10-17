"""Fixture tests for read-only fulfillment routing rules."""
import unittest
from scripts.fulfillment_routing_audit import audit


class RoutingAuditTests(unittest.TestCase):
    def setUp(self):
        self.good = {
            "locations": [{"id": "pod-1", "name": "POD Supplier", "shipsInventory": True, "fulfillsOnlineOrders": True}],
            "variants": [{"id": "v1", "sellable": True, "inventory_locations": ["pod-1"], "shipping_locations": ["pod-1"]}],
        }

    def test_valid_pod_routing(self):
        self.assertEqual(audit(self.good)["status"], "pass")

    def test_brand_location_is_flagged(self):
        self.good["locations"].append({"id": "brand", "name": "LEGENDARY BRANDING", "shipsInventory": True, "fulfillsOnlineOrders": True})
        self.assertIn("BRAND_LOCATION_SHIPPING_ENABLED", [x["code"] for x in audit(self.good)["issues"]])

    def test_no_shipping_origin(self):
        self.good["variants"][0]["shipping_locations"] = []
        self.assertIn("NO_ELIGIBLE_ORIGIN", [x["code"] for x in audit(self.good)["issues"]])

    def test_incomplete_does_not_pass(self):
        del self.good["variants"][0]["shipping_locations"]
        self.assertEqual(audit(self.good)["status"], "incomplete")

    def test_duplicate_variant(self):
        self.good["variants"].append(dict(self.good["variants"][0]))
        self.assertIn("DUPLICATE_VARIANT", [x["code"] for x in audit(self.good)["issues"]])


if __name__ == "__main__":
    unittest.main()
