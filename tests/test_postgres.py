"""Real PostgreSQL integration tests in disposable schemas of kostbar_test only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from io import BytesIO
import os
from threading import Barrier, Event, Thread
import unittest
from unittest.mock import patch
import uuid
from xml.etree import ElementTree
from zipfile import ZipFile

import finance
import policy_documents
import schema_migrations as schema
import server
import store

DSN = os.environ.get("KOSTBAR_TEST_DSN")


@unittest.skipUnless(DSN, "Use the isolated docker-compose.test.yml stack for PostgreSQL tests")
class PostgreSQLTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg.rows import dict_row
        self.psycopg = psycopg
        self.rows = dict_row
        with psycopg.connect(DSN, autocommit=True) as db:
            if not db.info.dbname.startswith("kostbar_test"):
                raise RuntimeError("Integration tests require a dedicated database named kostbar_test*.")
            self.namespace = "kostbar_test_" + uuid.uuid4().hex
            db.execute('CREATE SCHEMA "' + self.namespace + '"')
        @contextmanager
        def connect(source=None, snapshot=False):
            with psycopg.connect(DSN, row_factory=dict_row,
                                 options=f"-c search_path={self.namespace} -c lock_timeout=3500 -c statement_timeout=5000") as db:
                if snapshot:
                    db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                yield db
        self.connect = connect
        self.config = {
            "origin": "https://kostbar.internal.lan:18443", "card_key": "ab" * 32,
            "terms": {"version": "test-v35", "contact_name": "Test", "contact_reach": "Test"},
            "terminals": {key: {"label": "Test " + key, "token": key * 43} for key in ("a", "b")},
        }
        self.factory = patch("store.connect", connect)
        self.factory.start()

    def tearDown(self):
        self.factory.stop()
        with self.psycopg.connect(DSN, autocommit=True) as db:
            db.execute('DROP SCHEMA "' + self.namespace + '" CASCADE')

    def initialize(self):
        store.initialize({}, ("a", "b"), policy_documents.terms_document(self.config))

    def person(self, db, card="synthetic-test-card"):
        return db.execute("INSERT INTO people (card,first,last,department,created) VALUES (%s,'Test','Person','R1',%s) RETURNING id",
                          (card, store.now())).fetchone()["id"]

    def test_fresh_database_migrates_and_repeated_start_is_unchanged(self):
        self.initialize()
        with self.connect() as db:
            person = self.person(db)
            before = schema.schema_status(db)
        self.initialize()
        with self.connect() as db:
            self.assertEqual(schema.schema_status(db), before)
            self.assertEqual(db.execute("SELECT first FROM people WHERE id=%s", (person,)).fetchone()["first"], "Test")

    def test_radius_notices_update_a_published_v38_document_once(self):
        previous = server.App({}, self.config)
        old_terms_body = store.terms_body(previous.terms).replace(
            policy_documents.TERMINAL_WIFI_NOTICE, policy_documents.LEGACY_TERMINAL_WIFI_NOTICE
        ) + "\n\n## Eigener Hinweis\nDie lokalen Kontaktdaten bleiben erhalten."
        old_privacy_body = "## Eigener Datenschutzhinweis\nDie lokalen Angaben bleiben erhalten."
        with self.connect() as db:
            old_terms = store.publish_terms(db, old_terms_body, "test", previous.terms)
            old_privacy = {**previous.privacy, "version": "privacy-v38", "template": False, "body": old_privacy_body}
            store.publish_privacy(db, old_privacy, "test", previous.privacy)
            db.execute("DELETE FROM settings WHERE key IN ('terminal_wifi_notice_v2', 'terminal_wifi_privacy_notice_v1')")

        upgraded = server.App({}, self.config)
        new_body = store.terms_body(upgraded.terms)
        self.assertEqual(new_body.count("## Netzzugang der Terminals"), 1)
        self.assertEqual(new_body, old_terms_body.replace(policy_documents.LEGACY_TERMINAL_WIFI_NOTICE,
                                                         policy_documents.TERMINAL_WIFI_NOTICE))
        self.assertNotEqual(upgraded.terms["version"], old_terms["version"])
        self.assertEqual(upgraded.privacy["body"],
                         old_privacy_body + "\n\n## Netzzugang der Terminals\n" + policy_documents.TERMINAL_WIFI_PRIVACY_NOTICE)
        repeated = server.App({}, self.config)
        self.assertEqual(repeated.terms, upgraded.terms)
        self.assertEqual(repeated.privacy, upgraded.privacy)
        with self.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) AS total FROM terms_versions WHERE version=%s",
                                        (old_terms["version"],)).fetchone()["total"], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) AS total FROM privacy_versions WHERE version=%s",
                                        (old_privacy["version"],)).fetchone()["total"], 1)

    def test_unversioned_v35_schema_keeps_accounts_and_balances(self):
        with self.connect() as db:
            db.execute(schema.SCHEMA, prepare=False)
            person = self.person(db)
            db.execute("INSERT INTO journal (person,kind,cents,at) VALUES (%s,'payment',1250,%s)", (person, store.now()))
            db.execute("INSERT INTO manual_credentials VALUES (%s,%s)", (person, "existing-pin-hash"))
            db.execute("INSERT INTO terminals (id) VALUES ('a')")
            db.execute("INSERT INTO kiosk_devices VALUES ('a','browser-digest','reader-digest')")
        self.initialize()
        with self.connect() as db:
            self.assertEqual(store.balance(db, person), 1250)
            self.assertEqual(db.execute("SELECT pin_hash FROM manual_credentials").fetchone()["pin_hash"], "existing-pin-hash")
            self.assertEqual(db.execute("SELECT browser_digest FROM kiosk_devices").fetchone()["browser_digest"], "browser-digest")
            self.assertEqual(schema.schema_status(db)[0]["version"], 1)

    def test_incompatible_unversioned_database_is_not_stamped(self):
        with self.connect() as db:
            db.execute(schema.SCHEMA, prepare=False)
            person = self.person(db)
            db.execute("ALTER TABLE people DROP COLUMN department")
        with self.assertRaises(schema.MigrationError):
            self.initialize()
        with self.connect() as db:
            self.assertEqual(schema.schema_status(db), [])
            self.assertIsNotNone(db.execute("SELECT id FROM people WHERE id=%s", (person,)).fetchone())

    def test_later_alter_migration_and_history_are_atomic(self):
        self.initialize()
        plan = (*schema.MIGRATIONS, schema.Migration(schema.LATEST_VERSION + 1, "test_alter", "ALTER TABLE people ADD COLUMN test_marker TEXT DEFAULT 'kept'"))
        with self.connect() as db:
            person = self.person(db)
            self.assertEqual(schema.migrate(db, plan), schema.LATEST_VERSION + 1)
        with self.connect() as db:
            self.assertEqual(db.execute("SELECT test_marker FROM people WHERE id=%s", (person,)).fetchone()["test_marker"], "kept")
            self.assertEqual(len(schema.schema_status(db)), schema.LATEST_VERSION + 1)
        with self.assertRaises(schema.MigrationError):
            self.initialize()

    def test_failed_migration_rolls_back_schema_and_version(self):
        self.initialize()
        plan = (*schema.MIGRATIONS, schema.Migration(schema.LATEST_VERSION + 1, "fails", "ALTER TABLE people ADD COLUMN should_rollback TEXT; SELECT nonexistent_kostbar_function();"))
        with self.assertRaises(self.psycopg.Error), self.connect() as db:
            schema.migrate(db, plan)
        with self.connect() as db:
            self.assertEqual(len(schema.schema_status(db)), schema.LATEST_VERSION)
            self.assertIsNone(db.execute("SELECT 1 FROM information_schema.columns WHERE table_schema=%s AND table_name='people' AND column_name='should_rollback'",
                                         (self.namespace,)).fetchone())

    def test_changed_checksum_is_refused(self):
        self.initialize()
        with self.connect() as db:
            db.execute("UPDATE schema_migrations SET checksum='tampered'")
        with self.assertRaises(schema.MigrationError):
            self.initialize()

    def test_purchase_retry_only_debits_once_and_rejects_another_cart(self):
        self.initialize()
        with self.connect() as db:
            person = self.person(db)
            product = store.available_products(db, "a")[0]
            cart = [(product["id"], 2, product["cents"])]
            first = store.purchases(db, person, "1" * 32, cart, "a")
            repeated = store.purchases(db, person, "1" * 32, cart, "a")
            self.assertEqual(first["entry"], repeated["entry"])
            self.assertEqual(store.balance(db, person), -2 * product["cents"])
            with self.assertRaises(store.Problem):
                store.purchases(db, person, "1" * 32, [(product["id"], 3, product["cents"])], "a")

    def test_receipt_retry_keeps_original_purchase_after_catalog_change(self):
        app = server.App({}, self.config)
        terminal = app.terminals["a"]
        with self.connect() as db:
            person = self.person(db)
            store.accept_policies(db, person, app.version, app.privacy["version"], terminal.id)
            db.execute("INSERT INTO manual_credentials (person,pin_hash) VALUES (%s,'fixture')", (person,))
            product = store.available_products(db, terminal.id)[0]
        terminal.kiosk = {"token": "browser", "seen": server.monotonic()}
        app.clear_kiosk(terminal)
        terminal.kiosk.update(stage="shop", user=person, visit="visit", card="synthetic-test-card",
                              until=server.monotonic() + 15)
        line = {"id": product["id"], "qty": 2, "cents": product["cents"]}
        body = {"visit": "visit", "request": "1" * 32, "lines": [line]}

        def checkout(payload):
            result, _ = app.kiosk_route(terminal, "POST", "/api/kiosk/checkout", payload, {"kk_kiosk": "browser"})
            return result["receipt"]

        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with patch("store.now", return_value=stamp):
            original_receipt = checkout(body)
        with self.connect() as db:
            db.execute("UPDATE products SET name='Neuer Name',cents=cents+100 WHERE id=%s", (product["id"],))
        self.assertEqual(checkout(body), original_receipt)
        with self.assertRaises(store.Problem) as error:
            checkout({**body, "lines": [{**line, "qty": 3}]})
        self.assertEqual(error.exception.status, 409)
        with self.connect() as db:
            self.assertEqual(store.balance(db, person), -2 * product["cents"])
            self.assertEqual(db.execute("SELECT COUNT(*) AS total FROM journal").fetchone()["total"], 1)
            item = db.execute("SELECT name,price,quantity FROM items").fetchone()
            self.assertEqual(item, {"name": product["name"], "price": product["cents"], "quantity": 2})
            report = finance.monthly(db, finance.local_date(stamp).strftime("%Y-%m"), terminal.id)
            self.assertEqual((report["orders"], report["gross"]), (1, 2 * product["cents"]))
            self.assertEqual(len(report["products"]), 1)
            self.assertEqual((report["products"][0]["name"], report["products"][0]["sold"]), (product["name"], 2))

    def test_loyalty_upgrade_keeps_old_bookings_without_backfilling_stamps(self):
        with self.connect() as db:
            schema.migrate(db, schema.MIGRATIONS[:2])
            person = self.person(db)
            db.execute("INSERT INTO terminals (id) VALUES ('a')")
            product = db.execute(
                "INSERT INTO products (category,name,cents,icon) VALUES ('hot','Kaffee',50,'coffee') RETURNING id"
            ).fetchone()["id"]
            booking = db.execute("""INSERT INTO journal (person,kind,cents,terminal,at)
                                    VALUES (%s,'purchase',-500,'a',%s) RETURNING id""",
                                 (person, store.now())).fetchone()["id"]
            db.execute("INSERT INTO items VALUES (%s,%s,'Alter Kaffee',50,10)", (booking, product))
            previous = {"version": "custom", "date": "2026-01-01", "body": "Eigener Datenschutzhinweis", "template": False}
            store.publish_privacy(db, previous, "test", previous)

        app = server.App({}, self.config)
        self.assertIn(previous["body"], app.privacy["body"])
        self.assertIn(policy_documents.LOYALTY_PRIVACY_NOTICE, app.privacy["body"])
        self.assertIn(policy_documents.LOYALTY_ADMIN_PRIVACY_NOTICE, app.privacy["body"])
        self.assertNotEqual(app.privacy["version"], previous["version"])
        self.assertEqual(server.App({}, self.config).privacy, app.privacy)
        with self.connect() as db:
            self.assertEqual([row["name"] for row in schema.schema_status(db)][2:4], ["coffee_loyalty", "loyalty_redemptions"])
            self.assertEqual(store.balance(db, person), -500)
            self.assertEqual(store.loyalty_card(db, person)["stamps"], 0)
            self.assertEqual(store.purchase_bonus(db, booking), [])
            self.assertEqual(db.execute("SELECT COUNT(*) AS n FROM privacy_versions WHERE version='custom'").fetchone()["n"], 1)

    def test_admin_loyalty_overview_backfills_v34_bonus_but_excludes_reversals(self):
        with self.connect() as db:
            schema.migrate(db, schema.MIGRATIONS[:3])
            db.execute("INSERT INTO terminals (id) VALUES ('a')")
            person = self.person(db, "progress")
            empty = self.person(db, "empty")
            no_card_row = self.person(db, "full-cart")
            db.execute("INSERT INTO loyalty_cards VALUES (%s,4)", (person,))
            product = db.execute(
                "INSERT INTO products (category,name,cents,icon) VALUES ('hot','Kaffee',50,'coffee') RETURNING id"
            ).fetchone()["id"]
            for account, quantity, bonus, total, delta in (
                (person, 2, 2, 0, -20), (person, 1, 1, 0, -10), (no_card_row, 11, 1, -500, 0)
            ):
                purchase = store.entry(db, account, "purchase", total, loyalty_delta=delta, terminal="a")
                db.execute("INSERT INTO items VALUES (%s,%s,'Kaffee',50,%s,%s)", (purchase, product, quantity, bonus))
                if account == person and bonus == 1:
                    store.entry(db, account, "reversal", 0, reverses=purchase, loyalty_delta=10, terminal="a")
            db.execute("INSERT INTO admins (name,password) VALUES ('cashier','test')")
        app = server.App({}, self.config)
        app.admins["test-session"] = {"name": "cashier", "password": "test", "super_admin": False,
                                      "until": float("inf"), "max": float("inf")}

        def overview():
            result, _ = app.route(None, "GET", "/api/admin/overview", {}, {}, {"kk_admin": "test-session"})
            return {row["id"]: row["loyalty"] for row in result["people"]}

        cards = overview()
        self.assertEqual((cards[person]["stamps"], cards[person]["target"], cards[person]["redeemed"]), (4, 10, 2))
        self.assertEqual((cards[empty]["stamps"], cards[empty]["redeemed"]), (0, 0))
        self.assertEqual((cards[no_card_row]["stamps"], cards[no_card_row]["redeemed"]), (0, 1))
        self.initialize()
        self.assertEqual(overview(), cards)

    def test_loyalty_redemptions_remain_after_cleanup_when_progress_delta_is_zero(self):
        self.initialize()
        clock = datetime.now(timezone.utc)
        with self.connect() as db:
            person = self.person(db)
            product = next(p for p in store.available_products(db, "a") if p["category"] == "hot")
            with patch("store.now", return_value=(clock - timedelta(days=91)).isoformat()):
                store.purchases(db, person, "6" * 32, [(product["id"], 11, product["cents"])], "a")
            store.expire_booking_details(db, clock, b"test")
            card = store.people_overview(db, "test")[0]["loyalty"]
            self.assertEqual((card["stamps"], card["redeemed"]), (0, 1))
            self.assertEqual(db.execute("SELECT COUNT(*) AS n FROM journal").fetchone()["n"], 0)

    def test_loyalty_bonus_mixed_cart_is_exactly_once_and_reports_only_charged_amounts(self):
        self.initialize()
        with self.connect() as db:
            person = self.person(db)
            products = store.available_products(db, "a")
            coffee, cappuccino = [p for p in products if p["category"] == "hot"][:2]
            water = next(p for p in products if p["category"] == "cold")
            db.execute("UPDATE products SET cents=90 WHERE id=%s", (cappuccino["id"],))
            cart = [(cappuccino["id"], 2, 90), (water["id"], 2, water["cents"]), (coffee["id"], 20, coffee["cents"])]
            quote = store.purchase_pricing(db, person, cart, "a")
            self.assertEqual(quote["discount"], 2 * coffee["cents"])
            result = store.purchases(db, person, "9" * 32, cart, "a", quoted_discount=quote["discount"])
            self.assertEqual(result["bonus"], [{"name": coffee["name"], "qty": 2, "price": coffee["cents"]}])
            self.assertEqual(result["total"], quote["total"])
            self.assertEqual(result["stamps_earned"], 20)
            self.assertEqual(store.loyalty_card(db, person)["stamps"], 0)
            self.assertEqual(store.purchases(db, person, "9" * 32, cart[::-1], "a"), result)
            self.assertEqual(store.people_overview(db, "test")[0]["loyalty"]["redeemed"], 2)
            with self.assertRaises(store.Problem):
                store.purchases(db, person, "9" * 32, cart, "a", quoted_discount=0)
            self.assertEqual(store.balance(db, person), -quote["total"])
            month, start, end = finance.month_bounds(None)
            items = store.personal_history(db, person, start, end, None)["entries"][0]["items"]
            self.assertEqual(next(item for item in items if item["name"] == coffee["name"])["bonus_quantity"], 2)
            report = finance.monthly(db, month, "a")
            self.assertEqual(report["gross"], quote["total"])
            self.assertEqual(sum(p["net"] for p in report["products"]), quote["total"])
            self.assertEqual(next(p for p in report["products"] if p["id"] == coffee["id"])["sold"], 20)
            output = finance.account_export(db, person, {"a": "Test A"}, datetime.now(timezone.utc))
            with ZipFile(BytesIO(output.content)) as book:
                self.assertIn("Sammelkartenbonus", book.read("xl/sharedStrings.xml").decode())

    def test_loyalty_stale_quote_cannot_charge_second_terminal(self):
        app = server.App({}, self.config)
        with self.connect() as db:
            person = self.person(db)
            store.accept_policies(db, person, app.version, app.privacy["version"], "a")
            product = next(p for p in store.available_products(db, "a") if p["category"] == "hot")
            store.update_loyalty(db, person, 10)
            db.execute("INSERT INTO manual_credentials VALUES (%s,'fixture')", (person,))
        line = {"id": product["id"], "qty": 1, "cents": product["cents"]}
        cookie = {"kk_kiosk": "browser"}

        def kiosk(site, operation, **body):
            return app.kiosk_route(app.terminals[site], "POST", "/api/kiosk/" + operation,
                                   {"visit": site, **body}, cookie)[0]

        for site, terminal in app.terminals.items():
            terminal.kiosk = {"token": "browser", "seen": server.monotonic()}
            app.clear_kiosk(terminal)
            terminal.kiosk.update(stage="shop", user=person, visit=site, card="synthetic-test-card",
                                  until=server.monotonic() + 15)
        first_quote = kiosk("a", "checkout-quote", lines=[line])
        second_quote = kiosk("b", "checkout-quote", lines=[line])
        self.assertEqual((first_quote["total"], second_quote["total"]), (0, 0))
        first = kiosk("a", "checkout", request="a" * 32, lines=[line], discount=first_quote["discount"])
        self.assertEqual(first["receipt"]["total"], 0)
        recovered = app.state(app.terminals["b"])["booking"]
        self.assertEqual(recovered["bonus"], first["receipt"]["bonus"])
        kiosk("a", "booking-seen", kind="purchase", request="a" * 32)
        with self.assertRaisesRegex(store.Problem, "Sammelkarte hat sich geändert"):
            kiosk("b", "checkout", request="b" * 32, lines=[line], discount=second_quote["discount"])
        self.assertEqual(kiosk("b", "checkout-quote", lines=[line])["total"], product["cents"])
        with self.connect() as db:
            self.assertEqual(store.balance(db, person), 0)
            self.assertEqual(store.loyalty_card(db, person)["stamps"], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) AS n FROM journal").fetchone()["n"], 1)

    def test_loyalty_retention_and_reversal_of_a_zero_euro_purchase(self):
        app = server.App({}, self.config)
        clock = datetime.now(timezone.utc)
        with self.connect() as db:
            person = self.person(db)
            product = next(p for p in store.available_products(db, "a") if p["category"] == "hot")
            with patch("store.now", return_value=(clock - timedelta(days=91)).isoformat()):
                original = store.purchases(db, person, "7" * 32, [(product["id"], 10, product["cents"])], "a")
            store.expire_booking_details(db, clock, app.key)
            self.assertIsNone(db.execute("SELECT id FROM journal WHERE id=%s", (original["entry"],)).fetchone())
            self.assertEqual(store.loyalty_card(db, person)["ready"], 1)
            self.assertEqual(store.balance(db, person), -10 * product["cents"])
            reward = store.purchases(db, person, "8" * 32, [(product["id"], 1, product["cents"])], "b")
            db.execute("INSERT INTO admins (name,password) VALUES ('cashier','test')")
        app.admins["test-session"] = {"name": "cashier", "password": "test", "super_admin": False,
                                      "until": float("inf"), "max": float("inf")}
        self.assertEqual(reward["total"], 0)
        app.admin_route("POST", "/api/admin/reverse", {}, {"id": reward["entry"], "note": "Teststorno"},
                        {"kk_admin": "test-session"}, None)
        with self.connect() as db:
            reverse = db.execute("SELECT cents FROM journal WHERE reverses=%s", (reward["entry"],)).fetchone()
            self.assertEqual(reverse["cents"], 0)
            self.assertEqual(store.loyalty_card(db, person)["ready"], 1)
            self.assertEqual(store.balance(db, person), -10 * product["cents"])
            self.assertEqual(store.people_overview(db, "test")[0]["loyalty"]["redeemed"], 0)
            month, _, _ = finance.month_bounds(None)
            report = finance.monthly(db, month, "b")
            self.assertEqual((report["gross"], report["reversed"]), (0, 0))
            self.assertEqual((report["products"][0]["sold"], report["products"][0]["returned"]), (1, 1))
            store.entry(db, person, "payment", 10 * product["cents"])
            db.execute("UPDATE people SET active=0,closed_at=%s WHERE id=%s", (clock, person))
            store.expire_booking_details(db, clock + timedelta(days=91), app.key)
            self.assertIsNone(db.execute("SELECT id FROM people WHERE id=%s", (person,)).fetchone())
            self.assertIsNone(db.execute("SELECT person FROM loyalty_cards WHERE person=%s", (person,)).fetchone())

    def test_product_status_preserves_edits_and_historical_purchase(self):
        app = server.App({}, self.config)
        with self.connect() as db:
            person = self.person(db)
            original = store.available_products(db, "a")[0]
            store.purchases(db, person, "2" * 32, [(original["id"], 1, original["cents"])], "a")
            db.execute("INSERT INTO admins (name,password) VALUES ('editor','edit-hash'),('archiver','archive-hash')")
        app.admins["edit-session"] = {"name": "editor", "password": "edit-hash", "super_admin": False,
                                      "until": float("inf"), "max": float("inf")}
        app.admins["archive-session"] = {"name": "archiver", "password": "archive-hash", "super_admin": False,
                                         "until": float("inf"), "max": float("inf")}
        product = original["id"]

        def admin(path, body, session):
            return app.admin_route("POST", "/api/admin/" + path, {}, body, {"kk_admin": session}, None)

        edited = {**original, "name": "Aktueller Name", "cents": 175, "terminals": ["b"], "active": True}
        admin("product", edited, "edit-session")
        status = {"id": product, "active": False}
        admin("product-status", status, "archive-session")
        admin("product-status", status, "archive-session")
        with self.connect() as db:
            self.assertFalse(any(p["id"] == product for p in store.available_products(db, "a")))
            self.assertFalse(any(p["id"] == product for p in store.available_products(db, "b")))
        admin("product-status", {**status, "active": True}, "archive-session")
        with self.connect() as db:
            self.assertFalse(any(p["id"] == product for p in store.available_products(db, "a")))
            saved = next(p for p in store.available_products(db, "b") if p["id"] == product)
            self.assertEqual((saved["name"], saved["cents"]), ("Aktueller Name", 175))
            entry = store.list_journal(db, person, 2**63-1)["entries"][0]
            self.assertEqual(entry["items"], [{"name": original["name"], "price": original["cents"], "quantity": 1}])
            audit = [row for row in store.list_audit(db, 2**63-1)["entries"] if row["actor"] == "archiver"]
            self.assertEqual(len(audit), 2)
            self.assertEqual([row["new_state"]["Status"] for row in audit], ["Aktiv", "Archiviert"])
            for row in audit:
                self.assertEqual(row["new_state"], {**row["old_state"], "Status": row["new_state"]["Status"]})
        with self.assertRaises(store.Problem) as denied:
            admin("delete-product", {"id": product}, "edit-session")
        self.assertEqual(denied.exception.status, 403)
        with self.connect() as db:
            self.assertTrue(any(p["id"] == product for p in store.available_products(db, "b")))
        self.feature_admin(app, "super", True)
        admin("delete-product", {"id": product}, "super")
        with self.assertRaises(store.Problem) as error:
            admin("product-status", {**status, "active": True}, "archive-session")
        self.assertEqual(error.exception.status, 404)

    def test_cash_retry_does_not_credit_twice(self):
        self.initialize()
        with self.connect() as db:
            person = self.person(db)
            first = finance.cash(db, person, "a", "2" * 32, 500)
            repeated = finance.cash(db, person, "a", "2" * 32, 500)
            self.assertEqual(first["entry"], repeated["entry"])
            self.assertEqual(store.balance(db, person), 500)
            with self.assertRaises(store.Problem):
                finance.cash(db, person, "a", "2" * 32, 1000)

    def test_real_admin_retry_checks_payload_and_keeps_one_booking(self):
        app = server.App({}, self.config)
        with self.connect() as db:
            person = self.person(db)
            db.execute("INSERT INTO admins (name,password) VALUES ('tester','test-hash')")
        app.admins["session"] = {"name": "tester", "password": "test-hash", "super_admin": False,
                                 "until": float("inf"), "max": float("inf")}
        body = {"id": person, "kind": "payment", "cents": 500, "note": "Test", "request": "3" * 32}
        def call(payload):
            return app.admin_route("POST", "/api/admin/adjust", {}, payload, {"kk_admin": "session"}, None)
        call(body)
        call(body)
        with self.assertRaises(store.Problem) as error:
            call({**body, "cents": 1000})
        self.assertEqual(error.exception.status, 409)
        with self.connect() as db:
            self.assertEqual(store.balance(db, person), 500)
            self.assertEqual(db.execute("SELECT COUNT(*) AS total FROM journal").fetchone()["total"], 1)

    def test_new_terminal_retains_its_profile_and_coupling_across_restart(self):
        app = server.App({}, self.config)
        old = app.terminals["a"].secret
        profile_id = "etage-2"
        admin = self.feature_admin(app, "tester", True)
        terminal = {"id": profile_id, "label": "Etage 2"}
        created, _ = app.route(None, "POST", "/api/admin/terminal-create", {}, terminal, admin)
        self.assertEqual(created, terminal)
        with self.assertRaises(store.Problem) as duplicate:
            app.route(None, "POST", "/api/admin/terminal-create", {}, terminal, admin)
        self.assertEqual(duplicate.exception.status, 409)
        download, _ = app.route(None, "GET", "/api/admin/terminal-profile", {"terminal": [profile_id]}, {}, admin)
        self.assertEqual(download.name, "terminal-etage-2.json")
        with self.connect() as db:
            self.assertEqual(store.available_products(db, profile_id), [])
        instance = "c" * 64
        site = app.terminals[profile_id]
        app.route(site, "POST", "/internal/reader", {}, {"instance": instance, "connected": True}, {})
        pairing, cookie = app.route(None, "POST", "/api/kiosk/pair", {}, {"instance": instance}, {})
        app.route(None, "POST", "/api/admin/kiosk-pair", {}, {"id": profile_id, "code": pairing["code"]}, admin)
        secret = cookie.partition("=")[2].split(";")[0]
        paired, _ = app.route(None, "POST", "/api/kiosk/pair", {}, {}, {server.PAIR_COOKIE: secret})
        self.assertEqual(paired, {"paired": True})
        restarted = server.App({}, self.config)
        self.assertEqual(restarted.terminals["a"].secret, old)
        self.assertEqual(restarted.terminals[profile_id].secret, site.secret)
        self.assertEqual(restarted.browser_terminal({server.DEVICE_COOKIE: secret}).id, profile_id)

    def feature_admin(self, app, name, super_admin):
        with self.connect() as db:
            db.execute("INSERT INTO admins (name,password,super_admin) VALUES (%s,'test-hash',%s)",
                       (name, int(super_admin)))
        app.admins[name] = {"name": name, "password": "test-hash", "super_admin": super_admin,
                            "until": float("inf"), "max": float("inf")}
        return {"kk_admin": name}

    def test_admin_account_pages_sort_across_pages_and_keep_global_balances(self):
        app = server.App({}, self.config)
        admin = self.feature_admin(app, "cashier", False)
        with self.connect() as db:
            db.execute("""INSERT INTO people (card,first,last,department,created)
                          SELECT 'test-card-' || n, 'Anna', 'Ährens', 'R ' || n, %s
                          FROM generate_series(1, 120) n""", (store.now(),))
            person = db.execute("SELECT id FROM people WHERE department='R 2'").fetchone()["id"]
            store.accept_policies(db, person, app.version, app.privacy["version"], "a")
            db.execute("INSERT INTO carried_balances (person,cents) VALUES (%s,-700)", (person,))
            store.entry(db, person, "payment", 200)
            db.execute("""UPDATE people SET active=0,closed_at=%s WHERE department='R 3'""", (store.now(),))
            credit = db.execute("SELECT id FROM people WHERE department='R 120'").fetchone()["id"]
            store.entry(db, credit, "payment", 900)

        def read(endpoint, **query):
            return app.route(None, "GET", "/api/admin/" + endpoint,
                             {key: [str(value)] for key, value in query.items()}, {}, admin)[0]

        self.assertEqual(read("summary"), {"outstanding": 500, "credit": 900, "active": 119})
        self.assertNotIn("people", read("sites"))
        self.assertNotIn("people", read("products"))
        first = read("people", sort="department", search="ANNA ährens")
        second = read("people", sort="department", page=2)
        final = read("people", sort="department", page=3)
        self.assertEqual([len(result["people"]) for result in (first, second, final)], [50, 50, 20])
        self.assertEqual([row["department"] for result in (first, second, final) for row in result["people"]],
                         [f"R {number}" for number in range(1, 121)])
        self.assertTrue(first["has_next"])
        self.assertFalse(final["has_next"])
        self.assertTrue(first["people"][1]["terms_current"])
        self.assertNotIn("consents", first["people"][1])
        self.assertNotIn("card", first["people"][1])
        self.assertEqual(read("people", sort="balance")["people"][0]["balance"], -500)
        self.assertEqual(read("people", sort="balance", direction="descending")["people"][0]["balance"], 900)
        self.assertEqual(read("people", search="%")["people"], [])
        with ZipFile(BytesIO(read("export-balances").content)) as workbook:
            self.assertIn("R 120", workbook.read("xl/sharedStrings.xml").decode())
        options = read("account-options", search="ährens r 120")
        self.assertEqual(options["people"], [{"id": credit, "first": "Anna", "last": "Ährens", "department": "R 120"}])
        self.assertEqual(len(read("account-options", page=2)["people"]), 50)
        with self.assertRaises(store.Problem) as invalid:
            read("people", sort="created")
        self.assertEqual(invalid.exception.status, 400)

    def test_admin_journal_hides_reversal_rows_by_default(self):
        app = server.App({}, self.config)
        admin = self.feature_admin(app, "cashier", False)
        with self.connect() as db:
            person = self.person(db)
            purchase = store.entry(db, person, "purchase", -150, terminal="a")
            reversal = store.entry(db, person, "reversal", 150, reverses=purchase, terminal="a")

        def journal(query):
            return app.route(None, "GET", "/api/admin/journal", query, {}, admin)[0]["entries"]

        hidden = journal({})
        self.assertEqual([(entry["id"], entry["reversed_by"]) for entry in hidden], [(purchase, reversal)])
        self.assertEqual([entry["id"] for entry in journal({"reversals": ["1"]})], [reversal, purchase])
        self.assertEqual([entry["id"] for entry in journal({"reversals": ["0"]})], [purchase])
        export, _ = app.route(None, "GET", "/api/admin/export-account", {"person": [str(person)]}, {}, admin)
        with ZipFile(BytesIO(export.content)) as workbook:
            self.assertIn("Storno", workbook.read("xl/sharedStrings.xml").decode())
        with self.connect() as db:
            self.assertEqual(store.balance(db, person), 0)

    def test_closing_an_account_ends_kiosk_session_only_after_commit(self):
        app = server.App({}, self.config)
        admin = self.feature_admin(app, "cashier", False)
        with self.connect() as db:
            person = self.person(db)
            db.execute("INSERT INTO manual_credentials VALUES (%s,%s)", (person, "test-pin-hash"))
        terminal = app.terminals["a"]
        terminal.kiosk = {"stage": "shop", "user": person}
        terminal.capture = {"person": person}

        def close_account():
            return app.route(None, "POST", "/api/admin/close-account", {}, {"id": person}, admin)

        with patch("store.audit", side_effect=RuntimeError("synthetic audit failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic audit failure"):
                close_account()
        with self.connect() as db:
            self.assertIsNone(db.execute("SELECT closed_at FROM people WHERE id=%s", (person,)).fetchone()["closed_at"])
            self.assertIsNotNone(db.execute("SELECT 1 FROM manual_credentials WHERE person=%s", (person,)).fetchone())
        self.assertEqual(terminal.kiosk["stage"], "shop")
        self.assertIsNotNone(terminal.capture)

        clear_kiosk = app.clear_kiosk

        def check_committed(site, notice):
            with self.connect() as db:
                self.assertIsNotNone(db.execute("SELECT closed_at FROM people WHERE id=%s", (person,)).fetchone()["closed_at"])
                self.assertIsNone(db.execute("SELECT 1 FROM manual_credentials WHERE person=%s", (person,)).fetchone())
            clear_kiosk(site, notice)

        with patch.object(app, "clear_kiosk", side_effect=check_committed) as invalidation:
            self.assertEqual(close_account(), ({}, None))
        invalidation.assert_called_once()
        self.assertEqual(terminal.kiosk["stage"], "idle")
        self.assertIsNone(terminal.capture)

    def test_manually_created_account_requires_policies_card_and_new_pin(self):
        app = server.App({}, {**self.config, "self_registration": False})
        admin = self.feature_admin(app, "cashier", False)
        path = "/api/admin/person-create"
        start_pin = {"pin": "0123", "pin_confirmation": "0123"}
        enrollment = {"first": "Lena", "last": "Beispiel", "department": "R2", **start_pin}
        with self.assertRaises(store.Problem) as auth:
            app.route(None, "POST", path, {}, enrollment, {})
        self.assertEqual(auth.exception.status, 401)
        person = app.route(None, "POST", path, {}, enrollment, admin)[0]["id"]
        target = app.terminals["a"]
        target.kiosk = {"token": "browser", "seen": server.monotonic()}
        app.clear_kiosk(target)
        uid, used_uid = "04030201", "04030202"
        with self.connect() as db:
            self.person(db, app.card_digest(used_uid))
            account = app.account(db, person=person)
            self.assertIsNone(account["card"])
            self.assertTrue(account["pin_temporary"])
            self.assertFalse(account["accepted"])
            self.assertNotEqual(account["pin_hash"], start_pin["pin"])
            audit = db.execute("SELECT new_state FROM audit WHERE person=%s", (person,)).fetchone()
            self.assertNotIn(start_pin["pin"], audit["new_state"])

        def post(action, values=None):
            return app.kiosk_route(target, "POST", "/api/kiosk/" + action,
                                   {"visit": target.kiosk["visit"], **(values or {})}, {"kk_kiosk": "browser"})[0]

        def scan(card):
            target.kiosk["seen"] = server.monotonic()
            app.scan(target, card)

        post("manual-start")
        self.assertEqual(post("manual-search", {"query": "Beispiel"})["people"][0]["id"], person)
        self.assertEqual(post("manual-login", {"id": person, "pin": start_pin["pin"]})["stage"], "consent")
        scan(uid)
        self.assertEqual(target.kiosk["stage"], "consent")
        self.assertEqual(post("accept-terms", {"accepted": True, "version": app.version,
                                              "privacy_version": app.privacy["version"]})["stage"], "card-setup")
        with self.assertRaises(store.Problem):
            post("pin-setup", {"pin": "4321", "pin_confirmation": "4321"})
        scan(used_uid)
        self.assertEqual(target.kiosk["stage"], "card-setup")
        self.assertIn("bereits zugeordnet", target.kiosk["notice"])
        scan(uid)
        self.assertEqual(target.kiosk["stage"], "pin-setup")
        post("logout")
        scan(uid)
        self.assertEqual(target.kiosk["stage"], "idle")
        post("manual-start")
        self.assertEqual(post("manual-login", {"id": person, "pin": start_pin["pin"]})["stage"], "pin-setup")
        for invalid in (start_pin, {"pin": "4321", "pin_confirmation": "1234"}):
            with self.assertRaises(store.Problem) as refused:
                post("pin-setup", invalid)
            self.assertEqual(refused.exception.status, 400)
        self.assertEqual(post("pin-setup", {"pin": "4321", "pin_confirmation": "4321"})["stage"], "shop")
        post("logout")
        post("manual-start")
        with self.assertRaises(store.Problem) as refused:
            post("manual-login", {"id": person, "pin": start_pin["pin"]})
        self.assertEqual(refused.exception.status, 401)
        self.assertEqual(post("manual-login", {"id": person, "pin": "4321"})["stage"], "shop")
        post("logout")
        scan(uid)
        self.assertEqual(target.kiosk["stage"], "shop")
        with self.connect() as db:
            row = app.account(db, person=person)
            self.assertTrue(row["accepted"])
            self.assertFalse(row["pin_temporary"])
            self.assertEqual(row["card"], app.card_digest(uid))

    def test_migration_allows_cardless_accounts_and_preserves_existing_credentials(self):
        with self.connect() as db:
            schema.migrate(db, schema.MIGRATIONS[:6])
            existing = self.person(db)
            db.execute("INSERT INTO manual_credentials (person,pin_hash) VALUES (%s,'old-hash')", (existing,))
        app = server.App({}, self.config)
        with self.connect() as db:
            self.assertEqual(schema.schema_status(db)[-1]["name"], "manual_account_setup")
            self.assertEqual(app.account(db, person=existing)["pin_hash"], "old-hash")
            self.assertFalse(app.account(db, person=existing)["pin_temporary"])
            self.assertEqual(app.account(db, person=existing)["card"], "synthetic-test-card")
        admin = self.feature_admin(app, "cashier", False)
        person = app.route(None, "POST", "/api/admin/person-create", {}, {
            "first": "Lena", "last": "Beispiel", "department": "R2", "pin": "0123", "pin_confirmation": "0123",
        }, admin)[0]["id"]
        app.route(None, "POST", "/api/admin/reset-pin", {}, {
            "id": person, "pin": "0134", "pin_confirmation": "0134",
        }, admin)
        with self.connect() as db:
            row = app.account(db, person=person)
            self.assertIsNone(row["card"])
            self.assertTrue(row["pin_temporary"])
            self.assertTrue(store.check_password(app.pin_material("0134"), row["pin_hash"]))
        with self.connect() as db, self.assertRaises(schema.MigrationError):
            schema.migrate(db, schema.MIGRATIONS[:6])

    def test_terminal_management_requires_super_admin_and_delete_keeps_history(self):
        app = server.App({}, self.config)
        admin = self.feature_admin(app, "admin", False)
        owner = self.feature_admin(app, "owner", True)
        query = {"terminal": ["a"]}
        body = {"id": "a", "label": "Neu"}
        for method, path in (("POST", "terminal-create"), ("POST", "terminal"), ("POST", "terminal-delete"),
                             ("POST", "kiosk-pair"), ("POST", "kiosk-unpair"), ("GET", "terminal-profile")):
            with self.subTest(path=path), self.assertRaises(store.Problem) as forbidden:
                app.route(None, method, "/api/admin/" + path, query, body, admin)
            self.assertEqual(forbidden.exception.status, 403)
        with self.connect() as db:
            person = self.person(db)
            booking = store.entry(db, person, "payment", 500, terminal="a")
            db.execute("INSERT INTO kiosk_devices VALUES ('a','browser','reader')")
        app.route(None, "POST", "/api/admin/terminal", {}, body, owner)
        app.route(None, "POST", "/api/admin/terminal-delete", {}, body, owner)
        with self.connect() as db:
            self.assertIsNone(db.execute("SELECT 1 FROM kiosk_devices WHERE terminal='a'").fetchone())
            self.assertEqual(store.available_products(db, "a"), [])
        restarted = server.App({}, self.config)
        restarted.admins["owner"] = app.admins["owner"]
        self.assertNotIn("a", restarted.terminals)
        self.assertEqual(restarted.historical_terminal_labels()["a"], "Neu")
        journal, _ = restarted.route(None, "GET", "/api/admin/journal", query, {}, owner)
        self.assertEqual(journal["entries"][0]["id"], booking)
        restarted.route(None, "GET", "/api/admin/report", query, {}, owner)
        with self.assertRaises(store.Problem) as conflict:
            restarted.route(None, "POST", "/api/admin/terminal-create", {}, body, owner)
        self.assertEqual(conflict.exception.status, 409)

    def test_paypal_setting_updates_live_qr_and_keeps_original_recipient_for_pending_payments(self):
        original = "https://paypal.me/Original"
        updated = "https://paypal.me/Updated"
        cfg = {**self.config, "paypal_url": original}
        with self.connect() as db:
            schema.migrate(db, schema.MIGRATIONS[:4])
            person = self.person(db)
            db.execute("INSERT INTO terminals (id) VALUES ('a')")
            db.execute("""INSERT INTO paypal_requests (person,terminal,request_id,reference,cents,created,kiosk_pending)
                          VALUES (%s,'a','legacy','KK-legacy',300,%s,FALSE)""", (person, store.now()))
        app = server.App({}, cfg)
        admin = self.feature_admin(app, "admin", False)
        owner = self.feature_admin(app, "owner", True)
        path = "/api/admin/paypal-settings"
        for method in ("GET", "POST"):
            with self.assertRaises(store.Problem) as forbidden:
                app.route(None, method, path, {}, {"link": updated}, admin)
            self.assertEqual(forbidden.exception.status, 403)
        with self.assertRaises(store.Problem) as invalid:
            app.route(None, "POST", path, {}, {"link": "https://paypal.me.example/Name"}, owner)
        self.assertEqual(invalid.exception.status, 400)
        site = app.terminals["a"]
        with self.connect() as db:
            store.accept_policies(db, person, app.version, app.privacy["version"], site.id)
            db.execute("INSERT INTO manual_credentials (person,pin_hash) VALUES (%s,'fixture')", (person,))
        site.kiosk = {"token": "browser"}
        app.clear_kiosk(site)
        site.kiosk.update(stage="shop", user=person, card="synthetic-test-card", visit="visit", until=server.monotonic() + 15)

        def kiosk(method, action, body=None, query=None):
            return app.kiosk_route(site, method, "/api/kiosk/" + action, body or {},
                                   {"kk_kiosk": "browser"}, query)[0]

        payment = {"visit": "visit", "request": "a" * 32, "cents": 500, "link": original}
        old = kiosk("POST", "paypal", payment)
        kiosk("POST", "booking-seen", {**payment, "kind": "paypal"})
        app.route(None, "POST", path, {}, {"link": updated}, owner)
        options = kiosk("GET", "payment")
        self.assertEqual(options["link"], updated)
        self.assertEqual({item["reference"]: item["link"] for item in options["pending"]},
                         {old["reference"]: original, "KK-legacy": original})
        self.assertEqual(kiosk("GET", "paypal.svg", query={"link": [updated]}), finance.paypal_qr(updated))
        self.assertEqual(kiosk("GET", "paypal.svg", query={"reference": [old["reference"]], "link": [original]}),
                         finance.paypal_qr(original))
        with self.assertRaises(store.Problem) as stale:
            kiosk("POST", "paypal", {**payment, "request": "b" * 32})
        self.assertEqual(stale.exception.status, 409)
        restarted = server.App({}, cfg)
        restarted.admins["owner"] = app.admins["owner"]
        self.assertEqual(restarted.route(None, "GET", path, {}, {}, owner)[0]["link"], updated)
        restarted.route(None, "POST", path, {}, {"link": ""}, owner)
        self.assertIsNone(kiosk("GET", "payment")["link"])
        self.assertIsNone(kiosk("GET", "payment")["pending"][0]["link"])

    def test_preview_quote_uses_live_pricing_without_booking_or_kiosk_session(self):
        app = server.App({}, self.config)
        admin = self.feature_admin(app, "admin", False)
        owner = self.feature_admin(app, "owner", True)
        query = {"terminal": ["a"]}
        catalog, _ = app.route(None, "GET", server.PREVIEW_PATH, query, {}, owner)
        self.assertEqual((catalog["receipt_seconds"], catalog["cash_receipt_seconds"]), (8, 5))
        product = next(item for item in catalog["products"] if item["category"] == "hot")
        cart = {"lines": [{"id": product["id"], "qty": 2, "cents": product["cents"]}], "progress": 9}
        with self.assertRaises(store.Problem) as forbidden:
            app.route(None, "POST", server.PREVIEW_QUOTE_PATH, query, cart, admin)
        self.assertEqual(forbidden.exception.status, 403)
        quote, _ = app.route(None, "POST", server.PREVIEW_QUOTE_PATH, query, cart, owner)
        self.assertEqual((quote["total"], quote["discount"], quote["loyalty_delta"]),
                         (product["cents"], product["cents"], -9))
        with self.connect() as db:
            self.assertEqual(db.execute("SELECT count(*) AS count FROM journal").fetchone()["count"], 0)
            self.assertEqual(db.execute("SELECT count(*) AS count FROM loyalty_cards").fetchone()["count"], 0)
        self.assertIsNone(app.terminals["a"].kiosk)

    def test_two_terminals_serialize_purchases_for_the_same_account(self):
        app = server.App({}, self.config)
        uid = "04010203"
        with self.connect() as db:
            person = self.person(db, app.card_digest(uid))
            store.accept_policies(db, person, app.version, app.privacy["version"], "a")
            db.execute("INSERT INTO manual_credentials VALUES (%s,'fixture')", (person,))
            product = store.available_products(db, "a")[0]
        requests = {}
        for terminal in app.terminals.values():
            secret = terminal.id * 64
            terminal.paired_browser = app.device_digest("browser", secret)
            terminal.kiosk = {"token": "browser", "seen": server.monotonic()}
            app.clear_kiosk(terminal)
            app.scan(terminal, uid)
            requests[terminal.id] = (
                {"visit": terminal.kiosk["visit"], "request": terminal.id * 32,
                 "lines": [{"id": product["id"], "qty": 1, "cents": product["cents"]}]},
                {"kk_kiosk": "browser", server.DEVICE_COOKIE: secret},
            )

        def buy(site):
            body, cookies = requests[site]
            return app.route(None, "POST", "/api/kiosk/checkout", {}, body, cookies)[0]

        barrier = Barrier(2)
        def concurrent_purchase(site):
            barrier.wait(timeout=3)
            try:
                return site, buy(site)["receipt"]["total"]
            except store.Problem as error:
                self.assertEqual(error.status, 409)
                return site, None

        with ThreadPoolExecutor(max_workers=2) as workers:
            results = dict(workers.map(concurrent_purchase, ("a", "b")))
        self.assertCountEqual(results.values(), [product["cents"], None])
        first = next(site for site, total in results.items() if total is not None)
        body, cookies = requests[first]
        app.route(None, "POST", "/api/kiosk/booking-seen", {},
                  {"visit": body["visit"], "request": body["request"], "kind": "purchase"}, cookies)
        second = next(site for site in results if site != first)
        self.assertEqual(buy(second)["receipt"]["total"], product["cents"])
        with self.connect() as db:
            self.assertEqual(store.balance(db, person), -2 * product["cents"])

    def test_registration_pin_login_and_admin_reset(self):
        app = server.App({}, self.config)
        terminal = app.terminals["a"]
        terminal.kiosk = {"token": "browser", "seen": server.monotonic()}
        app.clear_kiosk(terminal)
        uid = "04010203"
        cookies = {"kk_kiosk": "browser"}

        def kiosk(action, **body):
            return app.kiosk_route(terminal, "POST", "/api/kiosk/" + action,
                                   {"visit": terminal.kiosk["visit"], **body}, cookies)[0]

        app.scan(terminal, uid)
        registration = {"first": "Test", "last": "Person", "department": "R1", "pin": "0042",
                        "accepted": True, "version": app.version, "privacy_version": app.privacy["version"]}
        with self.assertRaises(store.Problem) as mismatch:
            kiosk("register", **registration, pin_confirmation="0043")
        self.assertEqual(mismatch.exception.status, 400)
        with self.connect() as db:
            self.assertIsNone(db.execute("SELECT id FROM people").fetchone())

        self.assertEqual(kiosk("register", **registration, pin_confirmation="0042")["stage"], "shop")
        person = terminal.kiosk["user"]
        with self.connect() as db:
            account = app.account(db, person=person)
            self.assertTrue(store.check_password(app.pin_material("0042"), account["pin_hash"]))
            db.execute("INSERT INTO admins (name,password) VALUES ('cashier','test')")
        app.admins["session"] = {"name": "cashier", "password": "test", "super_admin": False,
                                 "until": float("inf"), "max": float("inf")}

        kiosk("logout")
        kiosk("manual-start")
        self.assertEqual(kiosk("manual-search", query="R1")["people"][0]["id"], person)
        login = kiosk("manual-login", id=person, pin="0042")
        self.assertEqual(login["stage"], "shop")
        self.assertEqual(login["catalog"], app.catalog(terminal))
        self.assertGreater(len(login["catalog"]["products"]), 0)
        self.assertNotIn("catalog", app.state(terminal))

        with self.assertRaises(store.Problem) as unauthorized:
            app.admin_route("POST", "/api/admin/reset-pin", {}, {"id": person}, {}, None)
        self.assertEqual(unauthorized.exception.status, 401)
        app.admin_route("POST", "/api/admin/reset-pin", {}, {"id": person}, {"kk_admin": "session"}, None)
        self.assertEqual(terminal.kiosk["stage"], "idle")
        kiosk("manual-start")
        self.assertEqual(kiosk("manual-search", query="R1")["people"], [])
        with self.assertRaises(store.Problem) as unconfigured:
            kiosk("pin-setup", pin="6789", pin_confirmation="6789")
        self.assertEqual(unconfigured.exception.status, 409)
        kiosk("logout")

        terminal.kiosk["seen"] = server.monotonic()
        app.scan(terminal, uid)
        self.assertEqual(app.state(terminal)["stage"], "pin-setup")
        self.assertEqual(kiosk("pin-setup", pin="6789", pin_confirmation="6789")["stage"], "shop")
        kiosk("logout")
        kiosk("manual-start")
        for attempt in range(server.MANUAL_LIMIT):
            with self.assertRaises(store.Problem) as rejected:
                kiosk("manual-login", id=person, pin="0042")
            self.assertEqual(rejected.exception.status, 401 if attempt + 1 < server.MANUAL_LIMIT else 429)
        with self.assertRaises(store.Problem) as blocked:
            kiosk("manual-login", id=person, pin="6789")
        self.assertEqual(blocked.exception.status, 429)
        kiosk("logout")
        terminal.kiosk["seen"] = server.monotonic()
        app.scan(terminal, uid)
        self.assertEqual(app.state(terminal)["stage"], "shop")

        with self.connect() as db:
            db.execute("UPDATE manual_attempts SET expires=0 WHERE person=%s", (person,))
        kiosk("logout")
        kiosk("manual-start")
        self.assertEqual(kiosk("manual-login", id=person, pin="6789")["stage"], "shop")

    def test_retention_preserves_balance_and_removes_old_booking_details(self):
        self.initialize()
        clock = datetime.now(timezone.utc)
        with self.connect() as db:
            person = self.person(db)
            store.entry(db, person, "purchase", -700, at=(clock - timedelta(days=91)).isoformat())
            store.entry(db, person, "payment", 200, at=clock.isoformat())
            before = store.balance(db, person)
            store.expire_booking_details(db, clock, b"k" * 32)
            self.assertEqual(store.balance(db, person), before)
            self.assertEqual(store.carried_balance(db, person), -700)
            self.assertEqual(db.execute("SELECT COUNT(*) AS total FROM journal").fetchone()["total"], 1)

    def test_retention_rollback_does_not_block_two_terminals_for_same_account(self):
        app = server.App({}, self.config)
        uid = "04010203"
        clock = datetime.now(timezone.utc)
        with self.connect() as db:
            person = self.person(db, app.card_digest(uid))
            store.accept_policies(db, person, app.version, app.privacy["version"], "a")
            db.execute("INSERT INTO manual_credentials VALUES (%s,'synthetic')", (person,))
            expired = store.entry(db, person, "payment", 500, at=(clock - timedelta(days=91)).isoformat(),
                                  terminal="a", kiosk_pending=True)
            product = store.available_products(db, "a")[0]

        original = store.expire_booking_details
        stop, before_commit, release, retry = Event(), Event(), Event(), Event()

        def run_expiry(db, now, key):
            due = original(db, now, key)
            if not before_commit.is_set():
                before_commit.set()
                if not release.wait(12):
                    raise RuntimeError("test did not release retention")
                raise RuntimeError("synthetic rollback before commit")
            retry.set()
            return due

        def buy(terminal):
            with terminal.lock:
                secret = terminal.id * 64
                terminal.paired_browser = app.device_digest("browser", secret)
                terminal.kiosk = {"token": "browser", "seen": server.monotonic()}
                app.clear_kiosk(terminal)
                app.scan(terminal, uid)
                self.assertEqual(terminal.kiosk["stage"], "shop")
                visit = terminal.kiosk["visit"]
                request = terminal.id * 32
                cookies = {"kk_kiosk": "browser", server.DEVICE_COOKIE: secret}
                body = {"visit": visit, "request": request, "lines": [
                    {"id": product["id"], "qty": 1, "cents": product["cents"]},
                ]}
                payload, _ = app.route(None, "POST", "/api/kiosk/checkout", {}, body, cookies)
                repeat, _ = app.route(None, "POST", "/api/kiosk/checkout", {}, body, cookies)
                self.assertEqual(payload["receipt"], repeat["receipt"])
                app.route(None, "POST", "/api/kiosk/booking-seen", {},
                          {"visit": visit, "request": request, "kind": "purchase"}, cookies)
                return payload["receipt"]["balance"]

        with patch("store.expire_booking_details", side_effect=run_expiry), ThreadPoolExecutor(max_workers=1) as requests:
            worker = Thread(target=app.retention_worker, args=(stop,), daemon=True)
            worker.start()
            try:
                self.assertTrue(before_commit.wait(6))
                balances = requests.submit(lambda: [buy(app.terminals[site]) for site in ("a", "b")]).result(timeout=6)
                self.assertEqual(balances, [500 - product["cents"], 500 - 2 * product["cents"]])
                release.set()
                self.assertTrue(retry.wait(12))
            finally:
                release.set()
                stop.set()
                worker.join(7)
            self.assertFalse(worker.is_alive())
            self.assertIsNone(app.retention_status["failed_since"])
            self.assertIsNotNone(app.retention_status["last_success"])

        with self.connect() as db:
            original(db, datetime.now(timezone.utc), app.key)
            self.assertEqual(store.carried_balance(db, person), 500)
            self.assertEqual(store.balance(db, person), 500 - 2 * product["cents"])
            self.assertIsNone(db.execute("SELECT id FROM journal WHERE id=%s", (expired,)).fetchone())
            sales = db.execute("SELECT terminal,cents FROM journal WHERE person=%s ORDER BY id", (person,)).fetchall()
            self.assertEqual(sales, [{"terminal": site, "cents": -product["cents"]} for site in ("a", "b")])
            totals = db.execute("SELECT SUM(orders) AS orders,SUM(gross) AS gross FROM monthly_sales").fetchone()
            self.assertEqual(totals, {"orders": 2, "gross": 2 * product["cents"]})

    def test_expired_purchase_is_hidden_in_export_and_kept_in_balance_during_backlog(self):
        self.initialize()
        clock = datetime.now(timezone.utc).replace(microsecond=0)
        with self.connect() as db:
            person = self.person(db)
            product = store.available_products(db, "a")[0]
            sale = self.buy_named(db, person, product, "ABGELAUFENER ARTIKEL",
                                  (clock - timedelta(days=91)).isoformat(), "a")["entry"]
            with self.assertRaises(store.Problem) as replay:
                store.purchases(db, person, "a" * 32, [(product["id"], 1, product["cents"])], "a")
            self.assertEqual(replay.exception.status, 409)
            store.entry(db, person, "reversal", product["cents"], at=clock.isoformat(), note="Aktiver Stornogrund",
                        reverses=sale, terminal="a")
            download = finance.account_export(db, person, {"a": "A"}, finance.local_date(clock))
            with ZipFile(BytesIO(download.content)) as archive:
                strings = archive.read("xl/sharedStrings.xml").decode()
                self.assertNotIn("ABGELAUFENER ARTIKEL", strings)
                self.assertNotIn("Zu Kauf #", strings)
                self.assertIn("Aktiver Stornogrund", strings)
                self.assertIn("Saldoübertrag", strings)
                sheet = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
                self.assertEqual(sheet.find(".//{*}c[@r='H2']/{*}v").text, "0")
            self.assertEqual(store.balance(db, person), 0)
            self.assertIsNotNone(db.execute("SELECT name FROM items WHERE entry=%s", (sale,)).fetchone())

    def test_retention_keeps_paypal_deduplication_after_deleting_details(self):
        self.initialize()
        clock = datetime.now(timezone.utc)
        expired = (clock - timedelta(days=91)).isoformat()
        key = b"k" * 32
        with self.connect() as db:
            person = self.person(db)
            booking = store.entry(db, person, "payment", 500, at=expired)
            db.execute("""INSERT INTO paypal_requests (person,terminal,request_id,reference,cents,created,status,
                                                       resolved,transaction_ref,journal_id)
                          VALUES (%s,'a','paid','ARCHIV-1',500,%s,'confirmed',%s,'TXN-OLD',%s)""",
                       (person, expired, expired, booking))
            pending = db.execute("""INSERT INTO paypal_requests(person,terminal,request_id,reference,cents,created)
                                    VALUES (%s,'a','unpaid','ARCHIV-2',300,%s) RETURNING id""",
                                 (person, expired)).fetchone()["id"]
            self.assertEqual(finance.paypal_for_person(db, person), [])
            self.assertIsNone(store.pending_kiosk_booking(db, person))
            self.assertEqual(finance.paypal_overview(db, "confirmed", 2**63-1)["payments"], [])
            with self.assertRaises(store.Problem) as error:
                finance.paypal_resolve(db, pending, "admin", cents=300, transaction="TXN-NEW", key=key)
            self.assertEqual(error.exception.status, 404)

            store.expire_booking_details(db, clock, key)
            self.assertEqual(db.execute("SELECT COUNT(*) AS total FROM paypal_requests").fetchone()["total"], 0)
            digest = db.execute("SELECT digest FROM paypal_used_fingerprints").fetchone()["digest"]
            self.assertEqual(digest, store.paypal_fingerprint(key, "TXN-OLD"))
            finance.paypal_prepare(db, person, "a", "current", 500)
            current = db.execute("SELECT id FROM paypal_requests WHERE request_id='current'").fetchone()["id"]
            with self.assertRaises(store.Problem) as error:
                finance.paypal_resolve(db, current, "admin", cents=500, transaction="TXN-OLD", key=key)
            self.assertEqual(error.exception.status, 409)
            self.assertEqual(store.balance(db, person), 500)

    def test_closed_settled_account_is_deleted(self):
        self.initialize()
        with self.connect() as db:
            person = self.person(db)
            db.execute("UPDATE people SET active=0,closed_at=%s WHERE id=%s", (store.now(), person))
            store.expire_booking_details(db, datetime.now(timezone.utc), b"k" * 32)
            self.assertIsNone(db.execute("SELECT id FROM people WHERE id=%s", (person,)).fetchone())

    def buy_named(self, db, person, product, name, stamp, request):
        db.execute("UPDATE products SET name=%s WHERE id=%s", (name, product["id"]))
        with patch("store.now", return_value=stamp):
            return store.purchases(db, person, request * 32, [(product["id"], 1, product["cents"])], "a")

    def test_renames_within_and_across_months_keep_original_names(self):
        self.initialize()
        with self.connect() as db:
            person = self.person(db)
            product = store.available_products(db, "a")[0]
            self.buy_named(db, person, product, "Alter Name", "2026-01-05T12:00:00+00:00", "a")
            self.buy_named(db, person, product, "Neuer Name", "2026-01-20T12:00:00+00:00", "b")
            self.buy_named(db, person, product, "Februarname", "2026-02-01T12:00:00+00:00", "c")
            january = finance.monthly(db, "2026-01", None)
            self.assertEqual({r["name"]: r["sold"] for r in january["products"]}, {"Alter Name": 1, "Neuer Name": 1})
            self.assertEqual(january["gross"], 2 * product["cents"])
            self.assertEqual(finance.monthly(db, "2026-02", "a")["products"][0]["name"], "Februarname")
            self.assertEqual(finance.monthly(db, "2026-01", "b")["products"], [])

    def test_reversal_uses_purchase_name_after_rename_and_hiding(self):
        self.initialize()
        with self.connect() as db:
            person = self.person(db)
            product = store.available_products(db, "a")[0]
            sale = self.buy_named(db, person, product, "Beim Kauf", "2026-01-31T22:59:00+00:00", "a")
            db.execute("UPDATE products SET name='Heute',deleted=1,active=0 WHERE id=%s", (product["id"],))
            at = "2026-01-31T23:01:00+00:00"  # February in Europe/Berlin
            reversal_id = store.entry(db, person, "reversal", product["cents"], reverses=sale["entry"],
                                      terminal="a", note="Doppelter Kauf", at=at)
            store.add_monthly_sale(db, "a", at, product["cents"], sale["entry"], reversal=True)
            row = finance.monthly(db, "2026-02", "a")["products"][0]
            self.assertEqual((row["name"], row["sold"], row["returned"], row["net"]), ("Beim Kauf", 0, 1, -product["cents"]))
            visible_since = "2026-01-01T00:00:00+00:00"
            reversal, purchase = store.list_journal(db, person, 2**63-1, cutoff=visible_since)["entries"]
            self.assertEqual(reversal["id"], reversal_id)
            self.assertEqual((reversal["reverses"], reversal["note"]), (sale["entry"], "Doppelter Kauf"))
            item = {"name": "Beim Kauf", "price": product["cents"], "quantity": 1}
            self.assertEqual(reversal["items"], [item])
            self.assertEqual(purchase["items"], [item])
            _, start, end = finance.month_bounds("2026-02")
            self.assertEqual(store.personal_history(db, person, start, end, None, cutoff=visible_since)
                             ["entries"][0]["items"], [item])

            # The purchase expires before the reversal, which has its own timestamp.
            clock = datetime.fromisoformat(at) + store.BOOKING_RETENTION - timedelta(minutes=1)
            store.expire_booking_details(db, clock, b"k" * 32)
            remaining, = store.list_journal(db, person, 2**63-1, cutoff=store.booking_cutoff(clock))["entries"]
            self.assertEqual(remaining["id"], reversal_id)
            self.assertEqual((remaining["reverses"], remaining["items"]), (None, []))
            self.assertEqual((remaining["cents"], remaining["note"]), (product["cents"], "Doppelter Kauf"))
            self.assertEqual(store.personal_history(db, person, start, end, None, cutoff=store.booking_cutoff(clock))
                             ["entries"][0]["items"], [])
            self.assertEqual(store.balance(db, person), 0)
            self.assertEqual(finance.monthly(db, "2026-02", "a")["products"], [row])

    def test_snapshot_names_survive_personal_booking_retention(self):
        self.initialize()
        clock = datetime.now(timezone.utc)
        stamp = (clock - timedelta(days=100)).isoformat()
        with self.connect() as db:
            person = self.person(db)
            product = store.available_products(db, "a")[0]
            self.buy_named(db, person, product, "Historisch", stamp, "a")
            db.execute("UPDATE products SET name='Aktuell' WHERE id=%s", (product["id"],))
            store.expire_booking_details(db, clock, b"k" * 32)
            self.assertEqual(db.execute("SELECT COUNT(*) AS n FROM items").fetchone()["n"], 0)
            month = finance.local_date(stamp).strftime("%Y-%m")
            self.assertEqual(finance.monthly(db, month, None)["products"][0]["name"], "Historisch")

    def test_v28_backfill_recovers_item_names_and_marks_expired_residual(self):
        with self.connect() as db:
            schema.migrate(db, schema.MIGRATIONS[:1])
            db.execute("INSERT INTO terminals (id) VALUES ('a'),('b')")
            person = self.person(db)
            product = db.execute("INSERT INTO products (category,name,cents,icon) VALUES ('snack','Aktuell',200,'snack') RETURNING id").fetchone()["id"]
            first, second = [row["id"] for row in db.execute(
                """INSERT INTO journal (person,kind,cents,terminal,at)
                   VALUES (%s,'purchase',-200,'a','2026-01-01T12:00:00Z'),
                          (%s,'purchase',-200,'a','2026-01-02T12:00:00Z') RETURNING id""", (person, person)
            )]
            db.execute("INSERT INTO items VALUES (%s,%s,'Alt',200,1),(%s,%s,'Umbenannt',200,1)", (first,product,second,product))
            db.execute("""INSERT INTO journal (person,kind,cents,terminal,at,reverses)
                          VALUES (%s,'reversal',200,'a','2026-02-01T12:00:00Z',%s)""", (person, first))
            db.execute("INSERT INTO monthly_sales VALUES ('2026-01-01','a',600,0,3),('2026-02-01','a',0,200,0)")
            db.execute("INSERT INTO monthly_products VALUES ('2026-01-01','a',%s,3,0,600),('2026-02-01','a',%s,0,1,-200)", (product,product))
        self.initialize()
        with self.connect() as db:
            report = finance.monthly(db, "2026-01", None)
            self.assertEqual(len(report["products"]), 3)
            self.assertEqual({r["name"] for r in report["products"] if r["name_recorded"]}, {"Alt", "Umbenannt"})
            unknown = [r for r in report["products"] if not r["name_recorded"]][0]
            self.assertIn("unbekannt", unknown["name"])
            self.assertEqual((unknown["sold"], unknown["net"]), (1,200))
            self.assertEqual(sum(r["net"] for r in report["products"]), report["gross"])
            self.assertEqual(finance.monthly(db, "2026-02", None)["products"][0]["name"], "Alt")
        self.initialize()  # no repeated backfill or changed checksums


if __name__ == "__main__":
    unittest.main()
