"""Transactional administration operations for accounts, products and bookings.

The caller owns the database transaction and applies kiosk session changes only
after the operation has committed.
"""

from dataclasses import dataclass
import re

import finance
import store as data
from validation import flag, number, request_id, string


CARD_MEDIA = {"badge": "Dienstausweis", "fob": "NFC-Schlüsselanhänger", "other": "Sonstiges"}


@dataclass(frozen=True)
class KioskInvalidation:
    person: int
    notice: str
    cancel_capture: bool = False


def lock_product_order(db):
    db.execute("SELECT pg_advisory_xact_lock(739310484)")


def next_product_position(db):
    return db.execute("SELECT COALESCE(MAX(sort_position),0)+1 AS position FROM products").fetchone()["position"]


def move_product(db, body, actor):
    group = body.get("group")
    if not isinstance(group, str) or group not in data.PRODUCT_ORDER_GROUPS:
        raise data.Problem(400, "Ungültige Sortimentsgruppe.")
    product = number(body.get("id"), 1, 2**53 - 1, "Produkt")
    neighbor = number(body.get("neighbor"), 1, 2**53 - 1, "Nachbarprodukt")
    lock_product_order(db)
    rows = db.execute("""SELECT id,sort_position FROM products WHERE deleted=0 AND category=ANY(%s)
                         ORDER BY sort_position,id""", (list(data.PRODUCT_ORDER_GROUPS[group]),)).fetchall()
    positions = {row["id"]: index for index, row in enumerate(rows)}
    left, right = positions.get(product), positions.get(neighbor)
    if left is None or right is None or abs(left - right) != 1:
        raise data.Problem(409, "Die Reihenfolge hat sich geändert. Lade das Sortiment neu.")
    # Reassign only the two ranks. Migration and product writes give each rank
    # a unique value within a group.
    db.execute("""UPDATE products SET sort_position=CASE WHEN id=%s THEN %s ELSE %s END
                  WHERE id IN (%s,%s)""",
               (product, rows[right]["sort_position"], rows[left]["sort_position"], product, neighbor))
    data.audit(db, actor, f"Sortimentsreihenfolge geändert ({group}).",
               {"Produkt": product, "Position": left + 1},
               {"Produkt": product, "Position": right + 1})


def save_product(db, body, actor, labels):
    name = string(body.get("name"), 80, "Produktname")
    category, icon = body.get("category"), body.get("icon")
    if not isinstance(category, str) or category not in data.CATEGORIES:
        raise data.Problem(400, "Ungültige Kategorie.")
    if not isinstance(icon, str) or icon not in data.ICONS:
        raise data.Problem(400, "Ungültiges Symbol.")
    cents = number(body.get("cents"), 1, 100000, "Preis")
    active = flag(body.get("active"))
    sites = body.get("terminals")
    if (not isinstance(sites, list) or len(sites) > len(labels)
            or any(not isinstance(site, str) or site not in labels for site in sites)
            or len(set(sites)) != len(sites)):
        raise data.Problem(400, "Ungültige Auswahl der Verkaufspunkte.")
    values = (category, name, cents, icon, active)
    lock_product_order(db)
    before = None
    if body.get("id") is None:
        product = db.execute(
            "INSERT INTO products (category,name,cents,icon,active,sort_position) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
            (*values, next_product_position(db))
        ).fetchone()["id"]
    else:
        product = number(body["id"], 1, 2**31 - 1, "Produkt")
        before = data.product_snapshot(db, product, labels)
        current = db.execute("SELECT category,sort_position FROM products WHERE id=%s", (product,)).fetchone()
        same_group = any(category in members and current["category"] in members
                         for members in data.PRODUCT_ORDER_GROUPS.values())
        rank = current["sort_position"] if same_group else next_product_position(db)
        if not db.execute("""UPDATE products SET category=%s,name=%s,cents=%s,icon=%s,active=%s,sort_position=%s
                             WHERE id=%s AND deleted=0""", (*values, rank, product)).rowcount:
            raise data.Problem(404, "Produkt nicht gefunden.")
    db.execute("DELETE FROM product_terminals WHERE product=%s", (product,))
    with db.cursor() as cursor:
        cursor.executemany("INSERT INTO product_terminals VALUES (%s,%s)", [(product, site) for site in sites])
    data.audit(db, actor, f"Produkt #{product} gespeichert.", before, data.product_snapshot(db, product, labels))


def set_product_status(db, body, actor, labels):
    product = number(body.get("id"), 1, 2**31 - 1, "Produkt")
    active = flag(body.get("active"))
    before = data.product_snapshot(db, product, labels)
    if not db.execute("UPDATE products SET active=%s WHERE id=%s AND deleted=0", (active, product)).rowcount:
        raise data.Problem(404, "Produkt nicht gefunden.")
    data.audit(db, actor, f"Produkt #{product} gespeichert.", before, data.product_snapshot(db, product, labels))


