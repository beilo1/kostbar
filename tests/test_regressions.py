"""Fast behavioural regressions without a database or terminal hardware."""
import io
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Event, RLock, Thread
from unittest.mock import Mock, patch
from xml.etree import ElementTree as ET

import server
import store

ROOT = Path(__file__).resolve().parents[1]


def kiosk_app():
    app = object.__new__(server.App)
    app.key = bytes(range(32))
    app.version = "test-terms"
    app.privacy = {"version": "test-privacy"}
    app.origin = "https://kostbar.internal.lan:18443"
    app.host = "kostbar.internal.lan:18443"
    app.db = {}
    app.admins = {}
    app.admin_state_lock = RLock()
    app.admin_write_lock = RLock()
    app.pairing_lock = RLock()
    app.policy_lock = RLock()
    app.retention_status = {"last_success": None, "running_since": None, "failed_since": None}
    terminal = server.Terminal("a", "Test A", "x" * 43)
    app.terminals = {"a": terminal}
    terminal.kiosk = {"token": "browser", "seen": server.monotonic()}
    app.clear_kiosk(terminal)
    return app, terminal


class ManualTimeoutTests(unittest.TestCase):
    def setUp(self):
        self.app, self.terminal = kiosk_app()
        self.cookies = {"kk_kiosk": "browser"}

    def call(self, action, body=None):
        return self.app.kiosk_route(self.terminal, "POST", "/api/kiosk/" + action,
                                   body or {}, self.cookies)[0]

    def test_manual_start_has_a_visit_and_fifteen_second_deadline(self):
        state = self.call("manual-start")
        self.assertEqual(state["stage"], "manual")
        self.assertTrue(state["visit"])
        self.assertGreater(state["remaining"], 14)
        self.assertLessEqual(state["remaining"], 15)

    def test_abandoned_manual_login_expires_and_erases_visit(self):
        state = self.call("manual-start")
        with patch("server.monotonic", return_value=self.terminal.kiosk["until"] + 1):
            self.app.sweep_terminal(self.terminal)
        self.assertEqual(self.terminal.kiosk["stage"], "idle")
        self.assertIsNone(self.terminal.kiosk["visit"])
        for action in ("manual-search", "manual-login"):
            with self.subTest(action=action), self.assertRaises(store.Problem) as error:
                self.call(action, {"visit": state["visit"], "query": "Test", "id": 1, "pin": "0042"})
            self.assertEqual(error.exception.status, 409)

    def test_activity_extends_manual_deadline(self):
        state = self.call("manual-start")
        clock = server.monotonic() + 9
        with patch("server.monotonic", return_value=clock):
            self.call("activity", {"visit": state["visit"]})
        self.assertEqual(self.terminal.kiosk["until"], clock + 15)

    def test_stale_activity_cannot_extend_another_visit(self):
        self.call("manual-start")
        before = self.terminal.kiosk["until"]
        with self.assertRaises(store.Problem):
            self.call("activity", {"visit": "stale"})
        self.assertEqual(self.terminal.kiosk["until"], before)

    def test_cancel_clears_manual_session(self):
        state = self.call("manual-start")
        result = self.call("logout", {"visit": state["visit"]})
        self.assertEqual(result["stage"], "idle")
        self.assertIsNone(result["visit"])

    def test_late_login_cannot_use_a_new_manual_visit(self):
        old = self.call("manual-start")
        self.call("logout", {"visit": old["visit"]})
        new = self.call("manual-start")
        self.assertNotEqual(old["visit"], new["visit"])
        with self.assertRaises(store.Problem):
            self.call("manual-login", {"visit": old["visit"], "id": 1, "pin": "0042"})
        self.assertEqual(self.terminal.kiosk["stage"], "manual")

    def test_missing_visit_is_rejected_before_credentials_are_checked(self):
        self.call("manual-start")
        with patch.object(self.app, "manual_login") as login:
            with self.assertRaises(store.Problem):
                self.call("manual-login", {"id": 1, "pin": "0042"})
            login.assert_not_called()

    def test_valid_visit_reaches_login(self):
        state = self.call("manual-start")
        body = {"visit": state["visit"], "id": 1, "pin": "0042"}
        with patch.object(self.app, "manual_login") as login:
            self.call("manual-login", body)
        login.assert_called_once_with(self.terminal, body)

    def test_manual_start_does_not_interrupt_an_active_visit(self):
        self.terminal.kiosk["stage"] = "shop"
        with self.assertRaises(store.Problem) as error:
            self.call("manual-start")
        self.assertEqual(error.exception.status, 409)

    def test_manual_start_does_not_interrupt_card_replacement(self):
        self.terminal.capture = {"owner": "admin"}
        with self.assertRaises(store.Problem):
            self.call("manual-start")


