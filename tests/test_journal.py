"""Exercise the journal read paths against an isolated relational fixture."""
import sqlite3
import unittest
from unittest.mock import patch

import store


class JournalReadTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE people (id INTEGER PRIMARY KEY, first TEXT, last TEXT, department TEXT);
            CREATE TABLE journal (
                id INTEGER PRIMARY KEY, person INTEGER, kind TEXT, cents INTEGER,
                at TEXT, note TEXT, terminal TEXT, request_id TEXT, reverses INTEGER, kiosk_pending INTEGER
            );
            CREATE TABLE items (
                entry INTEGER, product INTEGER, name TEXT, price INTEGER, quantity INTEGER, bonus_quantity INTEGER,
                PRIMARY KEY (entry, product)
            );
            INSERT INTO people VALUES (1, 'Gast', 'A', 'A1'), (2, 'Gast', 'B', 'B1');
            INSERT INTO journal VALUES
                (1, 1, 'purchase', -130, '2026-11-08T12:00:00+00:00', NULL, 'a', 'sale', NULL, 0),
                (51, 1, 'reversal', 130, '2026-11-08T12:00:00+00:00', 'Doppelter Kauf', 'a', NULL, 1, 0),
                (52, 2, 'purchase', -90, '2026-11-08T12:00:00+00:00', NULL, 'b', 'other', NULL, 0);
            INSERT INTO items VALUES
                (1, 5, 'Alter Kaffee', 50, 1, 0), (1, 3, 'Altes Wasser', 40, 2, 0), (52, 3, 'Anderer Einkauf', 90, 1, 0);
        """)
        self.db.executemany(
            """INSERT INTO journal
               VALUES (?, 1, 'payment', 100, '2026-11-08T12:00:00+00:00', NULL, 'a', ?, NULL, 0)""",
            [(id_, f"cash:{id_}" if id_ % 2 == 0 else f"paypal:{id_}") for id_ in range(2, 51)],
        )
        self.period = ("2026-11-01", "2026-12-01")
        cutoff = patch("store.booking_cutoff", return_value="2026-08-20T12:00:00+00:00")
        cutoff.start()
        self.addCleanup(cutoff.stop)
        self.items = [
            {"name": "Altes Wasser", "price": 40, "quantity": 2},
            {"name": "Alter Kaffee", "price": 50, "quantity": 1},
        ]
        self.statements = []

    def execute(self, query, params=()):
        self.statements.append(query)
        return self.db.execute(query.replace("%s", "?"), params)

    def test_admin_page_batches_items_and_keeps_filters_and_cursor(self):
        first = store.list_journal(self, 1, 2**63 - 1, "a")
        self.assertEqual(len(self.statements), 2)
        self.assertEqual([entry["id"] for entry in first["entries"]], list(range(51, 1, -1)))
        self.assertEqual(first["next"], 2)
        reversal, payment = first["entries"][:2]
        self.assertEqual(reversal["items"], self.items)
        self.assertEqual(reversal["note"], "Doppelter Kauf")
        self.assertEqual(reversal["reverses"], 1)
        self.assertEqual(payment["items"], [])
        self.assertNotIn("request_id", payment)
        self.assertNotIn("kiosk_pending", payment)

        second = store.list_journal(self, 1, first["next"], "a")
        self.assertIsNone(second["next"])
        self.assertEqual(len(second["entries"]), 1)
        sale = second["entries"][0]
        self.assertEqual((sale["id"], sale["reversed_by"], sale["items"]), (1, 51, self.items))
        other = store.list_journal(self, None, 2**63 - 1, "b")
        self.assertEqual([entry["id"] for entry in other["entries"]], [52])
        self.statements.clear()
        self.assertEqual(store.list_journal(self, 1, 2**63 - 1, "b"), {"entries": [], "next": None})
        self.assertEqual(len(self.statements), 1)

    def test_personal_page_batches_items_and_keeps_cursor_and_payment_methods(self):
        first = store.personal_history(self, 1, *self.period, None)
        self.assertEqual(len(self.statements), 2)
        self.assertEqual([entry["id"] for entry in first["entries"]], list(range(51, 1, -1)))
        self.assertEqual(first["next"], 2)
        self.assertEqual(first["entries"][0]["items"], self.items)
        self.assertEqual([entry["method"] for entry in first["entries"][1:3]], ["Bar", "PayPal"])

        self.statements.clear()
        second = store.personal_history(self, 1, *self.period, first["next"])
        self.assertEqual(len(self.statements), 3)
        self.assertIsNone(second["next"])
        self.assertEqual([(entry["id"], entry["items"]) for entry in second["entries"]], [(1, self.items)])
        with self.assertRaises(store.Problem) as error:
            store.personal_history(self, 1, *self.period, 52)
        self.assertEqual(error.exception.status, 400)

    def test_reversal_still_has_amount_and_reason_after_original_expires(self):
        self.db.execute("UPDATE journal SET at='2026-08-20T12:00:00+00:00' WHERE id=1")
        reversal = store.list_journal(self, 1, 2**63 - 1, "a")["entries"][0]
        self.assertEqual(
            (reversal["kind"], reversal["cents"], reversal["note"], reversal["reverses"], reversal["items"]),
            ("reversal", 130, "Doppelter Kauf", None, []),
        )
        personal = store.personal_history(self, 1, "2026-08-01", "2026-12-01", None)
        self.assertIsNone(personal["next"])
        self.assertNotIn(1, [entry["id"] for entry in personal["entries"]])
        self.assertEqual((personal["entries"][0]["reverses"], personal["entries"][0]["items"]), (None, []))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM items WHERE entry=1").fetchone()[0], 2)
