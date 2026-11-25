"""Central application for individually authenticated KoSTbar terminals."""
import argparse
from collections import deque
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from getpass import getpass
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sys
from threading import BoundedSemaphore, Event, RLock, Thread
from time import monotonic, time

import admin_operations
import finance
import kiosk_state
import schema_migrations
import store as data
import technical_docs
from configure import config, device_profile, paypal_url, token, valid_origin, valid_terminal_id
from kiosk_state import Stage
from pi.card_types import CARD_TYPES
from policy_documents import document_body, load_documents, terms_document
from validation import admin_name, number, request_id, string, terminal_pin
from web import WsgiApp

PAIR_COOKIE = "__Host-kk_pair"
DEVICE_COOKIE = "__Host-kk_device"
PAIR_LIFETIME = 300
READER_LIFETIME = 10
DEVICE_LIFETIME = 34560000
SESSION_IDLE = 15
MANUAL_WINDOW = 900
MANUAL_LIMIT = 5
RECEIPT_SECONDS = 8
CASH_RECEIPT_SECONDS = 5
TERMINAL_ONLINE_SECONDS = 10
TERMINAL_ADMIN_ACTIONS = ("/api/admin/terminal-create", "/api/admin/terminal", "/api/admin/terminal-delete",
                          "/api/admin/terminal-profile", "/api/admin/kiosk-pair", "/api/admin/kiosk-unpair")
PREVIEW_PATH = "/api/admin/terminal-preview"
PREVIEW_QUOTE_PATH = "/api/admin/terminal-preview/quote"
PREVIEW_QR_PATH = "/api/admin/terminal-preview/paypal.svg"
PREVIEW_PAYPAL_LABEL = "KoSTbar-Testzahlung"
PAYPAL_SETTINGS_LOCK = 739310483
ADMIN_IDLE = 600
ADMIN_MAX = 8 * 3600
ADMIN_FAILURE_WINDOW = 300
ADMIN_ACCOUNT_LIMIT = 8
ADMIN_IP_LIMIT = 20
ADMIN_RATE_MAX_KEYS = 4096
ADMIN_PASSWORD_MIN = 12


@dataclass
class Terminal:
    id: str
    label: str
    secret: str
    kiosk: dict | None = None
    reader_at: float = -100
    browser_at: float = -100
    capture: dict | None = None
    reader_digest: str | None = None
    reader_seen: float = -100
    paired_browser: str | None = None
    paired_reader: str | None = None
    pairing: dict | None = None
    reader_packages: dict | None = None
    reader_packages_at: str | None = None
    lock: RLock = field(default_factory=RLock, repr=False, compare=False)


class AdminLoginLimits:
    # Access is serialized by the login lock, independently of kiosk traffic.
    def __init__(self):
        self.failures = {}
        self.next_cleanup = 0

    def check(self, account, source):
        clock = monotonic()
        cutoff = clock - ADMIN_FAILURE_WINDOW
        if clock >= self.next_cleanup:
            self.failures = {key: attempts for key, attempts in self.failures.items() if attempts and attempts[-1] > cutoff}
            self.next_cleanup = clock + 30
        keys = (("account", account.casefold()), ("ip", source))
        for key, limit in zip(keys, (ADMIN_ACCOUNT_LIMIT, ADMIN_IP_LIMIT)):
            attempts = self.failures.get(key)
            if attempts is not None:
                while attempts and attempts[0] <= cutoff:
                    attempts.popleft()
                if len(attempts) >= limit:
                    raise data.Problem(429, "Zu viele Anmeldeversuche. Versuche es in einigen Minuten erneut.")
        if len(self.failures) + sum(key not in self.failures for key in keys) > ADMIN_RATE_MAX_KEYS:
            raise data.Problem(429, "Zu viele Anmeldeversuche. Versuche es in einigen Minuten erneut.")
        return keys

    def reject(self, keys):
        clock = monotonic()
        for key in keys:
            self.failures.setdefault(key, deque()).append(clock)

    def accept(self, keys):
        self.failures.pop(keys[0], None)