class TerminalPinTests(unittest.TestCase):
    def test_pin_is_exactly_four_ascii_digits(self):
        self.assertEqual(server.terminal_pin("0042"), "0042")
        for pin in (None, 1234, "", "042", "00042", "１２３４", "42a3", " 042", "0042\n"):
            with self.subTest(pin=pin), self.assertRaises(store.Problem) as error:
                server.terminal_pin(pin)
            self.assertEqual(error.exception.status, 400)

    def test_pin_confirmation_and_salted_storage(self):
        app, _ = kiosk_app()
        with self.assertRaises(store.Problem):
            app.confirmed_pin_hash({"pin": "0042", "pin_confirmation": "0043"})
        body = {"pin": "0042", "pin_confirmation": "0042"}
        first = app.confirmed_pin_hash(body)
        second = app.confirmed_pin_hash(body)
        self.assertNotEqual(first, second)
        self.assertTrue(store.check_password(app.pin_material("0042"), first))
        self.assertFalse(store.check_password("0042", first))

    def test_replacement_pin_does_not_reactivate_an_old_manual_session(self):
        app, terminal = kiosk_app()
        terminal.kiosk["manual_pin_hash"] = "old"
        self.assertFalse(app.valid_account({"active": 1, "pin_hash": None}, terminal.kiosk))
        self.assertFalse(app.valid_account({"active": 1, "pin_hash": "new"}, terminal.kiosk))


class AdminBookingRetryTests(unittest.TestCase):
    def setUp(self):
        self.app, _ = kiosk_app()
        self.app.admins = {"session": {"name": "admin", "password": "hash", "super_admin": False,
                                       "until": float("inf"), "max": float("inf")}}
        self.saved = {"id": 77, "kind": "payment", "cents": 500, "note": "Barzahlung", "actor": "admin"}
        self.body = {"id": 1, "request": "a" * 32, "kind": "payment", "cents": 500, "note": "Barzahlung"}
        self.db = Mock()
        def execute(sql, parameters=()):
            if "SELECT password,super_admin FROM admins" in sql:
                row = {"password": "hash", "super_admin": False}
            elif "FROM people" in sql:
                row = {"id": 1}
            elif "FROM journal" in sql:
                row = self.saved
            else:
                raise AssertionError(sql)
            result = Mock()
            result.fetchone.return_value = row
            return result
        self.db.execute.side_effect = execute
        @contextmanager
        def connect(*args, **kwargs):
            yield self.db
        self.connection = patch("store.connect", connect)
        self.connection.start()
        self.addCleanup(self.connection.stop)

    def call(self, body=None):
        return self.app.admin_route("POST", "/api/admin/adjust", {}, body or self.body,
                                    {"kk_admin": "session"}, None)

    def test_identical_retry_succeeds_without_another_entry(self):
        with patch("store.entry") as entry:
            self.assertEqual(self.call(), ({}, None))
            entry.assert_not_called()

    def test_changed_amount_is_rejected(self):
        with self.assertRaises(store.Problem) as error:
            self.call({**self.body, "cents": 1000})
        self.assertEqual(error.exception.status, 409)

    def test_changed_booking_kind_is_rejected(self):
        with self.assertRaises(store.Problem):
            self.call({**self.body, "kind": "correction"})

    def test_changed_note_is_rejected(self):
        with self.assertRaises(store.Problem):
            self.call({**self.body, "note": "Andere Zahlung"})

    def test_another_operator_cannot_reuse_the_request(self):
        self.saved["actor"] = "someone-else"
        with self.assertRaises(store.Problem):
            self.call()

    def test_new_request_writes_the_entry_and_audit(self):
        self.saved = None
        with patch("store.entry") as entry, patch("store.balance", return_value=-100) as balance, patch("store.audit") as audit:
            self.call()
            entry.assert_called_once()
            self.assertEqual(entry.call_args.args[1:6], (1, "payment", 500, "admin", "Barzahlung"))
            audit.assert_called_once()
            balance.assert_called_once()

    def test_normalized_note_is_still_an_identical_retry(self):
        self.assertEqual(self.call({**self.body, "note": "  Barzahlung  "}), ({}, None))

    def test_regular_admin_cannot_permanently_hide_a_product(self):
        with self.assertRaises(store.Problem) as error:
            self.app.admin_route("POST", "/api/admin/delete-product", {}, {"id": 1},
                                 {"kk_admin": "session"}, None)
        self.assertEqual(error.exception.status, 403)
        self.assertEqual(self.db.execute.call_count, 1)

    def test_unsigned_request_cannot_write_admin_bookings(self):
        with self.assertRaises(store.Problem) as error:
            self.app.admin_route("POST", "/api/admin/adjust", {}, self.body, {}, None)
        self.assertEqual(error.exception.status, 401)
        self.db.execute.assert_not_called()


class HttpBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.app, _ = kiosk_app()
        self.http = server.WsgiApp(self.app)

    def request(self, path, method="GET", body=b"{}", **changes):
        environ = {"HTTP_HOST": self.app.host, "REQUEST_METHOD": method, "PATH_INFO": path,
                   "REQUEST_URI": path, "QUERY_STRING": "", "HTTP_ORIGIN": self.app.origin,
                   "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(body)),
                   "wsgi.input": io.BytesIO(body)}
        environ.update(changes)
        response = {}
        def start(status, headers):
            response["status"] = int(status.split()[0]); response["headers"] = dict(headers)
        response["body"] = json.loads(b"".join(self.http(environ, start)))
        return response

    def test_admin_requires_authentication(self):
        self.assertEqual(self.request("/api/admin/overview")["status"], 401)

    def test_foreign_origin_is_rejected(self):
        self.assertEqual(self.request("/api/kiosk/manual-start", "POST", HTTP_ORIGIN="https://foreign.invalid")["status"], 403)

    def test_wrong_method_does_not_reach_a_booking(self):
        self.assertEqual(self.request("/api/admin/adjust")["status"], 405)

    def test_malformed_json_is_rejected(self):
        self.assertEqual(self.request("/api/kiosk/manual-start", "POST", body=b"{broken")["status"], 400)

    def test_reader_requires_its_own_token(self):
        self.assertEqual(self.request("/terminal/a/internal/reader", "POST")["status"], 403)

    def test_unknown_host_is_rejected(self):
        self.assertEqual(self.request("/api/admin/overview", HTTP_HOST="foreign.invalid")["status"], 421)

    def test_sensitive_responses_are_not_cached(self):
        self.assertEqual(self.request("/api/admin/overview")["headers"]["Cache-Control"], "no-store")

    def test_http_serializes_postgres_timestamps(self):
        with patch.object(self.app, "route", return_value=({"at": datetime(2026, 1, 1, tzinfo=timezone.utc)}, None)):
            self.assertEqual(self.request("/api/admin/journal")["body"], {"at": "2026-01-01T00:00:00+00:00"})

    def test_export_and_slow_terminal_do_not_hold_a_global_lock(self):
        export_started, terminal_started, release = Event(), Event(), Event()
        self.app.admins["session"] = {"name": "test", "password": "hash", "super_admin": False,
                                      "until": float("inf"), "max": float("inf")}
        self.app.terminals["etage-2"] = self.app.new_terminal("etage-2", "Etage 2")
        for terminal, secret in zip(self.app.terminals.values(), ("a" * 64, "b" * 64)):
            terminal.paired_browser = self.app.device_digest("browser", secret)

        def export(path, query, key, session, caddy_version):
            export_started.set()
            if not release.wait(5):
                raise RuntimeError("Export wurde nicht freigegeben.")
            return {"exported": True}

        real_state = self.app.state

        def state(terminal):
            if terminal.id == "a":
                terminal_started.set()
                if not release.wait(5):
                    raise RuntimeError("Terminal A wurde nicht freigegeben.")
            return real_state(terminal)

        def poll(secret):
            cookie = f"{server.DEVICE_COOKIE}={secret}; kk_kiosk=browser"
            return self.request("/api/kiosk/state", HTTP_COOKIE=cookie)

        with (patch("store.connect") as connect, patch.object(self.app, "admin_read", side_effect=export),
              patch.object(self.app, "state", side_effect=state), ThreadPoolExecutor(max_workers=3) as jobs):
            db = connect.return_value.__enter__.return_value
            db.execute.return_value.fetchone.return_value = {"password": "hash", "super_admin": False}
            try:
                export_job = jobs.submit(self.request, "/api/admin/export-balances", HTTP_COOKIE="kk_admin=session")
                self.assertTrue(export_started.wait(2))
                first = jobs.submit(poll, "a" * 64)
                self.assertTrue(terminal_started.wait(2))
                self.assertEqual(jobs.submit(poll, "b" * 64).result(timeout=2)["body"]["terminal"], "Etage 2")
            finally:
                release.set()
            self.assertEqual(export_job.result(timeout=2)["status"], 200)
            self.assertEqual(first.result(timeout=2)["status"], 200)

    def test_pending_retention_does_not_lock_health_request(self):
        stop, started, release = Event(), Event(), Event()

        def retention(db, clock, key):
            started.set()
            release.wait(10)
            return clock + timedelta(minutes=1)

        with patch("store.connect"), patch("store.expire_booking_details", side_effect=retention):
            worker = Thread(target=self.app.retention_worker, args=(stop,), daemon=True)
            worker.start()
            with ThreadPoolExecutor(max_workers=1) as executor:
                try:
                    self.assertTrue(started.wait(3))
                    self.assertIsNotNone(self.app.retention_status["running_since"])
                    response = executor.submit(self.request, "/healthz").result(timeout=3)
                    self.assertEqual(response["status"], 200)
                    self.assertEqual(response["body"], {"ok": True})
                finally:
                    stop.set()
                    release.set()
                    worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertIsNotNone(self.app.retention_status["last_success"])

    def test_retention_failure_retries_and_records_recovery(self):
        stop = Mock()
        stop.is_set.side_effect = [False, False, True]
        statuses = []
        stop.wait.side_effect = lambda delay: statuses.append((delay, self.app.retention_status))

        attempts = iter((RuntimeError("synthetic failure"), None))

        def fail_then_complete(db, clock, key):
            error = next(attempts)
            if error:
                raise error
            return clock + timedelta(minutes=1)

        with (patch("store.connect"), patch("store.expire_booking_details", side_effect=fail_then_complete),
              patch("sys.stderr", new_callable=io.StringIO) as log):
            self.app.retention_worker(stop)
            self.assertIn("wieder erfolgreich", log.getvalue())
        self.assertEqual(statuses[0][0], 5)
        self.assertIsNotNone(statuses[0][1]["failed_since"])
        self.assertIsNone(statuses[0][1]["last_success"])
        self.assertIsNone(statuses[1][1]["failed_since"])
        self.assertIsNotNone(statuses[1][1]["last_success"])

    def test_checkout_receipt_retry_matches_booked_lines(self):
        terminal = self.app.terminals["a"]
        secret = "b" * 64
        terminal.paired_browser = self.app.device_digest("browser", secret)
        terminal.kiosk.update(stage="shop", user=1, visit="visit", until=server.monotonic() + 15)
        key = "1" * 32
        cookie = f"{server.DEVICE_COOKIE}={secret}; kk_kiosk=browser"
        def checkout(lines, request=key):
            body = {"visit": "visit", "request": request, "lines": lines}
            return self.request("/api/kiosk/checkout", "POST", json.dumps(body).encode(), HTTP_COOKIE=cookie)
        cart = [{"id": 2, "qty": 2, "cents": 80}, {"id": 1, "qty": 1, "cents": 50}]
        loyalty = store.loyalty_card_status(10)
        with (patch("store.connect"), patch.object(self.app, "require_account"),
              patch("store.check_pending_kiosk_booking"), patch("store.purchases",
              return_value={"entry": 17, "total": 210, "balance": -210, "stamps_earned": 2}) as purchases,
              patch("store.loyalty_card", return_value=loyalty) as loyalty_card):
            first = checkout(cart)
            self.assertEqual(first["status"], 200)
            self.assertEqual(first["body"]["receipt"]["loyalty"], loyalty)
            original_deadline = terminal.kiosk["until"]
            repeat = checkout(cart[::-1])
            self.assertEqual(repeat["status"], 200)
            self.assertEqual(repeat["body"]["receipt"], first["body"]["receipt"])
            for change in ({"id": 3}, {"qty": 1}, {"cents": 81}):
                with self.subTest(change=change):
                    self.assertEqual(checkout([{**cart[0], **change}, cart[1]])["status"], 409)
            self.assertEqual(checkout(cart, "2" * 32)["status"], 409)
            self.assertEqual(terminal.kiosk["until"], original_deadline)
            purchases.assert_called_once()
            loyalty_card.assert_called_once()