def hide_product(db, body, actor, labels):
    lock_product_order(db)
    product = number(body.get("id"), 1, 2**31 - 1, "Produkt")
    before = data.product_snapshot(db, product, labels)
    # Keep the product ID for journal items and monthly reports.
    db.execute("UPDATE products SET deleted=1,active=0 WHERE id=%s", (product,))
    db.execute("DELETE FROM product_terminals WHERE product=%s", (product,))
    data.audit(db, actor, f"Produkt #{product} dauerhaft ausgeblendet.", before, None)


def create_person(db, body, actor, pin_hash):
    first = string(body.get("first"), 60, "Vorname")
    last = string(body.get("last"), 60, "Nachname")
    department = string(body.get("department"), 80, "Referat")
    person = db.execute("INSERT INTO people (first,last,department,created) VALUES (%s,%s,%s,%s) RETURNING id",
                        (first, last, department, data.now())).fetchone()["id"]
    db.execute("INSERT INTO manual_credentials (person,pin_hash,temporary) VALUES (%s,%s,TRUE)", (person, pin_hash))
    data.audit(db, actor, f"Konto #{person} manuell angelegt.", None, data.person_snapshot(db, person), person=person)
    return {"id": person}


def reset_pin(db, body, actor, confirmed_pin_hash):
    person = number(body.get("id"), 1, 2**31 - 1, "Konto")
    data.lock_booking_account(db, person)
    account = db.execute("SELECT card,closed_at FROM people WHERE id=%s", (person,)).fetchone()
    if account["closed_at"]:
        raise data.Problem(409, "Dieses Konto ist zur Löschung vorgemerkt.")
    if account["card"] is None:
        db.execute("""INSERT INTO manual_credentials (person,pin_hash,temporary) VALUES (%s,%s,TRUE)
                      ON CONFLICT(person) DO UPDATE SET pin_hash=excluded.pin_hash,temporary=TRUE""",
                   (person, confirmed_pin_hash(body)))
        change = "Neue Start-PIN vergeben"
    else:
        removed = db.execute("DELETE FROM manual_credentials WHERE person=%s", (person,)).rowcount
        change = "Neu einzurichten" if removed else None
    db.execute("DELETE FROM manual_attempts WHERE person=%s", (person,))
    if change:
        data.audit(db, actor, f"PIN für Konto #{person} zurückgesetzt.",
                   None, {"Manuelle Anmeldung": change},
                   person=person)
    return KioskInvalidation(person, "Die PIN wurde zurückgesetzt.")


def edit_person(db, body, actor):
    person = number(body.get("id"), 1, 2**31 - 1, "Konto")
    first, last = string(body.get("first"), 60, "Vorname"), string(body.get("last"), 60, "Nachname")
    active = flag(body.get("active"))
    data.lock_booking_account(db, person)
    before = data.person_snapshot(db, person)
    if active and db.execute("SELECT closed_at FROM people WHERE id=%s", (person,)).fetchone()["closed_at"]:
        raise data.Problem(409, "Dieses Konto ist zur Löschung vorgemerkt.")
    department = string(body["department"], 80, "Referat") if body.get("department") else before["Referat"]
    if "card_medium" in body:
        medium = body["card_medium"]
        if not isinstance(medium, str) or (medium and medium not in CARD_MEDIA):
            raise data.Problem(400, "Unbekannter Kartenträger.")
        db.execute("UPDATE people SET card_medium=%s WHERE id=%s", (medium or None, person))
    db.execute("UPDATE people SET first=%s,last=%s,department=%s,active=%s WHERE id=%s",
               (first, last, department, active, person))
    data.audit(db, actor, f"Konto #{person} bearbeitet.", before, data.person_snapshot(db, person), person=person)
    if not active:
        return KioskInvalidation(person, "Dieses Konto ist gesperrt.")


def close_account(db, body, actor):
    person = number(body.get("id"), 1, 2**31 - 1, "Konto")
    saved = db.execute("SELECT closed_at FROM people WHERE id=%s FOR NO KEY UPDATE", (person,)).fetchone()
    if not saved:
        raise data.Problem(404, "Konto nicht gefunden.")
    if not saved["closed_at"]:
        db.execute("UPDATE people SET active=0,closed_at=%s WHERE id=%s", (data.now(), person))
        db.execute("DELETE FROM manual_credentials WHERE person=%s", (person,))
        db.execute("DELETE FROM manual_attempts WHERE person=%s", (person,))
        data.audit(db, actor, f"Konto #{person} geschlossen.", person=person)
    return KioskInvalidation(person, "Dieses Konto wurde geschlossen.", cancel_capture=True)