class App:
    def __init__(self, db, cfg):
        self.db = db
        self.admin_state_lock = RLock()
        self.admin_write_lock = RLock()
        self.pairing_lock = RLock()
        self.policy_lock = RLock()
        try:
            self.key = bytes.fromhex(cfg["card_key"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SystemExit("card_key muss ein 32-Byte-Hexschlüssel sein.") from exc
        if len(self.key) != 32:
            raise SystemExit("card_key muss ein 32-Byte-Hexschlüssel sein.")
        self.registration = cfg.get("self_registration", True)
        if type(self.registration) is not bool:
            raise SystemExit("self_registration muss true oder false sein.")
        self.origin = cfg["origin"]
        self.host = valid_origin(self.origin)
        platform = os.environ.get("KOSTBAR_DEPLOYMENT")
        self.deployment = cfg.get("deployment", platform or "qnap")
        if self.deployment not in ("qnap", "synology") or (platform and platform != self.deployment):
            raise SystemExit("Deployment in server.json und Compose muss übereinstimmen.")
        ca_path = "/etc/kaffeekasse-terminal/nas-root.crt"
        self.reader_ca = cfg.get("reader_ca_file", ca_path if self.deployment == "qnap" else None)
        if self.reader_ca not in (None, ca_path):
            raise SystemExit("reader_ca_file muss null oder der Pfad zur Pi-CA sein.")
        configured = cfg.get("terminals", {})
        if not isinstance(configured, dict) or any(
                not valid_terminal_id(key) or not isinstance(value, dict) for key, value in configured.items()):
            raise SystemExit("Ungültige Verkaufspunktkonfiguration.")
        self.terminals = {key: Terminal(key, string(value.get("label"), 60, "Verkaufspunkt"), value.get("token"))
                          for key, value in configured.items()}
        tokens = [terminal.secret for terminal in self.terminals.values()]
        if any(not isinstance(secret, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{43,120}", secret)
               for secret in tokens) or len(set(tokens)) != len(tokens):
            raise SystemExit("Für jedes Terminal ist ein eigener zufälliger Token erforderlich.")
        self.terms = terms_document(cfg)
        self.admins = {}
        self.admin_login_lock = BoundedSemaphore(1)
        self.admin_limits = AdminLoginLimits()
        self.dummy_password = data.admin_password_hash(token())
        data.initialize(db, self.terminals, self.terms)
        with data.connect(db) as conn:
            self.terms, self.privacy = load_documents(
                conn, self.terms, self.deployment, session_idle=SESSION_IDLE, receipt_seconds=RECEIPT_SECONDS,
                cash_receipt_seconds=CASH_RECEIPT_SECONDS,
            )
            self.retired_terminals = {}
            for row in conn.execute("SELECT id,label,retired FROM terminals ORDER BY id"):
                terminal_id = row["id"]
                if row["retired"]:
                    self.terminals.pop(terminal_id, None)
                    self.retired_terminals[terminal_id] = row["label"] or terminal_id.upper()
                    continue
                if terminal_id not in self.terminals:
                    if not valid_terminal_id(terminal_id):
                        raise SystemExit("Ungültige Verkaufspunktkennung in PostgreSQL.")
                    self.terminals[terminal_id] = self.new_terminal(terminal_id, row["label"] or terminal_id.upper())
                elif row["label"]:
                    self.terminals[terminal_id].label = row["label"]
            for row in conn.execute("SELECT terminal,browser_digest,reader_digest FROM kiosk_devices"):
                terminal = self.terminals[row["terminal"]]
                terminal.paired_browser = row["browser_digest"]
                terminal.paired_reader = row["reader_digest"]
        self.version = self.terms["version"]
        self.default_paypal = paypal_url(cfg.get("paypal_url"))
        self.retention_status = {"last_success": None, "running_since": None, "failed_since": None}

    def retention_worker(self, stop):
        while not stop.is_set():
            self.retention_status = {**self.retention_status, "running_since": data.now()}
            try:
                with data.connect(self.db) as db:
                    db.execute("SET LOCAL lock_timeout='500ms'")
                    next_due = data.expire_booking_details(db, datetime.now(timezone.utc), self.key)
            except Exception as exc:
                failed_since = self.retention_status["failed_since"]
                if failed_since is None:
                    failed_since = data.now()
                    print(f"Datenbereinigung seit {failed_since} gestört ({type(exc).__name__}). Neuer Versuch folgt.",
                          file=sys.stderr, flush=True)
                self.retention_status = {**self.retention_status, "running_since": None, "failed_since": failed_since}
                delay = 5
            else:
                if self.retention_status["failed_since"]:
                    print("Datenbereinigung wieder erfolgreich.", file=sys.stderr, flush=True)
                self.retention_status = {"last_success": data.now(), "running_since": None, "failed_since": None}
                delay = max(0, min(60, (next_due - datetime.now(timezone.utc)).total_seconds()))
            stop.wait(delay)

    def terminal_labels(self):
        return {key: terminal.label for key, terminal in self.terminals.items()}

    def historical_terminal_labels(self):
        return {**self.retired_terminals, **self.terminal_labels()}

    def paypal_link(self, db):
        row = db.execute("SELECT value FROM settings WHERE key='paypal_url'").fetchone()
        return (row["value"] or None) if row else self.default_paypal

    def save_paypal_link(self, body, actor):
        if not isinstance(body.get("link"), str):
            raise data.Problem(400, "Gib einen PayPal.Me-Link oder ein leeres Feld an.")
        try:
            link = paypal_url(body["link"].strip())
        except ValueError as exc:
            raise data.Problem(400, str(exc)) from exc
        with data.connect(self.db) as db:
            db.execute("SELECT pg_advisory_xact_lock(%s)", (PAYPAL_SETTINGS_LOCK,))
            previous = self.paypal_link(db)
            db.execute("""INSERT INTO settings (key,value) VALUES ('paypal_url',%s)
                          ON CONFLICT(key) DO UPDATE SET value=excluded.value""", (link or "",))
            if link != previous:
                db.execute("""UPDATE paypal_requests SET recipient_link=%s
                              WHERE status='pending' AND recipient_link IS NULL""", (previous or "",))
                data.audit(db, actor, "PayPal-Empfängerlink geändert.",
                           {"PayPal.Me": previous or "Deaktiviert"}, {"PayPal.Me": link or "Deaktiviert"})
        return {"link": link}

    def new_terminal(self, terminal_id, label):
        secret = hmac.new(self.key, f"terminal-reader:{terminal_id}".encode("ascii"), hashlib.sha256).hexdigest()
        return Terminal(terminal_id, label, secret)

    def create_terminal(self, body, actor):
        terminal_id = body.get("id")
        if not valid_terminal_id(terminal_id):
            raise data.Problem(400, "Kennung: 1–32 Kleinbuchstaben, Ziffern oder Bindestriche. Beginne mit einem Buchstaben.")
        label = string(body.get("label"), 60, "Name des Verkaufspunkts")
        if terminal_id in self.terminals:
            raise data.Problem(409, "Diese Verkaufspunktkennung ist bereits vergeben.")
        terminal = self.new_terminal(terminal_id, label)
        with data.connect(self.db) as db:
            if not db.execute("INSERT INTO terminals (id,label) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                              (terminal_id, label)).rowcount:
                raise data.Problem(409, "Diese Verkaufspunktkennung ist bereits vergeben.")
            data.audit(db, actor, f"Verkaufspunkt {terminal_id.upper()} angelegt.", None, {"Name": label})
        self.terminals = {**self.terminals, terminal_id: terminal}
        return {"id": terminal_id, "label": label}

    def delete_terminal(self, body, actor):
        terminal = self.terminal(body.get("id"))
        with self.pairing_lock, terminal.lock:
            with data.connect(self.db) as db:
                db.execute("UPDATE terminals SET retired=TRUE,label=%s WHERE id=%s", (terminal.label, terminal.id))
                db.execute("DELETE FROM kiosk_devices WHERE terminal=%s", (terminal.id,))
                db.execute("DELETE FROM product_terminals WHERE terminal=%s", (terminal.id,))
                data.audit(db, actor, f"Verkaufspunkt {terminal.id.upper()} gelöscht.", {"Name": terminal.label}, None)
            terminal.paired_browser = terminal.paired_reader = terminal.pairing = None
            terminal.kiosk = terminal.capture = None
            self.retired_terminals = {**self.retired_terminals, terminal.id: terminal.label}
            self.terminals = {key: site for key, site in self.terminals.items() if site is not terminal}
        return {}

    def card_digest(self, uid):
        if not isinstance(uid, str) or not re.fullmatch(r"(?:[0-9A-F]{2}){4,10}", uid):
            raise data.Problem(400, "Kartenkennung nicht unterstützt.")
        return hmac.new(self.key, uid.encode("ascii"), hashlib.sha256).hexdigest()

    def clear_kiosk(self, terminal, notice=None):
        if terminal.kiosk:
            kiosk_state.reset(terminal.kiosk, notice)

    def sweep_admins(self):
        clock = monotonic()
        for key, session in list(self.admins.items()):
            if session["until"] <= clock or session["max"] <= clock:
                del self.admins[key]

    def sweep_terminal(self, terminal):
        clock = monotonic()
        if terminal.kiosk and terminal.kiosk["stage"] != Stage.IDLE and terminal.kiosk["until"] <= clock:
            self.clear_kiosk(terminal)
        if terminal.capture:
            with self.admin_state_lock:
                self.sweep_admins()
                if terminal.capture["until"] <= clock or terminal.capture["owner"] not in self.admins:
                    terminal.capture = None

    def sweep_sessions(self, stop):
        while not stop.wait(1):
            with self.admin_state_lock:
                self.sweep_admins()
            for terminal in self.terminals.values():
                if terminal.lock.acquire(blocking=False):
                    try:
                        self.sweep_terminal(terminal)
                    finally:
                        terminal.lock.release()

    def policy_documents(self):
        with self.policy_lock:
            return self.version, self.privacy["version"]

    def account(self, db, *, card=None, person=None, policies=None):
        column, value = ("p.card", card) if card is not None else ("p.id", person)
        version, privacy_version = policies or self.policy_documents()
        return db.execute(
            f"""SELECT p.id,p.first,p.card,p.card_type,p.active,m.pin_hash,COALESCE(m.temporary,FALSE) AS pin_temporary,
                EXISTS(SELECT 1 FROM policy_acceptances a WHERE a.person=p.id
                       AND a.terms_version=%s AND a.privacy_version=%s) AS accepted
                FROM people p LEFT JOIN manual_credentials m ON m.person=p.id WHERE {column}=%s""",
            (version, privacy_version, value),
        ).fetchone()

    def valid_account(self, row, session):
        if not row or not row["active"]:
            return False
        if session["manual_pin_hash"]:
            return row["pin_hash"] == session["manual_pin_hash"]
        return session["card"] is not None and row["card"] == session["card"]

    def advance_kiosk(self, session, account):
        session["stage"] = kiosk_state.account_stage(account)

    def link_kiosk_card(self, terminal, card, card_type):
        session = terminal.kiosk
        try:
            with data.connect(self.db) as db:
                data.lock_booking_account(db, session["user"])
                account = self.account(db, person=session["user"])
                if not self.valid_account(account, session):
                    self.clear_kiosk(terminal, "Bitte melde dich erneut an.")
                    return
                if kiosk_state.account_stage(account) != Stage.CARD_SETUP:
                    self.advance_kiosk(session, account)
                    return
                if (data.retired_card_active(db, card)
                        or db.execute("SELECT 1 FROM people WHERE card=%s", (card,)).fetchone()):
                    session["notice"] = "Diese Karte ist bereits zugeordnet oder gesperrt. Verwende eine andere Karte."
                    return
                db.execute("UPDATE people SET card=%s,card_type=%s WHERE id=%s", (card, card_type, account["id"]))
                data.audit(db, "Terminal", f"Karte für Konto #{account['id']} an {terminal.label} zugeordnet.",
                           None, {"Kartenzuordnung": "Erfasst"}, person=account["id"])
        except Exception as exc:
            if getattr(exc, "sqlstate", None) != "23505":
                raise
            session["notice"] = "Diese Karte ist bereits zugeordnet. Verwende eine andere Karte."
            return
        session.update(stage=Stage.PIN_SETUP, notice=None, until=monotonic() + SESSION_IDLE)

    def scan(self, terminal, uid, card_type=None):
        card = self.card_digest(uid)
        if terminal.capture:
            if not terminal.capture["card"]:
                terminal.capture["card"] = card
                terminal.capture["card_type"] = card_type
            return
        session = terminal.kiosk
        if not session or monotonic() - session["seen"] > 3:
            return
        if session["stage"] == Stage.CARD_SETUP:
            self.link_kiosk_card(terminal, card, card_type)
            return
        if session["stage"] != Stage.IDLE:
            return
        with data.connect(self.db) as db:
            row = self.account(db, card=card)
            retired = data.retired_card_active(db, card)
        if retired or (row and not row["active"]):
            self.clear_kiosk(terminal, "Diese Karte ist gesperrt. Wende dich an das Kassen-Team.")
        elif row and row["pin_temporary"]:
            self.clear_kiosk(terminal, "Melde dich ohne Ausweis mit deiner Start-PIN an und schließe die Einrichtung ab.")
        elif not row and not self.registration:
            self.clear_kiosk(terminal, "Diese Karte ist noch nicht freigeschaltet.")
        else:
            session.update(stage=Stage.REGISTER, card=card, card_type=card_type, notice=None, user=row["id"] if row else None,
                           until=monotonic() + SESSION_IDLE, visit=token(), manual_pin_hash=None)
            if row:
                if card_type and not row["card_type"]:
                    with data.connect(self.db) as db:
                        db.execute("UPDATE people SET card_type=%s WHERE id=%s AND card_type IS NULL",
                                   (card_type, row["id"]))
                self.advance_kiosk(session, row)

    def pin_material(self, pin):
        return hmac.new(self.key, ("manual-pin:" + pin).encode(), hashlib.sha256).hexdigest()

    def confirmed_pin_hash(self, body):
        pin = terminal_pin(body.get("pin"))
        confirmation = terminal_pin(body.get("pin_confirmation"))
        if pin != confirmation:
            raise data.Problem(400, "Die PIN und ihre Bestätigung stimmen nicht überein.")
        return data.password_hash(self.pin_material(pin))

    def manual_login(self, terminal, body):
        user = number(body.get("id"), 1, 2**31 - 1, "Konto")
        pin = terminal_pin(body.get("pin"))
        clock = int(time())
        success = False
        with data.connect(self.db) as db:
            db.execute("SELECT id FROM people WHERE id=%s FOR NO KEY UPDATE", (user,))
            account = self.account(db, person=user)
            if not account or not account["active"] or not account["pin_hash"]:
                raise data.Problem(401, "Name oder PIN stimmt nicht.")
            rate = db.execute("SELECT attempts,expires FROM manual_attempts WHERE person=%s", (user,)).fetchone()
            if rate and rate["expires"] > clock and rate["attempts"] >= MANUAL_LIMIT:
                raise data.Problem(429, "Zu viele Versuche. Warte 15 Minuten oder halte deinen Ausweis an.")
            success = data.check_password(self.pin_material(pin), account["pin_hash"])
            if success:
                db.execute("DELETE FROM manual_attempts WHERE person=%s", (user,))
            else:
                attempts = rate["attempts"] + 1 if rate and rate["expires"] > clock else 1
                expires = (rate["expires"] if rate and rate["expires"] > clock and attempts < MANUAL_LIMIT
                           else clock + MANUAL_WINDOW)
                db.execute("""INSERT INTO manual_attempts VALUES (%s,%s,%s)
                              ON CONFLICT(person) DO UPDATE SET attempts=excluded.attempts,expires=excluded.expires""",
                           (user, attempts, expires))
        if not success:
            if attempts >= MANUAL_LIMIT:
                raise data.Problem(429, "Zu viele Versuche. Warte 15 Minuten oder halte deinen Ausweis an.")
            raise data.Problem(401, "Name oder PIN stimmt nicht.")
        session = terminal.kiosk
        session.update(user=user, manual_pin_hash=account["pin_hash"], card=None, visit=token(),
                       notice=None, until=monotonic() + SESSION_IDLE)
        self.advance_kiosk(session, account)

    def state(self, terminal, *, include_catalog=False):
        session = terminal.kiosk
        policies = self.policy_documents()
        profile = None
        booking = None
        catalog = None
        account = None
        if session["stage"] in (Stage.SHOP, Stage.CONSENT, Stage.CARD_SETUP, Stage.PIN_SETUP):
            with data.connect(self.db) as db:
                account = self.account(db, person=session["user"], policies=policies)
                if not self.valid_account(account, session):
                    self.clear_kiosk(terminal, "Dieses Konto ist gesperrt oder der Zugang wurde geändert.")
                else:
                    self.advance_kiosk(session, account)
                    if session["stage"] == Stage.SHOP:
                        profile = {"first": account["first"], "balance": data.balance(db, session["user"]),
                                   "loyalty": data.loyalty_card(db, session["user"])}
                        booking = data.pending_kiosk_booking(db, session["user"])
                        if booking and booking["kind"] == "purchase":
                            booking["bonus"] = data.purchase_bonus(db, booking["entry"])
                        if include_catalog and not booking:
                            catalog = data.product_catalog(db, terminal.id)
        remaining = max(0, session["until"] - monotonic())
        result = {"stage": session["stage"], "notice": session["notice"], "visit": session["visit"],
                  "remaining": remaining, "terminal": terminal.label, "version": policies[0],
                  "privacy_version": policies[1],
                  "reader": monotonic() - terminal.reader_at < 8, "maintenance": bool(terminal.capture)}
        if profile is not None:
            result["profile"] = profile
        if booking:
            result["booking"] = booking
        if catalog is not None:
            result["catalog"] = catalog
        if session["stage"] == Stage.RECEIPT:
            result["receipt"] = session["receipt"]
        if session["stage"] == Stage.PIN_SETUP:
            result["pin_temporary"] = account["pin_temporary"]
        return result

    def require_account(self, db, terminal, *, accepted=True, policies=None):
        session = terminal.kiosk
        account = self.account(db, person=session["user"], policies=policies)
        if not self.valid_account(account, session):
            self.clear_kiosk(terminal)
            raise data.Problem(403, "Dieses Konto ist gesperrt oder der Zugang wurde geändert.")
        if accepted and kiosk_state.account_stage(account) != Stage.SHOP:
            self.advance_kiosk(session, account)
            message = ("Bitte bestätige zuerst die aktuellen Nutzungsbedingungen und die Datenschutzerklärung."
                       if not account["accepted"] else "Schließe zuerst die Einrichtung deines Kontos ab.")
            raise data.Problem(409, message)
        return account

    def kiosk_consent(self, terminal, body, registration):
        session = terminal.kiosk
        policies = self.policy_documents()
        if body.get("accepted") is not True or (body.get("version"), body.get("privacy_version")) != policies:
            raise data.Problem(400, "Akzeptiere die aktuellen Nutzungsbedingungen und bestätige die Kenntnisnahme der Datenschutzerklärung.")
        with data.connect(self.db) as db:
            if registration:
                if data.retired_card_active(db, session["card"]):
                    raise data.Problem(403, "Diese Karte ist gesperrt.")
                first = string(body.get("first"), 60, "Vorname")
                last = string(body.get("last"), 60, "Nachname")
                department = string(body.get("department"), 80, "Referat")
                pin_hash = self.confirmed_pin_hash(body)
                person = db.execute(
                    """INSERT INTO people (card,first,last,department,created,card_type) VALUES (%s,%s,%s,%s,%s,%s)
                       ON CONFLICT(card) DO NOTHING RETURNING id""",
                    (session["card"], first, last, department, data.now(), session["card_type"]),
                ).fetchone()
                if not person:
                    self.clear_kiosk(terminal)
                    raise data.Problem(409, "Dieses Konto wurde bereits angelegt. Halte die Karte erneut an.")
                db.execute("INSERT INTO manual_credentials (person,pin_hash) VALUES (%s,%s)",
                           (person["id"], pin_hash))
            else:
                data.lock_booking_account(db, session["user"])
                person = self.require_account(db, terminal, accepted=False, policies=policies)
            data.accept_policies(db, person["id"], *policies, terminal.id)
        session.update(stage=Stage.CONSENT, user=person["id"], until=monotonic() + SESSION_IDLE)
        return self.state(terminal), None

    def kiosk_payment(self, terminal, path, body):
        session = terminal.kiosk
        user = session["user"]
        key = request_id(body.get("request"))
        cents = number(body.get("cents"), 1, 1000000, "Zahlungsbetrag")
        if path == "/api/kiosk/cash" and cents > finance.CASH_MAX_CENTS:
            raise data.Problem(400, "Barzahlungen am Terminal sind bis 100 € pro Vorgang möglich.")
        if path == "/api/kiosk/cash" and session["stage"] == Stage.RECEIPT and session["committed"] == "cash:" + key:
            if session["receipt"]["total"] != cents:
                raise data.Problem(409, "Die Zahlung wurde bereits mit einem anderen Betrag gebucht.")
            return self.state(terminal), None
        if session["stage"] != Stage.SHOP:
            raise data.Problem(409, "Melde dich an, um eine Zahlung zu buchen.")
        with data.connect(self.db) as db:
            kind = "paypal" if path == "/api/kiosk/paypal" else "cash"
            data.lock_booking_account(db, user)
            self.require_account(db, terminal)
            data.check_pending_kiosk_booking(db, user, kind, key)
            if path == "/api/kiosk/paypal":
                db.execute("SELECT pg_advisory_xact_lock_shared(%s)", (PAYPAL_SETTINGS_LOCK,))
                link = self.paypal_link(db)
                if not link:
                    raise data.Problem(409, "PayPal ist für diesen Verkaufspunkt nicht eingerichtet.")
                if body.get("link", link) != link:
                    raise data.Problem(409, "Der PayPal-Link wurde geändert. Öffne die Zahlungsoptionen erneut.")
                ref = finance.paypal_prepare(db, user, terminal.id, key, cents, link=link)
                return {"reference": ref, "cents": cents}, None
            receipt = finance.cash(db, user, terminal.id, key, cents)
        receipt["request"] = key
        session.update(stage=Stage.RECEIPT, receipt=receipt, committed="cash:" + key,
                       until=monotonic() + CASH_RECEIPT_SECONDS)
        return self.state(terminal), None

    def kiosk_route(self, terminal, method, path, body, cookies, query=None):
        session = terminal.kiosk
        if path == "/api/kiosk/state" and method == "GET":
            if not session or cookies.get("kk_kiosk") != session["token"]:
                if session and monotonic() - session["seen"] <= 3:
                    raise data.Problem(409, "Das Terminal ist bereits in einem anderen Fenster geöffnet.")
                terminal.kiosk = {"token": token(), "seen": monotonic()}
                self.clear_kiosk(terminal)
            terminal.kiosk["seen"] = monotonic()
            state = self.state(terminal)
            terminal.browser_at = monotonic()
            return state, self.cookie("kk_kiosk", terminal.kiosk["token"], "/api/kiosk", secure=True)
        if not session or cookies.get("kk_kiosk") != session["token"]:
            raise data.Problem(401, "Die Terminalsitzung ist abgelaufen.")
        if method == "GET" and path in ("/api/kiosk/payment", "/api/kiosk/paypal.svg"):
            if session["stage"] != Stage.SHOP:
                raise data.Problem(403, "Bitte melde dich an.")
            query = query or {}
            with data.connect(self.db, snapshot=True) as db:
                self.require_account(db, terminal)
                link = self.paypal_link(db)
                if path == "/api/kiosk/payment":
                    pending = finance.paypal_for_person(db, session["user"])
                    for item in pending:
                        recipient = item.pop("recipient_link")
                        item["link"] = (link if recipient is None else recipient or None) if link else None
                    return {"link": link, "cash_max": finance.CASH_MAX_CENTS,
                            "pending": pending}, None
                if link and (reference := query.get("reference", [None])[0]):
                    payment = db.execute("""SELECT recipient_link FROM paypal_requests
                                            WHERE person=%s AND reference=%s AND status='pending' AND created>%s""",
                                         (session["user"], reference, data.booking_cutoff())).fetchone()
                    if not payment:
                        raise data.Problem(404, "PayPal-Meldung nicht gefunden.")
                    if payment["recipient_link"] is not None:
                        link = payment["recipient_link"]
            if not link:
                raise data.Problem(404, "PayPal ist nicht eingerichtet.")
            if query.get("link", [link])[0] != link:
                raise data.Problem(409, "Der PayPal-Link wurde geändert. Öffne die Zahlungsoptionen erneut.")
            return finance.paypal_qr(link), None
        if method != "POST":
            raise data.Problem(404, "Seite nicht gefunden.")
        if path == "/api/kiosk/manual-start":
            if session["stage"] != Stage.IDLE or terminal.capture:
                raise data.Problem(409, "Das Terminal ist gerade belegt.")
            session.update(stage=Stage.MANUAL, visit=token(), until=monotonic() + SESSION_IDLE, notice=None)
            return self.state(terminal), None
        if path in ("/api/kiosk/manual-search", "/api/kiosk/manual-login"):
            if (session["stage"] != Stage.MANUAL or terminal.capture
                    or not isinstance(body.get("visit"), str) or body["visit"] != session["visit"]):
                raise data.Problem(409, "Die manuelle Anmeldung ist abgelaufen. Beginne erneut.")
            if path.endswith("search"):
                search = string(body.get("query"), 120, "Name")
                with data.connect(self.db) as db:
                    return {"people": data.manual_people(db, search) if len(search) >= 2 else []}, None
            self.manual_login(terminal, body)
            return self.state(terminal, include_catalog=True), None
        if not isinstance(body.get("visit"), str) or body["visit"] != session["visit"]:
            raise data.Problem(409, "Die Sitzung hat gewechselt. Bitte melde dich erneut an.")
        if path == "/api/kiosk/logout":
            self.clear_kiosk(terminal)
            return self.state(terminal), None
        if path == "/api/kiosk/activity" and session["stage"] in kiosk_state.ACTIVITY_STAGES:
            session["until"] = monotonic() + SESSION_IDLE
            return {"remaining": SESSION_IDLE}, None
        if path == "/api/kiosk/booking-seen" and session["stage"] in (Stage.SHOP, Stage.RECEIPT):
            key = request_id(body.get("request"))
            kind = body.get("kind")
            if kind not in ("purchase", "cash", "paypal"):
                raise data.Problem(400, "Unbekannte Buchungsart.")
            with data.connect(self.db) as db:
                self.require_account(db, terminal)
                data.acknowledge_kiosk_booking(db, session["user"], kind, key)
            return {}, None
        required_stage = kiosk_state.STAGE_ACTIONS.get(path)
        if required_stage and session["stage"] != required_stage:
            raise data.Problem(409, "Diese Aktion ist in der aktuellen Sitzung nicht verfügbar.")
        if path == "/api/kiosk/register":
            return self.kiosk_consent(terminal, body, registration=True)
        if path == "/api/kiosk/accept-terms":
            return self.kiosk_consent(terminal, body, registration=False)
        if path == "/api/kiosk/pin-setup":
            pin_hash = self.confirmed_pin_hash(body)
            with data.connect(self.db) as db:
                data.lock_booking_account(db, session["user"])
                account = self.require_account(db, terminal, accepted=False)
                if kiosk_state.account_stage(account) != Stage.PIN_SETUP:
                    raise data.Problem(409, "Die PIN kann erst nach Zustimmung und Kartenzuordnung eingerichtet werden.")
                if account["pin_temporary"] and data.check_password(self.pin_material(body["pin"]), account["pin_hash"]):
                    raise data.Problem(400, "Wähle eine andere PIN als deine Start-PIN.")
                db.execute("""INSERT INTO manual_credentials (person,pin_hash) VALUES (%s,%s)
                              ON CONFLICT(person) DO UPDATE SET pin_hash=excluded.pin_hash,temporary=FALSE""",
                           (session["user"], pin_hash))
            if session["manual_pin_hash"] is not None:
                session["manual_pin_hash"] = pin_hash
            session["until"] = monotonic() + SESSION_IDLE
            return self.state(terminal), None
        if path in ("/api/kiosk/cash", "/api/kiosk/paypal"):
            return self.kiosk_payment(terminal, path, body)
        if path == "/api/kiosk/history":
            if session["stage"] != Stage.SHOP:
                raise data.Problem(403, "Bitte melde dich an.")
            current, _, _ = finance.month_bounds(None)
            month, start, end = finance.month_bounds(body.get("month"))
            if month > current:
                raise data.Problem(400, "Dieser Monat liegt in der Zukunft.")
            before = body.get("before")
            if before is not None:
                before = number(before, 1, 2**53 - 1, "Seitengrenze")
            with data.connect(self.db, snapshot=True) as db:
                self.require_account(db, terminal)
                cutoff = data.booking_cutoff()
                oldest = db.execute("SELECT MIN(at) AS at FROM journal WHERE person=%s AND at>%s",
                                    (session["user"], cutoff)).fetchone()["at"]
                entries = data.personal_history(db, session["user"], start, end, before, cutoff=cutoff)
            return {**entries, "month": month, "current": current, "terminals": self.historical_terminal_labels(),
                    "oldest": finance.local_date(oldest).strftime("%Y-%m") if oldest else current}, None
        if path == "/api/kiosk/checkout-quote":
            if session["stage"] != Stage.SHOP:
                raise data.Problem(403, "Bitte melde dich an.")
            cart = self.checkout_cart(body)
            with data.connect(self.db, snapshot=True) as db:
                self.require_account(db, terminal)
                quote = data.purchase_pricing(db, session["user"], cart, terminal.id)
            quote.pop("loyalty_delta")
            return quote, None
        if path == "/api/kiosk/checkout":
            return self.kiosk_checkout(terminal, body)
        raise data.Problem(409, "Diese Aktion ist in der aktuellen Sitzung nicht verfügbar.")

    @staticmethod
    def checkout_cart(body):
        lines = body.get("lines")
        if not isinstance(lines, list) or not 1 <= len(lines) <= 100:
            raise data.Problem(400, "Der Warenkorb ist leer oder zu groß.")
        cart = []
        for line in lines:
            if not isinstance(line, dict):
                raise data.Problem(400, "Ungültiger Warenkorb.")
            cart.append((number(line.get("id"), 1, 2**31 - 1, "Produkt"),
                         number(line.get("qty"), 1, 99, "Anzahl"),
                         number(line.get("cents"), 1, 100000, "Preis")))
        if len({line[0] for line in cart}) != len(cart):
            raise data.Problem(400, "Doppelte Warenkorbposition.")
        return sorted(cart)

    def kiosk_checkout(self, terminal, body):
        session = terminal.kiosk
        key = request_id(body.get("request"))
        receipt_retry = session["stage"] == Stage.RECEIPT and key == session["committed"]
        if session["stage"] != Stage.SHOP and not receipt_retry:
            raise data.Problem(409, "Die Einkaufssitzung ist beendet.")
        cart = self.checkout_cart(body)
        discount = body.get("discount")
        if discount is not None:
            discount = number(discount, 0, 990_000_000, "Bonusbetrag")
        if receipt_retry:
            if cart != session["receipt_cart"]:
                raise data.Problem(409, "Die Buchungskennung gehört zu einem anderen Warenkorb.")
            data.check_purchase_discount(discount, sum(
                line["price"] * line["qty"] for line in session["receipt"].get("bonus", [])
            ))
            return self.state(terminal), None
        with data.connect(self.db) as db:
            data.lock_booking_account(db, session["user"])
            self.require_account(db, terminal)
            data.check_pending_kiosk_booking(db, session["user"], "purchase", key)
            receipt = data.purchases(db, session["user"], key, cart, terminal.id, quoted_discount=discount)
            if receipt.get("stamps_earned") or receipt.get("bonus"):
                receipt["loyalty"] = data.loyalty_card(db, session["user"])
        receipt["request"] = key
        session.update(stage=Stage.RECEIPT, receipt=receipt, committed=key, receipt_cart=cart,
                       until=monotonic() + RECEIPT_SECONDS)
        return self.state(terminal), None

    def cookie(self, name, value, path, secure=False, delete=False):
        return f"{name}={value}; Path={path}; HttpOnly; SameSite=Strict" + (
            "; Secure" if secure else ""
        ) + ("; Max-Age=0" if delete else "")

    def device_digest(self, purpose, value):
        if isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value):
            return hmac.new(self.key, f"{purpose}:{value}".encode(), hashlib.sha256).hexdigest()
        return None

    def browser_terminal(self, cookies):
        digest = self.device_digest("browser", cookies.get(DEVICE_COOKIE))
        return next((t for t in self.terminals.values() if digest and t.paired_browser == digest), None)

    def live_pairing(self, terminal):
        pairing = terminal.pairing
        if pairing and pairing["until"] > monotonic():
            return pairing
        terminal.pairing = None
        return None

    def pairing_route(self, body, cookies):
        if self.browser_terminal(cookies):
            return {"paired": True}, self.device_cookie(cookies[DEVICE_COOKIE])
        secret = cookies.get(PAIR_COOKIE)
        digest = self.device_digest("pairing", secret)
        browser_digest = self.device_digest("browser", secret)
        if browser_digest and any(t.paired_browser == browser_digest for t in self.terminals.values()):
            return {"paired": True}, self.device_cookie(secret)
        for terminal in self.terminals.values():
            pairing = self.live_pairing(terminal)
            if pairing and digest and pairing["digest"] == digest:
                if pairing["approved"]:
                    with terminal.lock:
                        if (terminal.paired_browser or not self.reader_matches(terminal, pairing["reader"])
                                or any(other.paired_reader == pairing["reader"] for other in self.terminals.values())):
                            raise data.Problem(409, "Der Leserdienst ist nicht erreichbar oder bereits gekoppelt.")
                        with data.connect(self.db) as db:
                            db.execute("INSERT INTO kiosk_devices VALUES (%s,%s,%s)",
                                       (terminal.id, browser_digest, pairing["reader"]))
                            data.audit(db, pairing["actor"], f"Terminal {terminal.id.upper()} gekoppelt.",
                                       None, {"Verkaufspunkt": terminal.label})
                        terminal.paired_reader = pairing["reader"]
                        terminal.paired_browser = browser_digest
                        terminal.pairing = None
                    return {"paired": True}, self.device_cookie(secret)
                return self.pairing_info(terminal, pairing), None
        reader = self.device_digest("reader", body.get("instance"))
        matches = [terminal for terminal in self.terminals.values() if self.reader_matches(terminal, reader)]
        if len(matches) != 1:
            raise data.Problem(409, "Warte auf den Leserdienst dieses Pi. Prüfe das Geräteprofil und den Dienststatus.")
        terminal = matches[0]
        if terminal.paired_browser:
            raise data.Problem(409, "Dieser Verkaufspunkt ist bereits gekoppelt. Die Zuordnung kann in der Verwaltung gelöst werden.")
        if self.live_pairing(terminal):
            raise data.Problem(409, "Für diesen Verkaufspunkt läuft bereits eine Kopplung. Warte auf deren Ablauf.")
        secret = secrets.token_hex(32)
        active_codes = {pending["code"] for t in self.terminals.values() if (pending := self.live_pairing(t))}
        code = f"{secrets.randbelow(100_000_000):08d}"
        while code in active_codes:
            code = f"{secrets.randbelow(100_000_000):08d}"
        pairing = {"digest": self.device_digest("pairing", secret), "reader": reader,
                   "code": code, "until": monotonic() + PAIR_LIFETIME,
                   "approved": False}
        terminal.pairing = pairing
        return self.pairing_info(terminal, pairing), self.cookie(PAIR_COOKIE, secret, "/", secure=True) + f"; Max-Age={PAIR_LIFETIME}"

    def device_cookie(self, secret):
        return self.cookie(DEVICE_COOKIE, secret, "/", secure=True) + f"; Max-Age={DEVICE_LIFETIME}"

    def reader_matches(self, terminal, digest):
        return bool(digest and terminal.reader_digest == digest and monotonic() - terminal.reader_seen < READER_LIFETIME)

    @staticmethod
    def pairing_info(terminal, pairing):
        return {"code": pairing["code"], "site": terminal.id.upper(), "label": terminal.label}

    def manage_pairing(self, path, body, actor):
        terminal = self.terminal(body.get("id"))
        with terminal.lock:
            return self.update_pairing(terminal, path, body, actor)

    def update_pairing(self, terminal, path, body, actor):
        if path == "/api/admin/kiosk-pair":
            pairing = self.live_pairing(terminal)
            code = body.get("code")
            if (terminal.paired_browser or not pairing or not isinstance(code, str)
                    or not re.fullmatch(r"[0-9]{8}", code)
                    or not hmac.compare_digest(code, pairing["code"])
                    or not self.reader_matches(terminal, pairing["reader"])):
                raise data.Problem(409, "Der Code passt nicht zu diesem Verkaufspunkt oder ist abgelaufen.")
            pairing.update(approved=True, actor=actor)
        else:
            with data.connect(self.db) as db:
                if db.execute("DELETE FROM kiosk_devices WHERE terminal=%s", (terminal.id,)).rowcount:
                    data.audit(db, actor, f"Kopplung von Terminal {terminal.id.upper()} aufgehoben.",
                               {"Verkaufspunkt": terminal.label}, None)
            terminal.paired_browser = terminal.paired_reader = terminal.pairing = None
            terminal.kiosk = terminal.capture = None
            terminal.browser_at = terminal.reader_at = -100
        return {}, None

    def login(self, body, source_ip):
        user, password = body.get("name"), body.get("password")
        if not isinstance(user, str) or not isinstance(password, str) or len(user) > 32 or len(password) > 256:
            raise data.Problem(400, "Ungültige Anmeldedaten.")
        try:
            admin_name(user)
        except ValueError:
            raise data.Problem(401, "Anmeldename oder Passwort ist falsch.") from None
        if not self.admin_login_lock.acquire(blocking=False):
            raise data.Problem(503, "Eine Anmeldung läuft bereits. Versuche es gleich erneut.")
        try:
            keys = self.admin_limits.check(user, source_ip)
            with data.connect(self.db) as db:
                row = db.execute("SELECT password,super_admin FROM admins WHERE name=%s", (user,)).fetchone()
            record = row["password"] if row else self.dummy_password
            if not data.check_admin_password(password, record) or not row:
                self.admin_limits.reject(keys)
                raise data.Problem(401, "Anmeldename oder Passwort ist falsch.")
            if not record.startswith(data.ADMIN_HASH_PREFIX):
                upgraded = data.admin_password_hash(password)
                with data.connect(self.db) as db:
                    data.lock_admins(db)
                    changed = db.execute(
                        "UPDATE admins SET password=%s WHERE name=%s AND password=%s AND super_admin=%s",
                        (upgraded, user, record, row["super_admin"]),
                    ).rowcount
                if not changed:
                    raise data.Problem(401, "Die Zugangsdaten wurden geändert. Bitte melde dich erneut an.")
                record = upgraded
            self.admin_limits.accept(keys)
        finally:
            self.admin_login_lock.release()
        clock = monotonic()
        key = token()
        with self.admin_state_lock:
            self.sweep_admins()
            self.admins[key] = {"name": user, "until": clock + ADMIN_IDLE, "max": clock + ADMIN_MAX,
                                "password": record, "super_admin": bool(row["super_admin"])}
        return {"name": user, "super_admin": bool(row["super_admin"])}, self.cookie("kk_admin", key, "/api/admin", secure=True)

    @staticmethod
    def new_admin_password(body):
        password = body.get("password")
        if not isinstance(password, str) or not ADMIN_PASSWORD_MIN <= len(password) <= 256 or body.get("repeat") != password:
            raise data.Problem(400, f"Das Passwort muss {ADMIN_PASSWORD_MIN} bis 256 Zeichen haben und mit der Wiederholung übereinstimmen.")
        return password

    def manage_admin(self, path, body, session):
        actor = session["name"]
        with data.connect(self.db) as db:
            data.lock_admins(db)
            operator = data.admin_snapshot(db, actor)
            saved = db.execute("SELECT password FROM admins WHERE name=%s", (actor,)).fetchone()
            if not operator or not saved or saved["password"] != session["password"]:
                raise data.Problem(401, "Bitte melde dich erneut an.")
            if path != "/api/admin/change-password" and not operator["super_admin"]:
                raise data.Problem(403, "Diese Aktion ist dem Super-Admin vorbehalten.")
            operator_label = " ".join(part for part in (operator["first"], operator["last"]) if part)
            if path == "/api/admin/change-password":
                current = body.get("current")
                password = self.new_admin_password(body)
                if not isinstance(current, str) or len(current) > 256 or not data.check_admin_password(current, saved["password"]):
                    raise data.Problem(400, "Das bisherige Passwort stimmt nicht.")
                if current == password:
                    raise data.Problem(400, "Wähle ein anderes neues Passwort.")
                db.execute("UPDATE admins SET password=%s WHERE name=%s", (data.admin_password_hash(password), actor))
                data.audit(db, actor, "Eigenes Passwort geändert.",
                           {"Passwort": "Bisheriges Passwort"}, {"Passwort": "Neues Passwort"})
                return actor
            try:
                name = admin_name(body.get("name") if isinstance(body.get("name"), str) else "")
                previous = admin_name(body.get("previous", name)) if path == "/api/admin/edit-admin" else name
            except (ValueError, TypeError) as exc:
                raise data.Problem(400, "Anmeldename: 3–32 Kleinbuchstaben, Ziffern, Punkte, Minus oder Unterstriche.") from exc
            old = data.admin_snapshot(db, previous)
            before = data.admin_snapshot_labels(old)
            if path == "/api/admin/remove-admin":
                if not old:
                    raise data.Problem(404, "Administratorkonto nicht gefunden.")
                if old["super_admin"]:
                    raise data.Problem(409, "Weise die Super-Admin-Rolle zuerst einem anderen Konto zu.")
                db.execute("DELETE FROM admins WHERE name=%s", (name,))
                data.audit(db, actor, f"Administratorkonto {name} gelöscht.", before, None)
                return name
            if path == "/api/admin/reset-admin-password":
                if not old:
                    raise data.Problem(404, "Administratorkonto nicht gefunden.")
                password = self.new_admin_password(body)
                db.execute("UPDATE admins SET password=%s WHERE name=%s", (data.admin_password_hash(password), name))
                data.audit(db, actor, f"Passwort für Administratorkonto {name} zurückgesetzt.",
                           {"Anmeldename": name, "Passwort": "Bisheriges Passwort"},
                           {"Anmeldename": name, "Passwort": "Neues Passwort"})
                return name
            first = string(body.get("first"), 60, "Vorname")
            last = string(body.get("last"), 60, "Nachname")
            desc = body.get("description", "")
            description = "" if isinstance(desc, str) and not desc.strip() else string(desc, 240, "Beschreibung")
            if path == "/api/admin/add-admin":
                password = self.new_admin_password(body)
                if not db.execute("""INSERT INTO admins (name,password,first,last,description) VALUES (%s,%s,%s,%s,%s)
                                     ON CONFLICT DO NOTHING""",
                                  (name, data.admin_password_hash(password), first, last, description)).rowcount:
                    raise data.Problem(409, "Dieser Adminname ist bereits vergeben.")
                detail = f"Administratorkonto {name} angelegt."
            else:
                if not old:
                    raise data.Problem(404, "Administratorkonto nicht gefunden.")
                if name != previous and data.admin_snapshot(db, name):
                    raise data.Problem(409, "Dieser Adminname ist bereits vergeben.")
                db.execute("UPDATE admins SET name=%s,first=%s,last=%s,description=%s WHERE name=%s",
                           (name, first, last, description, previous))
                detail = f"Administratorkonto {previous} bearbeitet."
            after = data.admin_snapshot_labels(data.admin_snapshot(db, name))
            data.audit(db, actor, detail, before, after, actor_label=operator_label)
            return previous if name != previous else None

    def admin_route(self, method, path, query, body, cookies, caddy_version):
        with self.admin_write_lock if method == "POST" and path != PREVIEW_QUOTE_PATH else nullcontext():
            return self.authorized_admin_route(method, path, query, body, cookies, caddy_version)

    def authorized_admin_route(self, method, path, query, body, cookies, caddy_version):
        key = cookies.get("kk_admin")
        with self.admin_state_lock:
            self.sweep_admins()
            session = self.admins.get(key)
        if not session:
            raise data.Problem(401, "Bitte melde dich an.")
        with data.connect(self.db) as db:
            credential = db.execute("SELECT password,super_admin FROM admins WHERE name=%s", (session["name"],)).fetchone()
        with self.admin_state_lock:
            self.sweep_admins()
            if (self.admins.get(key) is not session or not credential or credential["password"] != session["password"]
                    or bool(credential["super_admin"]) != session["super_admin"]):
                self.admins.pop(key, None)
                raise data.Problem(401, "Bitte melde dich erneut an.")
            if path not in ("/api/admin/capture-status", "/api/admin/terminal-status", PREVIEW_PATH):
                session["until"] = monotonic() + ADMIN_IDLE
        actor = session["name"]
        if not session["super_admin"] and (
            path in (*TERMINAL_ADMIN_ACTIONS, "/api/admin/paypal-settings", "/api/admin/delete-product", PREVIEW_PATH)
            or path.startswith(PREVIEW_PATH + "/")
        ):
            raise data.Problem(403, "Diese Funktion ist dem Super-Admin vorbehalten.")
        if method == "GET":
            return self.admin_read(path, query, key, session, caddy_version), None
        if method != "POST":
            raise data.Problem(404, "Seite nicht gefunden.")
        if path == "/api/admin/logout":
            with self.admin_state_lock:
                self.admins.pop(key, None)
            return {}, self.cookie("kk_admin", "", "/api/admin", secure=True, delete=True)
        if path in ("/api/admin/kiosk-pair", "/api/admin/kiosk-unpair"):
            with self.pairing_lock:
                return self.manage_pairing(path, body, actor)
        if path.startswith("/api/admin/capture-"):
            return self.capture_action(path, body, key, actor), None
        if path in ("/api/admin/add-admin", "/api/admin/edit-admin", "/api/admin/remove-admin",
                    "/api/admin/change-password", "/api/admin/reset-admin-password"):
            revoked = self.manage_admin(path, body, session)
            if revoked:
                with self.admin_state_lock:
                    for session_key, active in list(self.admins.items()):
                        if active["name"] == revoked:
                            del self.admins[session_key]
                if revoked == actor:
                    return {"relogin": True}, self.cookie("kk_admin", "", "/api/admin", secure=True, delete=True)
            return {}, None
        if path == "/api/admin/terminal-create":
            return self.create_terminal(body, actor), None
        if path == "/api/admin/person-create":
            with data.connect(self.db) as db:
                return admin_operations.create_person(db, body, actor, self.confirmed_pin_hash(body)), None
        if path == "/api/admin/terminal-delete":
            return self.delete_terminal(body, actor), None
        if path == "/api/admin/paypal-settings":
            return self.save_paypal_link(body, actor), None
        if path == PREVIEW_QUOTE_PATH:
            terminal = self.terminal(query.get("terminal", [""])[0])
            cart = self.checkout_cart(body)
            progress = number(body.get("progress"), 0, 2**31 - 1, "Sammelkartenstand")
            with data.connect(self.db, snapshot=True) as db:
                quote = data.price_cart(data.available_products(db, terminal.id), cart, lambda: progress)
            return quote, None
        if path == "/api/admin/terminal":
            terminal = self.terminal(body.get("id"))
            label = string(body.get("label"), 60, "Name des Verkaufspunkts")
            if label != terminal.label:
                with data.connect(self.db) as db:
                    db.execute("UPDATE terminals SET label=%s WHERE id=%s", (label, terminal.id))
                    data.audit(db, actor, f"Verkaufspunkt {terminal.id.upper()} umbenannt.",
                               {"Name": terminal.label}, {"Name": label})
                terminal.label = label
            return {}, None
        if path == "/api/admin/terms":
            draft = document_body(body)
            if body.get("base") != self.version:
                raise data.Problem(409, "Eine andere Fassung wurde veröffentlicht. Lade die Ansicht neu.")
            if data.terms_body(self.terms) != draft:
                with data.connect(self.db) as db:
                    document = data.publish_terms(db, draft, actor, self.terms)
                with self.policy_lock:
                    self.terms, self.version = document, document["version"]
            return self.terms, None
        if path == "/api/admin/privacy":
            draft = document_body(body)
            stand = body.get("date")
            try:
                if not isinstance(stand, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", stand):
                    raise ValueError
                date.fromisoformat(stand)
            except ValueError as exc:
                raise data.Problem(400, "Gib ein gültiges Standdatum an.") from exc
            if body.get("base") != self.privacy["version"]:
                raise data.Problem(409, "Die Datenschutzerklärung wurde inzwischen geändert. Lade die Ansicht neu.")
            if (draft, stand) != (self.privacy["body"], self.privacy["date"]):
                document = {"version": secrets.token_hex(12), "date": stand, "body": draft,
                            "template": bool(re.search(r"\[\s*EINTRAGEN\s*:", draft, re.IGNORECASE))}
                with data.connect(self.db) as db:
                    data.publish_privacy(db, document, actor, self.privacy)
                with self.policy_lock:
                    self.privacy = document
            return self.privacy, None
        invalidate = None
        with data.connect(self.db) as db:
            if path == "/api/admin/product":
                admin_operations.save_product(db, body, actor, self.terminal_labels())
            elif path == "/api/admin/product-status":
                admin_operations.set_product_status(db, body, actor, self.terminal_labels())
            elif path == "/api/admin/delete-product":
                admin_operations.hide_product(db, body, actor, self.terminal_labels())
            elif path == "/api/admin/reset-pin":
                invalidate = admin_operations.reset_pin(db, body, actor, self.confirmed_pin_hash)
            elif path == "/api/admin/paypal-confirm":
                admin_operations.confirm_paypal(db, body, actor, self.key)
            elif path == "/api/admin/paypal-reject":
                admin_operations.reject_paypal(db, body, actor, self.key)
            elif path == "/api/admin/person":
                invalidate = admin_operations.edit_person(db, body, actor)
            elif path == "/api/admin/close-account":
                invalidate = admin_operations.close_account(db, body, actor)
            elif path == "/api/admin/adjust":
                admin_operations.adjust_balance(db, body, actor)
            elif path == "/api/admin/reverse":
                admin_operations.reverse_purchase(db, body, actor)
            else:
                raise data.Problem(404, "Seite nicht gefunden.")
        if invalidate:
            # Kiosk requests acquire their terminal lock before opening a transaction.
            # Invalidate RAM only after the database transaction has released its locks.
            for terminal in self.terminals.values():
                with terminal.lock:
                    if terminal.kiosk and terminal.kiosk["user"] == invalidate.person:
                        self.clear_kiosk(terminal, invalidate.notice)
                    if invalidate.cancel_capture and terminal.capture and terminal.capture["person"] == invalidate.person:
                        terminal.capture = None
        return {}, None

    def admin_read(self, path, query, key, session, caddy_version):
        if path == "/api/admin/session":
            return {"name": session["name"], "super_admin": session["super_admin"]}
        if path in (PREVIEW_PATH, PREVIEW_PATH + "/page", PREVIEW_PATH + "/screen"):
            terminal = self.terminal(query.get("terminal", [""])[0])
            if path != PREVIEW_PATH:
                return None
            policies = self.policy_documents()
            return {**self.catalog(terminal), "terminal": terminal.label, "terminals": self.terminal_labels(),
                    "version": policies[0], "privacy_version": policies[1], "registration": self.registration,
                    "session_idle": SESSION_IDLE, "receipt_seconds": RECEIPT_SECONDS, "cash_receipt_seconds": CASH_RECEIPT_SECONDS,
                    "cash_max": finance.CASH_MAX_CENTS, "paypal": PREVIEW_PAYPAL_LABEL,
                    "loyalty": data.loyalty_card_status(0)}
        if path == PREVIEW_QR_PATH:
            return finance.paypal_qr(PREVIEW_PAYPAL_LABEL)
        if path == "/api/admin/terminal-status":
            clock = monotonic()
            return {key: {"online": clock - terminal.browser_at < TERMINAL_ONLINE_SECONDS,
                          "reader": clock - terminal.reader_at < 8,
                          "paired": bool(terminal.paired_browser)}
                    for key, terminal in self.terminals.items()}
        if path == "/api/admin/capture-status":
            terminal = self.terminal(query.get("terminal", [""])[0])
            with terminal.lock:
                self.sweep_terminal(terminal)
                capture = terminal.capture
                if not capture or capture["owner"] != key:
                    return {"state": "idle"}
                return {"state": "ready" if capture["card"] else "waiting",
                        "remaining": max(0, capture["until"] - monotonic())}
        if path == "/api/admin/terminal-profile":
            terminal = self.terminal(query.get("terminal", [""])[0])
            profile = device_profile(self.origin, terminal.id, terminal.secret, self.reader_ca)
            return finance.Download((json.dumps(profile, indent=2) + "\n").encode(),
                                    "application/json; charset=utf-8", f"terminal-{terminal.id}.json")
        if path == "/api/admin/terms":
            return self.terms
        if path == "/api/admin/privacy":
            return self.privacy
        if path == "/api/admin/sites":
            return {"terminals": self.terminal_labels(), "retired_terminals": self.retired_terminals}
        with data.connect(self.db, snapshot=path in (
            "/api/admin/journal", "/api/admin/report", "/api/admin/export-balances", "/api/admin/export-account",
            "/api/admin/people"
        )) as db:
            if path == "/api/admin/summary":
                return data.admin_summary(db)
            if path == "/api/admin/products":
                return {"products": data.all_products(db), "categories": data.CATEGORIES, "icons": data.ICONS}
            if path in ("/api/admin/people", "/api/admin/account-options"):
                search = query.get("search", [""])[0]
                if len(search) > 240:
                    raise data.Problem(400, "Der Suchtext darf höchstens 240 Zeichen lang sein.")
                if "\x00" in search:
                    raise data.Problem(400, "Ungültiger Suchtext.")
                words = search.split()
                page = number(int(query.get("page", ["1"])[0]), 1, 2**31 - 1, "Seite")
                if path == "/api/admin/account-options":
                    return data.admin_account_options(db, words, page)
                sort = query.get("sort", ["last"])[0]
                direction = query.get("direction", ["ascending"])[0]
                if sort not in data.ADMIN_PEOPLE_SORTS or direction not in ("ascending", "descending"):
                    raise data.Problem(400, "Ungültige Sortierung.")
                with self.policy_lock:
                    terms, privacy_version = self.terms, self.privacy["version"]
                result = data.admin_people_page(db, terms["version"], privacy_version, words, sort,
                                                direction == "descending", page)
                return {**result, "card_types": CARD_TYPES, "card_media": admin_operations.CARD_MEDIA,
                        "terms_date": terms.get("date")}
            if path == "/api/admin/paypal-settings":
                return {"link": self.paypal_link(db)}
            if path == "/api/admin/technical-docs":
                return {**technical_docs.versions(db, self.terminals, caddy_version, self.deployment),
                        "retention": self.retention_status}
            if path == "/api/admin/admins":
                return {"admins": [dict(row) for row in db.execute(
                    "SELECT name,first,last,description,super_admin FROM admins ORDER BY super_admin DESC,name"
                )]}
            if path == "/api/admin/payments":
                status = query.get("status", ["pending"])[0]
                if status not in ("pending", "confirmed", "rejected"):
                    raise data.Problem(400, "Ungültiger Zahlungsstatus.")
                before = number(int(query.get("before", [str(2**53 - 1)])[0]), 1, 2**53 - 1, "Seitengrenze")
                return finance.paypal_overview(db, status, before)
            if path == "/api/admin/report":
                site = query.get("terminal", [""])[0]
                if site and site not in self.historical_terminal_labels():
                    raise data.Problem(400, "Unbekannter Verkaufspunkt.")
                return finance.monthly(db, query.get("month", [""])[0], site or None)
            if path in ("/api/admin/export-balances", "/api/admin/export-account"):
                stamp = finance.local_date(datetime.now(timezone.utc))
                if path.endswith("balances"):
                    return finance.balances_export(db, stamp)
                person = number(int(query.get("person", ["0"])[0]), 1, 2**31 - 1, "Konto")
                return finance.account_export(db, person, self.historical_terminal_labels(), stamp)
            if path == "/api/admin/overview":
                with self.policy_lock:
                    terms, privacy_version = self.terms, self.privacy["version"]
                return {"people": data.people_overview(db, terms["version"], privacy_version),
                        "products": data.all_products(db), "card_types": CARD_TYPES, "card_media": admin_operations.CARD_MEDIA,
                        "categories": data.CATEGORIES, "icons": data.ICONS,
                        "terminals": self.terminal_labels(), "retired_terminals": self.retired_terminals,
                        "terms_version": terms["version"],
                        "terms_date": terms.get("date")}
            if path == "/api/admin/journal":
                try:
                    person = int(query["person"][0]) if "person" in query else None
                    before = int(query["before"][0]) if "before" in query else 2**53 - 1
                except ValueError as exc:
                    raise data.Problem(400, "Ungültiger Filter.") from exc
                if person is not None:
                    number(person, 1, 2**31 - 1, "Konto")
                number(before, 1, 2**53 - 1, "Seitengrenze")
                site = query.get("terminal", [""])[0]
                if site and site not in self.historical_terminal_labels():
                    raise data.Problem(400, "Unbekannter Verkaufspunkt.")
                reversals = query.get("reversals", ["0"])[0]
                if reversals not in ("0", "1"):
                    raise data.Problem(400, "Ungültiger Storno-Filter.")
                return data.list_journal(db, person, before, site or None, include_reversals=reversals == "1")
            if path == "/api/admin/audit":
                before = number(int(query.get("before", [str(2**53 - 1)])[0]), 1, 2**53 - 1, "Seitengrenze")
                return data.list_audit(db, before)
        raise data.Problem(404, "Seite nicht gefunden.")

    def terminal(self, key):
        if not isinstance(key, str) or key not in self.terminals:
            raise data.Problem(400, "Unbekannter Verkaufspunkt.")
        return self.terminals[key]

    def capture_action(self, path, body, key, actor):
        terminal = self.terminal(body.get("terminal"))
        with terminal.lock:
            self.sweep_terminal(terminal)
            return self.update_capture(terminal, path, body, key, actor)

    def update_capture(self, terminal, path, body, key, actor):
        if path == "/api/admin/capture-start":
            if terminal.capture:
                raise data.Problem(409, "Es läuft bereits ein Kartentausch.")
            if terminal.kiosk and terminal.kiosk["stage"] != Stage.IDLE:
                raise data.Problem(409, "Am Terminal läuft gerade ein Einkauf oder eine Anmeldung.")
            person = number(body.get("id"), 1, 2**31 - 1, "Konto")
            with data.connect(self.db) as db:
                if not db.execute("SELECT id FROM people WHERE id=%s AND closed_at IS NULL", (person,)).fetchone():
                    raise data.Problem(404, "Konto nicht gefunden.")
            terminal.capture = {"owner": key, "person": person, "until": monotonic() + 45, "card": None}
            return {}
        if not terminal.capture or terminal.capture["owner"] != key:
            raise data.Problem(409, "Die Kartenerfassung ist abgelaufen.")
        if path == "/api/admin/capture-cancel":
            terminal.capture = None
            return {}
        if path == "/api/admin/capture-confirm" and terminal.capture["card"]:
            capture = terminal.capture
            with data.connect(self.db) as db:
                if db.execute("SELECT id FROM people WHERE card=%s", (capture["card"],)).fetchone():
                    raise data.Problem(409, "Diese Karte gehört bereits zu einem Konto.")
                if data.retired_card_active(db, capture["card"]):
                    raise data.Problem(409, "Diese Karte ist nach einem Kartentausch noch gesperrt.")
                old = db.execute("""SELECT card,card_type,card_medium FROM people
                                    WHERE id=%s AND closed_at IS NULL FOR NO KEY UPDATE""", (capture["person"],)).fetchone()
                if not old:
                    raise data.Problem(404, "Konto nicht gefunden.")
                if old["card"]:
                    db.execute("""INSERT INTO retired_cards (card,expires_at) VALUES (%s,%s)
                                  ON CONFLICT(card) DO UPDATE SET expires_at=excluded.expires_at""",
                               (old["card"], datetime.now(timezone.utc) + data.BOOKING_RETENTION))
                db.execute("UPDATE people SET card=%s,card_type=%s,card_medium=NULL WHERE id=%s",
                           (capture["card"], capture["card_type"], capture["person"]))
                data.audit(db, actor, f"Karte für Konto #{capture['person']} an {terminal.label} ersetzt.",
                           {"Kartenzuordnung": "Bisherige Karte",
                            "Kartentyp": CARD_TYPES.get(old["card_type"]), "Kartenträger": admin_operations.CARD_MEDIA.get(old["card_medium"])},
                           {"Kartenzuordnung": "Neue Karte",
                            "Kartentyp": CARD_TYPES.get(capture["card_type"]), "Kartenträger": None}, person=capture["person"])
            terminal.capture = None
            return {}
        raise data.Problem(409, "Noch keine neue Karte erfasst.")

    def catalog(self, terminal):
        with data.connect(self.db) as db:
            return data.product_catalog(db, terminal.id)

    def route(self, terminal, method, path, query, body, cookies, caddy_version=None):
        if path.startswith("/api/admin/"):
            return self.admin_route(method, path, query, body, cookies, caddy_version)
        if method == "GET" and path == "/healthz":
            with data.connect(self.db) as db:
                db.execute("SELECT 1").fetchone()
            return {"ok": True}, None
        if method == "GET" and path == "/api/privacy":
            return self.privacy, None
        if terminal:
            with terminal.lock:
                if self.terminals.get(terminal.id) is not terminal:
                    raise data.Problem(404, "Unbekannter Verkaufspunkt.")
                self.sweep_terminal(terminal)
                return self.reader_event(terminal, body)
        if path == "/api/kiosk/pair" and method == "POST":
            with self.pairing_lock:
                return self.pairing_route(body, cookies)
        if path.startswith("/api/kiosk/") or path == "/api/catalog":
            terminal = self.browser_terminal(cookies)
            if not terminal:
                raise data.Problem(403, "Dieser Browser ist nicht als Terminal gekoppelt.")
            with terminal.lock:
                if self.device_digest("browser", cookies.get(DEVICE_COOKIE)) != terminal.paired_browser:
                    raise data.Problem(403, "Dieser Browser ist nicht als Terminal gekoppelt.")
                self.sweep_terminal(terminal)
                if path.startswith("/api/kiosk/"):
                    return self.kiosk_route(terminal, method, path, body, cookies, query)
                if method == "GET" and path == "/api/catalog":
                    return self.catalog(terminal), None
        if method == "GET" and path == "/api/terms":
            return self.terms, None
        raise data.Problem(404, "Seite nicht gefunden.")

    def reader_event(self, terminal, body):
        digest = self.device_digest("reader", body.get("instance"))
        if not digest:
            raise data.Problem(400, "Der Leserdienst benötigt eine Gerätekennung.")
        if any(t is not terminal and t.paired_reader == digest for t in self.terminals.values()):
            raise data.Problem(409, "Dieser Leserdienst ist einem anderen Verkaufspunkt zugeordnet.")
        if terminal.paired_reader and terminal.paired_reader != digest:
            raise data.Problem(409, "Dieser Leserdienst gehört nicht zum gekoppelten Terminal.")
        terminal.reader_digest = digest
        terminal.reader_seen = monotonic()
        if "packages" in body:
            terminal.reader_packages = technical_docs.checked_packages(body["packages"])
            terminal.reader_packages_at = data.now()
        connected = body.get("connected") is True
        terminal.reader_at = terminal.reader_seen if connected else -100
        if terminal.paired_reader:
            if "uid" in body and connected:
                card_type = body.get("card_type")
                self.scan(terminal, body["uid"], card_type if isinstance(card_type, str) and card_type in CARD_TYPES else None)
            if body.get("issue") and terminal.kiosk and terminal.kiosk["stage"] == Stage.IDLE and not terminal.capture:
                terminal.kiosk["notice"] = string(body["issue"], 120, "Leserhinweis")
        return {}, None


def serve(db, cfg, port):
    from waitress import serve as serve_wsgi

    app = App(db, cfg)
    print(f"KoSTbar bereit · {app.origin}/admin", flush=True)
    stop = Event()
    workers = [Thread(target=target, args=(stop,), daemon=True)
               for target in (app.retention_worker, app.sweep_sessions)]
    for worker in workers:
        worker.start()
    try:
        serve_wsgi(WsgiApp(app), host="0.0.0.0", port=port,
                   threads=8, connection_limit=64, channel_timeout=15, cleanup_interval=5,
                   max_request_header_size=16384, max_request_body_size=65536, ident="KoSTbar")
    finally:
        stop.set()
        for worker in workers:
            worker.join(timeout=5)


def database():
    return {"host": os.environ.get("PGHOST", "db"), "dbname": os.environ.get("PGDATABASE", "kaffeekasse"),
            "user": os.environ.get("PGUSER", "kaffeekasse"), "password": os.environ["PGPASSWORD"]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("/app/config.json"))
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("serve").add_argument("--port", type=int, default=8765)
    sub.add_parser("migrate", help="Datenbankschema transaktional aktualisieren.")
    sub.add_parser("schema-status", help="Angewendete Datenbankmigrationen anzeigen.")
    for command in ("set-super-admin", "set-admin", "remove-admin"):
        sub.add_parser(command).add_argument("name")
    args = parser.parse_args()
    if sys.platform != "win32":
        os.umask(0o077)
    cfg = config(args.config)
    db_source = database()
    if args.command == "serve":
        serve(db_source, cfg, args.port)
    elif args.command == "migrate":
        data.initialize(db_source, cfg.get("terminals", {}), terms_document(cfg))
        print(f"Datenbankschema bereit: Version {schema_migrations.LATEST_VERSION}.")
    elif args.command == "schema-status":
        with data.connect(db_source) as db:
            rows = schema_migrations.schema_status(db)
        if not rows:
            print("Datenbankschema ist noch unversioniert.")
        for row in rows:
            print(f"{row['version']} · {row['name']} · {row['checksum']} · {row['applied_at']}")
    else:
        try:
            name = admin_name(args.name)
        except ValueError as exc:
            raise SystemExit(str(exc)) from exc
        data.initialize(db_source, cfg.get("terminals", {}), terms_document(cfg))
        if args.command == "remove-admin":
            with data.connect(db_source) as db:
                data.lock_admins(db)
                existing = data.admin_snapshot(db, name)
                if existing and existing["super_admin"]:
                    raise SystemExit("Weise die Super-Admin-Rolle zuerst einem anderen Konto zu.")
                previous = data.admin_snapshot_labels(existing)
                if db.execute("SELECT COUNT(*) AS total FROM admins").fetchone()["total"] <= 1:
                    raise SystemExit("Mindestens ein Administratorkonto muss bestehen bleiben.")
                if not db.execute("DELETE FROM admins WHERE name=%s", (name,)).rowcount:
                    raise SystemExit("Administratorkonto nicht gefunden.")
                data.audit(db, "Konsole", f"Admin {name} entfernt.", previous, None)
        else:
            password = getpass(f"Neues Passwort (mindestens {ADMIN_PASSWORD_MIN} Zeichen): ")
            if not ADMIN_PASSWORD_MIN <= len(password) <= 256 or getpass("Passwort wiederholen: ") != password:
                raise SystemExit(f"Das Passwort muss {ADMIN_PASSWORD_MIN} bis 256 Zeichen haben und mit der Wiederholung übereinstimmen.")
            digest = data.admin_password_hash(password)
            with data.connect(db_source) as db:
                data.lock_admins(db)
                existing = data.admin_snapshot(db, name)
                if existing:
                    db.execute("UPDATE admins SET password=%s WHERE name=%s", (digest, name))
                    data.audit(db, "Konsole", f"Passwort für Admin {name} geändert.",
                               {"Passwort": "Bisheriges Passwort"}, {"Passwort": "Neues Passwort"})
                else:
                    try:
                        first = string(input("Vorname: "), 60, "Vorname")
                        last = string(input("Nachname: "), 60, "Nachname")
                        description = input("Beschreibung (optional): ").strip()
                        if description:
                            description = string(description, 240, "Beschreibung")
                    except data.Problem as exc:
                        raise SystemExit(str(exc)) from exc
                    db.execute("INSERT INTO admins (name,password,first,last,description) VALUES (%s,%s,%s,%s,%s)",
                               (name, digest, first, last, description))
                    data.audit(db, "Konsole", f"Administratorkonto {name} angelegt.", None,
                               data.admin_snapshot_labels(data.admin_snapshot(db, name)))
                if args.command == "set-super-admin":
                    previous = db.execute("SELECT name FROM admins WHERE super_admin=1 AND name<>%s",
                                          (name,)).fetchone()
                    if previous:
                        db.execute("UPDATE admins SET super_admin=0 WHERE name=%s", (previous["name"],))
                        data.audit(db, "Konsole", f"Super-Admin-Rolle für {previous['name']} entzogen.",
                                   {"Rolle": "Super-Admin"}, {"Rolle": "Administrator"})
                    if not existing or not existing["super_admin"]:
                        db.execute("UPDATE admins SET super_admin=1 WHERE name=%s", (name,))
                        data.audit(db, "Konsole", f"Super-Admin-Rolle an {name} vergeben.",
                                   {"Rolle": "Administrator"}, {"Rolle": "Super-Admin"})
        print(f"Administratorkonto {name} aktualisiert.")


if __name__ == "__main__":
    main()