@unittest.skipUnless(sys.platform != "win32" and shutil.which("bash"), "Bash preflight runs on Linux/Pi or in the test container")
class InstallerPathTests(unittest.TestCase):
    def test_relative_and_absolute_inputs_survive_changing_directory(self):
        source = (ROOT / "pi/install.sh").read_text(encoding="utf-8")
        prefix = source.split("if ! /usr/bin/python3 -c 'import smartcard.scard'", 1)[0]
        self.assertNotEqual(prefix, source)
        prefix = prefix.replace("/usr/bin/python3", shlex.quote(sys.executable))
        with tempfile.TemporaryDirectory(prefix="kostbar-installer-") as folder:
            root = Path(folder)
            (root / "pi").mkdir()
            (root / "terminal a.json").write_text(json.dumps({"ca_file": "/etc/kaffeekasse-terminal/nas-root.crt"}))
            (root / "root ca.crt").write_text("public certificate test fixture")
            script = root / "pi/install.sh"
            script.write_text(prefix + '\nprintf "%s\\n%s\\n" "$device" "$cert"\n')
            driver = 'id() { echo 0; }; certutil() { :; }; export -f id certutil; bash "$@"'
            for absolute in (False, True):
                with self.subTest(absolute=absolute):
                    files = [root / "terminal a.json", root / "root ca.crt"]
                    args = [str(p if absolute else p.relative_to(root)) for p in files]
                    result = subprocess.run(["bash", "-c", driver, "bash", str(script), *args],
                                            cwd=root, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.splitlines()[-2:], [str(p) for p in files])