def adjust_balance(db, body, actor):
    person = number(body.get("id"), 1, 2**31 - 1, "Konto")
    kind = body.get("kind")
    if kind not in ("payment", "correction"):
        raise data.Problem(400, "Ungültige Buchungsart.")
    cents = number(body.get("cents"), 1 if kind == "payment" else -1000000, 1000000, "Betrag")
    if not cents:
        raise data.Problem(400, "Der Betrag muss ungleich null sein.")
    note = string(body.get("note"), 240, "Begründung")
    key_id = "admin:" + request_id(body.get("request"))
    data.lock_booking_account(db, person)
    existing = db.execute("SELECT id,kind,cents,note,actor FROM journal WHERE person=%s AND request_id=%s",
                          (person, key_id)).fetchone()
    if existing and (existing["kind"], existing["cents"], existing["note"], existing["actor"]) != (kind, cents, note, actor):
        raise data.Problem(409, "Diese Vorgangskennung gehört zu einer anderen Verwaltungsbuchung. Prüfe den Kontoverlauf.")
    if not existing:
        old_balance = data.balance(db, person)
        at = data.now()
        data.entry(db, person, kind, cents, actor, note, request_id=key_id, at=at)
        data.audit(db, actor, f"Saldo für Konto #{person} angepasst.",
                   {"Saldo (Cent)": old_balance},
                   {"Saldo (Cent)": old_balance + cents, "Buchungsbetrag (Cent)": cents, "Grund": note},
                   booking_detail=True, person=person, at=at)


def reverse_booking(db, body, actor):
    target = number(body.get("id"), 1, 2**53 - 1, "Buchung")
    note = string(body.get("note"), 240, "Begründung")
    account = db.execute("""SELECT p.id FROM people p JOIN journal j ON j.person=p.id
                            WHERE j.id=%s AND j.kind IN ('purchase','payment','correction') FOR NO KEY UPDATE OF p""",
                         (target,)).fetchone()
    if not account:
        raise data.Problem(404, "Buchung nicht gefunden.")
    original = db.execute("SELECT * FROM journal WHERE id=%s AND at>%s FOR UPDATE",
                          (target, data.booking_cutoff())).fetchone()
    if not original:
        raise data.Problem(404, "Buchung nicht gefunden.")
    reversed_by = db.execute("SELECT actor,note FROM journal WHERE reverses=%s", (target,)).fetchone()
    if reversed_by:
        if (reversed_by["actor"], reversed_by["note"]) == (actor, note):
            return
        raise data.Problem(409, "Diese Buchung wurde bereits storniert.")
    at = data.now()
    data.entry(db, original["person"], "reversal", -original["cents"], actor, note, reverses=target,
               terminal=original["terminal"], at=at, loyalty_delta=-original["loyalty_delta"])
    db.execute("UPDATE journal SET kiosk_pending=FALSE WHERE id=%s AND kiosk_pending", (target,))
    if original["kind"] == "purchase":
        redeemed = sum(line["qty"] for line in data.purchase_bonus(db, target))
        data.update_loyalty(db, original["person"], -original["loyalty_delta"], redeemed_delta=-redeemed)
        data.add_monthly_sale(db, original["terminal"], at, -original["cents"], target, reversal=True)
    elif original["kind"] == "payment":
        db.execute("UPDATE paypal_requests SET kiosk_pending=FALSE WHERE journal_id=%s AND kiosk_pending", (target,))
    data.audit(db, actor, f"{finance.KINDS[original['kind']]} #{target} storniert.", {"Status": "Gebucht"},
               {"Status": "Storniert", "Gegenbuchung (Cent)": -original["cents"], "Begründung": note},
               booking_detail=True, person=original["person"], at=at)


def confirm_paypal(db, body, actor, key):
    payment = number(body.get("id"), 1, 2**53 - 1, "Zahlung")
    cents = number(body.get("cents"), 1, 1000000, "Zahlungsbetrag")
    transaction = string(body.get("transaction"), 100, "PayPal-Transaktions-ID").upper()
    if not re.fullmatch(r"[A-Z0-9-]{5,100}", transaction):
        raise data.Problem(400, "Gib die PayPal-Transaktions-ID aus der Zahlung ein.")
    finance.paypal_resolve(db, payment, actor, cents=cents, transaction=transaction, key=key)


def reject_paypal(db, body, actor, key):
    payment = number(body.get("id"), 1, 2**53 - 1, "Zahlung")
    note = string(body.get("note"), 240, "Begründung")
    finance.paypal_resolve(db, payment, actor, note=note, key=key)
