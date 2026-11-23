"""Report output uses historical labels even if the product is hidden now."""
import unittest
from unittest.mock import Mock
import finance


class MonthlyLabelTests(unittest.TestCase):
    def report(self, rows):
        db = Mock()
        totals = Mock()
        totals.fetchone.return_value = {"gross": 400, "reversed": 200, "orders": 2}
        db.execute.side_effect = [totals, rows]
        return finance.monthly(db, "2026-01", None)

    def test_two_names_for_same_id_remain_separate(self):
        report = self.report([
            {"id": 1, "name": "Früher", "name_recorded": True, "sold": 1, "returned": 1, "net": 0},
            {"id": 1, "name": "Später", "name_recorded": True, "sold": 1, "returned": 0, "net": 200},
        ])
        self.assertEqual([p["name"] for p in report["products"]], ["Früher", "Später"])
        self.assertEqual(report["unallocated"], 0)

    def test_unrecoverable_legacy_name_is_explicitly_unknown(self):
        report = self.report([{"id": 7, "name": "", "name_recorded": False, "sold": 2, "returned": 1, "net": 200}])
        self.assertEqual(report["products"][0]["name"], "Historische Bezeichnung unbekannt (Produkt #7)")


if __name__ == "__main__":
    unittest.main()