class KioskDesktopTests(unittest.TestCase):
    def boot(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "pi/kiosk_boot.py"), *args],
                              capture_output=True, text=True, check=True).stdout

    def test_kiosk_reuses_touch_mapping_and_calibration_from_desktop(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            labwc = home / ".config/labwc"
            labwc.mkdir(parents=True)
            rc = labwc / "rc.xml"
            original = ('<openbox_config xmlns="http://openbox.org/3.4/rc">\n'
                        '  <keyboard><keybind key="F7"><action name="ShowMenu"/></keybind></keyboard>\n'
                        '  <touch deviceName="Touch A" mapToOutput="DSI-2" mouseEmulation="yes"/>\n'
                        '  <touch><deviceName>Touch B</deviceName><mouseEmulation>yes</mouseEmulation></touch>\n'
                        '  <libinput><device category="touch"><calibrationMatrix>1 0 0 0 1 0</calibrationMatrix>'
                        '</device></libinput>\n</openbox_config>\n')
            rc.write_text(original, encoding="utf-8")
            config = ET.fromstring(self.boot("rc", folder))
            self.assertEqual([device.attrib for device in config.findall("./touch")], [
                {"deviceName": "Touch A", "mapToOutput": "DSI-2", "mouseEmulation": "no"},
                {"deviceName": "Touch B", "mouseEmulation": "no"}])
            self.assertEqual(config.findtext("./libinput/device/calibrationMatrix"), "1 0 0 0 1 0")
            self.assertEqual([action.get("name") for action in config.findall(".//action")], ["Focus", "Focus"])
            self.assertEqual(rc.read_text(encoding="utf-8"), original)

    def test_autostart_carries_only_scale_and_keeps_cursor_theme(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            labwc = home / ".config/labwc"
            labwc.mkdir(parents=True)
            autostart = labwc / "autostart"
            launch = "/opt/kaffeekasse-terminal/start-kiosk.sh"
            original = f"custom-start &\nKIOSK_SCALE=1.5 {launch} &\n"
            autostart.write_text(original, encoding="utf-8")
            environment = labwc / "environment"
            environment.write_text("XKB_DEFAULT_LAYOUT=de\nXCURSOR_THEME=PiXflat\n", encoding="utf-8")
            scale = self.boot("saved-scale", autostart).strip()
            self.assertEqual(self.boot("autostart", scale), f"KIOSK_SCALE=1.5 {launch} &\n")
            self.assertEqual(self.boot("autostart", ""), f"{launch} &\n")
            self.boot("cursor", folder)
            self.boot("cursor", folder)
            self.assertEqual(autostart.read_text(encoding="utf-8"), original)
            self.assertEqual(environment.read_text(encoding="utf-8").splitlines(),
                             ["XKB_DEFAULT_LAYOUT=de", "XCURSOR_THEME=PiXflat"])
            cursors = home / ".icons/KoSTbar-Transparent/cursors"
            data = (cursors / "default").read_bytes()
            self.assertEqual(data[:4], b"Xcur")
            self.assertEqual(data[-4:], bytes(4))
            self.assertEqual(data, (cursors / "left_ptr").read_bytes())

    def test_browser_policies_allow_only_expected_navigation(self):
        with tempfile.TemporaryDirectory() as folder:
            profile = Path(folder) / "device.json"
            for authority, browser_filter in (
                ("kostbar.internal.lan:18443", "https://.kostbar.internal.lan:18443"),
                ("kostbar.example.org", "https://.kostbar.example.org:443"),
                ("192.0.2.25:18443", "https://.192.0.2.25:18443"),
            ):
                with self.subTest(authority=authority):
                    profile.write_text(json.dumps({"origin": f"https://{authority}"}), encoding="utf-8")
                    policy = json.loads(self.boot("policy", profile))
                    self.assertEqual(policy["URLAllowlist"], [browser_filter, "https://.github.com:443/beilo1/kostbar"])
                    self.assertEqual(policy["URLBlocklist"], [
                        "*", "file://*", "chrome://*", f"{browser_filter}/admin", f"{browser_filter}/api/admin"])
                    self.assertFalse(policy["AllowFileSelectionDialogs"])
                    self.assertFalse(policy["RemoteDebuggingAllowed"])
                    self.assertEqual(policy["DownloadRestrictions"], 3)
                    self.assertEqual(policy["DeveloperToolsAvailability"], 2)

    def test_browser_policy_rejects_noncanonical_origins(self):
        with tempfile.TemporaryDirectory() as folder:
            profile = Path(folder) / "device.json"
            for origin in ("http://kostbar.example.org", "https://kostbar.example.org:99999",
                           "https://kostbar.example.org/admin", "https://*.example.org"):
                with self.subTest(origin=origin), self.assertRaises(subprocess.CalledProcessError):
                    profile.write_text(json.dumps({"origin": origin}), encoding="utf-8")
                    self.boot("policy", profile)


if __name__ == "__main__":
    unittest.main()
