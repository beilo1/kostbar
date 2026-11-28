"""PostgreSQL journal and catalog."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
import secrets
from zoneinfo import ZoneInfo

import schema_migrations

CATEGORIES = {
    "cold": "Kaltgetränke", "hot": "Heißgetränke", "snack": "Snacks",
    "sweet": "Süßes", "chocolate": "Schokoladiges",
}
PRODUCT_ORDER_GROUPS = {
    "drink": ("cold", "hot"), "snack": ("snack",), "sweet": ("sweet",), "chocolate": ("chocolate",),
}
LOYALTY_STAMPS = 10
BOOKING_RETENTION = timedelta(days=90)
AUDIT_RETENTION = timedelta(days=180)
ICONS = {
    "water": "Wasserflasche", "lemon": "Zitronenflasche", "apple": "Schorleflasche",
    "energy": "Dose", "coffee": "Kaffee", "cappuccino": "Cappuccino", "milk": "Milchkaffee",
    "salami": "Snack", "noodles": "Nudeln", "pasta": "Pasta",
    "bar": "Riegel", "wafer": "Waffel", "candy": "Bonbons", "cookie": "Keks",
    "cola": "Cola", "limo": "Limo", "chips": "Chips", "tuc-cracker": "TUC-Cracker",
    "peanuts": "Nic Nacs / Erdnüsse",
    "trail-mix": "Studentenfutter / Nussmix", "mr-tom": "Mr. Tom Riegel", "hanuta": "Hanuta",
    "knoppers-bar": "Knoppers Riegel", "chocolate-bar": "Schokoriegel", "chocolate-tablet": "Schokoladentafel",
    "twix": "Twix", "mentos": "Mentos", "maoam": "Maoam", "ballisto": "Ballisto", "oreo": "Oreo",
    "double-biscuit": "Doppelkeks / Prinzenrolle", "snickers": "Snickers", "mars": "Mars",
}
CATALOG = (
    ("cold", "Mineralwasser", 50, "water"),
    ("cold", "Mineralwasser Zitrone", 80, "lemon"),
    ("cold", "Apfelschorle", 100, "apple"),
    ("cold", "Red Bull", 200, "energy"),
    ("hot", "Kaffee", 50, "coffee"),
    ("hot", "Cappuccino", 50, "cappuccino"),
    ("hot", "Milchkaffee", 50, "milk"),
    ("snack", "Bifi", 100, "salami"),
    ("snack", "Asianudeln", 100, "noodles"),
    ("snack", "Pasta Pot", 100, "pasta"),
    ("chocolate", "Kinderriegel", 50, "bar"),
    ("chocolate", "Kinder Country", 50, "wafer"),
    ("chocolate", "Balisto", 50, "ballisto"),
    ("chocolate", "Duplo", 50, "wafer"),
    ("sweet", "Maoam", 50, "maoam"),
    ("sweet", "Mentos", 50, "mentos"),
    ("chocolate", "Knoppers", 50, "wafer"),
    ("chocolate", "Mars", 50, "mars"),
    ("chocolate", "Snickers", 50, "snickers"),
    ("chocolate", "Oreo", 50, "oreo"),
)


class Problem(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def booking_cutoff(clock=None):
    clock = clock if clock is not None else datetime.now(timezone.utc)
    return (clock - BOOKING_RETENTION).isoformat(timespec="seconds")


ADMIN_HASH_PREFIX = "scrypt-v2:"


def scrypt_record(password, salt, cost):
    salt = salt if salt is not None else secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=cost, r=8, p=1, maxmem=192 * 1024**2)
    return salt.hex() + ":" + digest.hex()


def password_hash(password, salt=None):
    return scrypt_record(password, salt, 2**15)


def check_password(password, record):
    salt = bytes.fromhex(record.split(":")[0])
    return hmac.compare_digest(password_hash(password, salt), record)


def admin_password_hash(password):
    return ADMIN_HASH_PREFIX + scrypt_record(password, None, 2**17)


def check_admin_password(password, record):
    current = record.startswith(ADMIN_HASH_PREFIX)
    value = record.removeprefix(ADMIN_HASH_PREFIX)
    try:
        salt = bytes.fromhex(value.partition(":")[0])
        if len(salt) != 16 or not value.isascii():
            return False
        computed = scrypt_record(password, salt, 2**17 if current else 2**15)
    except (ValueError, UnicodeError):
        return False
    return hmac.compare_digest(computed, value)


@contextmanager
def connect(source, snapshot=False):
    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(**source, row_factory=dict_row, connect_timeout=3,
                         options="-c statement_timeout=5000 -c lock_timeout=3500") as db:
        if snapshot:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        yield db


def admin_snapshot(db, name):
    row = db.execute("SELECT name,first,last,description,super_admin FROM admins WHERE name=%s", (name,)).fetchone()
    return dict(row) if row else None


def admin_snapshot_labels(row):
    if row is None:
        return None
    return {"Anmeldename": row["name"], "Vorname": row["first"], "Nachname": row["last"],
            "Beschreibung": row["description"], "Rolle": "Super-Admin" if row["super_admin"] else "Administrator"}


def lock_admins(db):
    db.execute("SELECT pg_advisory_xact_lock(739310482)")


def initialize(source, terminals, terms):
    with connect(source) as db:
        schema_migrations.migrate(db)
        with db.cursor() as cursor:
            cursor.executemany("INSERT INTO terminals (id) VALUES (%s) ON CONFLICT DO NOTHING",
                               [(key,) for key in terminals])
        document = json.dumps(terms, ensure_ascii=False, sort_keys=True)
        db.execute("INSERT INTO terms_versions VALUES (%s,%s) ON CONFLICT DO NOTHING",
                   (terms["version"], document))
        recorded = db.execute("SELECT document FROM terms_versions WHERE version=%s", (terms["version"],)).fetchone()
        if recorded["document"] != document:
            raise SystemExit("Der Text der Nutzungsbedingungen wurde geändert. Setze eine neue terms.version.")
        if db.execute("INSERT INTO settings VALUES ('catalog_seeded', '1') ON CONFLICT DO NOTHING").rowcount:
            with db.cursor() as cursor:
                cursor.executemany("INSERT INTO products (category,name,cents,icon) VALUES (%s,%s,%s,%s)", CATALOG)
            db.execute("UPDATE products SET sort_position=id WHERE sort_position=0")
            db.execute("INSERT INTO product_terminals SELECT p.id,t.id FROM products p CROSS JOIN terminals t WHERE NOT t.retired")


def carried_balance(db, person):
    row = db.execute("SELECT cents FROM carried_balances WHERE person=%s", (person,)).fetchone()
    return int(row["cents"]) if row else 0


def balance(db, person):
    row = db.execute("""SELECT COALESCE((SELECT cents FROM carried_balances WHERE person=%s),0)
                        + COALESCE(SUM(cents),0) AS balance FROM journal WHERE person=%s""",
                     (person, person)).fetchone()
    return int(row["balance"])


def paypal_fingerprint(key, transaction):
    return hmac.new(key, ("paypal-transaction:" + transaction).encode(), hashlib.sha256).hexdigest()


def expire_booking_details(db, clock, key):
    """Fold expired entries into balances and return the next expiry, in one transaction."""
    db.execute("SELECT pg_advisory_xact_lock(739310483)")
    cutoff = booking_cutoff(clock)
    audit_cutoff = (clock - AUDIT_RETENTION).isoformat(timespec="seconds")
    # Take original-booking locks before folding or deleting their data.
    db.execute("SELECT id FROM journal WHERE at<=%s AND kind IN ('purchase','payment','correction') ORDER BY id FOR UPDATE",
               (cutoff,))
    db.execute("""INSERT INTO carried_balances (person,cents)
                  SELECT person,SUM(cents) FROM journal WHERE at<=%s
                  GROUP BY person HAVING SUM(cents)<>0
                  ON CONFLICT(person) DO UPDATE SET cents=carried_balances.cents+excluded.cents""", (cutoff,))
    db.execute("DELETE FROM carried_balances WHERE cents=0")
    # Resolved requests use the decision timestamp. For confirmed payments it is the booking timestamp.
    fingerprints = [
        (paypal_fingerprint(key, row["transaction_ref"]),)
        for row in db.execute(
            "DELETE FROM paypal_requests WHERE COALESCE(resolved,created)<=%s RETURNING transaction_ref", (cutoff,)
        )
        if row["transaction_ref"] is not None
    ]
    if fingerprints:
        with db.cursor() as cursor:
            cursor.executemany("INSERT INTO paypal_used_fingerprints (digest) VALUES (%s) ON CONFLICT DO NOTHING",
                               fingerprints)
    db.execute("DELETE FROM items WHERE entry IN (SELECT id FROM journal WHERE at<=%s)", (cutoff,))
    db.execute("UPDATE journal SET reverses=NULL WHERE reverses IN (SELECT id FROM journal WHERE at<=%s)", (cutoff,))
    db.execute("DELETE FROM journal WHERE at<=%s", (cutoff,))
    db.execute("DELETE FROM audit WHERE booking_detail=1 AND at<=%s", (cutoff,))
    db.execute("DELETE FROM audit WHERE booking_detail=0 AND at<=%s", (audit_cutoff,))
    db.execute("DELETE FROM retired_cards WHERE expires_at<=%s", (clock,))
    db.execute("DELETE FROM manual_attempts WHERE expires<=%s", (int(clock.timestamp()),))
    settled = """p.closed_at IS NOT NULL
                  AND NOT EXISTS (SELECT 1 FROM journal j WHERE j.person=p.id)
                  AND NOT EXISTS (SELECT 1 FROM paypal_requests r WHERE r.person=p.id)
                  AND NOT EXISTS (SELECT 1 FROM carried_balances c WHERE c.person=p.id AND c.cents<>0)"""
    closed_ids = [row["id"] for row in db.execute(
        f"SELECT p.id FROM people p WHERE {settled} ORDER BY p.id FOR UPDATE OF p SKIP LOCKED"
    )]
    if closed_ids:
        # Check again with a fresh statement snapshot after locking the accounts.
        db.execute(f"DELETE FROM people p WHERE p.id=ANY(%s) AND {settled}", (closed_ids,))
    oldest = db.execute("""SELECT MIN(at) AS at FROM (
                            SELECT MIN(at) AS at FROM journal
                            UNION ALL SELECT MIN(COALESCE(resolved,created)) FROM paypal_requests
                            UNION ALL SELECT MIN(at) FROM audit WHERE booking_detail=1
                          ) AS dates""").fetchone()["at"]
    return min((oldest or clock) + BOOKING_RETENTION, clock + timedelta(minutes=1))


def retired_card_active(db, card):
    return db.execute("SELECT 1 FROM retired_cards WHERE card=%s AND expires_at>%s", (card, now())).fetchone()


def accept_terms(db, person, version, terminal, accepted_at=None):
    db.execute("INSERT INTO terms_acceptances VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
               (person, version, accepted_at or now(), terminal))


def accept_policies(db, person, terms, privacy, terminal):
    stamp = now()
    accept_terms(db, person, terms, terminal, stamp)
    db.execute("""INSERT INTO policy_acceptances (person,terms_version,privacy_version,accepted_at,terminal)
                  VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
               (person, terms, privacy, stamp, terminal))


def available_products(db, terminal):
    return [dict(row) for row in db.execute(
        """SELECT p.id,p.category,p.name,p.cents,p.icon,p.active FROM products p
           JOIN product_terminals pt ON p.id=pt.product
           WHERE pt.terminal=%s AND p.active=1 AND p.deleted=0 ORDER BY p.sort_position,p.id""", (terminal,)
    )]


def product_catalog(db, terminal):
    return {"products": available_products(db, terminal), "categories": CATEGORIES}


def all_products(db):
    assignments = {}
    for row in db.execute("SELECT product,terminal FROM product_terminals ORDER BY terminal"):
        assignments.setdefault(row["product"], []).append(row["terminal"])
    return [{**dict(row), "terminals": assignments.get(row["id"], [])}
            for row in db.execute("SELECT id,category,name,cents,icon,active FROM products WHERE deleted=0 ORDER BY sort_position,id")]


def entry(db, person, kind, cents, actor=None, note=None, request_id=None, reverses=None, terminal=None, *, kiosk_pending=False, at=None, loyalty_delta=0):
    return db.execute(
        """INSERT INTO journal (person,kind,cents,at,actor,note,request_id,reverses,terminal,kiosk_pending,loyalty_delta)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (person, kind, cents, at or now(), actor, note, request_id, reverses, terminal, kiosk_pending, loyalty_delta),
    ).fetchone()["id"]


def pending_kiosk_booking(db, person):
    cutoff = booking_cutoff()
    return db.execute(
        """SELECT 'paypal' AS kind, request_id AS request, id AS entry, cents AS total, reference, status
           FROM paypal_requests WHERE person=%s AND kiosk_pending AND COALESCE(resolved,created)>%s
           UNION ALL
           SELECT CASE WHEN kind='purchase' THEN 'purchase' ELSE 'cash' END,
                  REPLACE(request_id, 'cash:', ''), id, ABS(cents), NULL, 'booked'
           FROM journal WHERE person=%s AND kiosk_pending AND at>%s""", (person, cutoff, person, cutoff)
    ).fetchone()


def lock_booking_account(db, person):
    # Serialize bookings for this account while allowing the worker's foreign-key key-share locks.
    if not db.execute("SELECT id FROM people WHERE id=%s FOR NO KEY UPDATE", (person,)).fetchone():
        raise Problem(404, "Konto nicht gefunden.")


def check_pending_kiosk_booking(db, person, kind, key):
    """Check the previous receipt after the caller has locked the account."""
    previous = pending_kiosk_booking(db, person)
    if previous and (previous["kind"], previous["request"]) != (kind, key):
        raise Problem(409, "Prüfe zuerst, ob dein letzter Vorgang gebucht wurde.")


def acknowledge_kiosk_booking(db, person, kind, key):
    lock_booking_account(db, person)
    if kind == "paypal":
        db.execute("UPDATE paypal_requests SET kiosk_pending=FALSE WHERE person=%s AND request_id=%s AND kiosk_pending",
                   (person, key))
    else:
        prefix, journal_kind = ("cash:", "payment") if kind == "cash" else ("", "purchase")
        db.execute("UPDATE journal SET kiosk_pending=FALSE WHERE person=%s AND request_id=%s AND kind=%s AND kiosk_pending",
                   (person, prefix + key, journal_kind))


def audit(db, actor, detail, before=None, after=None, actor_label=None, *, booking_detail=False, person=None, at=None):
    if before is not None and before == after:
        return
    if actor_label is None:
        account = admin_snapshot(db, actor)
        if account:
            actor_label = " ".join(part for part in (account["first"], account["last"]) if part)
    db.execute("""INSERT INTO audit (at,actor,detail,old_state,new_state,actor_label,booking_detail,person)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
               (at or now(), actor, detail, json.dumps(before, ensure_ascii=False) if before is not None else None,
                json.dumps(after, ensure_ascii=False) if after is not None else None, actor_label, int(booking_detail), person))


def list_audit(db, before):
    clock = datetime.now(timezone.utc)
    rows = db.execute("""SELECT * FROM audit WHERE id<%s
                         AND ((booking_detail=1 AND at>%s) OR (booking_detail=0 AND at>%s))
                         ORDER BY id DESC LIMIT 101""",
                      (before, booking_cutoff(clock), clock - AUDIT_RETENTION)).fetchall()
    result = []
    for row in rows[:100]:
        event = dict(row)
        event.pop("person")
        for key in ("old_state", "new_state"):
            event[key] = json.loads(event[key]) if event[key] else None
        result.append(event)
    return {"entries": result, "next": result[-1]["id"] if len(rows) > 100 else None}


def person_snapshot(db, person):
    row = db.execute("SELECT first,last,department,active,card_medium FROM people WHERE id=%s", (person,)).fetchone()
    if not row:
        raise Problem(404, "Konto nicht gefunden.")
    return {"Vorname": row["first"], "Nachname": row["last"], "Referat": row["department"],
            "Status": "Aktiv" if row["active"] else "Gesperrt", "Kartenträger": row["card_medium"]}


def product_snapshot(db, product, labels):
    row = db.execute("SELECT category,name,cents,icon,active FROM products WHERE id=%s AND deleted=0", (product,)).fetchone()
    if not row:
        raise Problem(404, "Produkt nicht gefunden.")
    sites = db.execute("SELECT terminal FROM product_terminals WHERE product=%s ORDER BY terminal", (product,))
    return {"Name": row["name"], "Kategorie": CATEGORIES[row["category"]], "Preis": f"{row['cents']/100:.2f}".replace(".", ",") + " €",
            "Symbol": ICONS[row["icon"]], "Status": "Aktiv" if row["active"] else "Archiviert",
            "Verkaufspunkte": ", ".join(labels[site["terminal"]] for site in sites)}



def loyalty_progress(db, person):
    row = db.execute("SELECT progress FROM loyalty_cards WHERE person=%s", (person,)).fetchone()
    return row["progress"] if row else 0


def loyalty_card_status(progress):
    return {"stamps": max(0, min(progress, LOYALTY_STAMPS)), "target": LOYALTY_STAMPS,
            "ready": max(0, progress // LOYALTY_STAMPS), "remaining": max(0, LOYALTY_STAMPS - progress)}


def loyalty_card(db, person):
    return loyalty_card_status(loyalty_progress(db, person))


def update_loyalty(db, person, delta, *, redeemed_delta=0):
    # A reversal can leave a debt when the bonus has already been used. New paid
    # drinks offset it without modifying any other booking or charging retroactively.
    if delta or redeemed_delta:
        db.execute("""INSERT INTO loyalty_cards (person,progress,redeemed) VALUES (%s,%s,GREATEST(0,%s))
                      ON CONFLICT(person) DO UPDATE SET progress=loyalty_cards.progress+excluded.progress,
                         redeemed=loyalty_cards.redeemed+%s""",
                   (person, delta, redeemed_delta, redeemed_delta))


def purchase_pricing(db, person, cart, terminal):
    return price_cart(available_products(db, terminal), cart, lambda: loyalty_progress(db, person))


def price_cart(products, cart, get_progress):
    catalog = {product["id"]: product for product in products}
    lines = []
    hot = []
    for product_id, quantity, expected in cart:
        row = catalog.get(product_id)
        if not row or row["cents"] != expected:
            raise Problem(409, "Das Sortiment oder ein Preis hat sich geändert. Prüfe deinen Warenkorb.")
        line = {"id": product_id, "name": row["name"], "cents": expected, "qty": quantity, "bonus_qty": 0}
        lines.append(line)
        if row["category"] == "hot":
            hot.append(line)
    hot_units = sum(line["qty"] for line in hot)
    free_units = 0
    if hot_units:
        # A free unit consumes ten stamps and earns none of its own.
        free_units = min(hot_units, max(0, (get_progress() + hot_units) // (LOYALTY_STAMPS + 1)))
    remaining = free_units
    for line in sorted(hot, key=lambda item: (item["cents"], item["id"])):
        line["bonus_qty"] = min(remaining, line["qty"])
        remaining -= line["bonus_qty"]
    subtotal = sum(line["qty"] * line["cents"] for line in lines)
    discount = sum(line["bonus_qty"] * line["cents"] for line in hot)
    return {"lines": lines, "subtotal": subtotal, "discount": discount, "total": subtotal - discount,
            "loyalty_delta": hot_units - (LOYALTY_STAMPS + 1) * free_units}


def purchase_bonus(db, booking):
    return [dict(row) for row in db.execute(
        """SELECT name,bonus_quantity AS qty,price FROM items WHERE entry=%s AND bonus_quantity>0 ORDER BY product""",
        (booking,),
    )]


def check_purchase_discount(quoted, actual):
    if quoted is not None and quoted != actual:
        raise Problem(409, "Deine Sammelkarte hat sich geändert. Prüfe den aktualisierten Gesamtbetrag.")


def purchases(db, person, request_id, cart, terminal, *, quoted_discount=None):
    existing = db.execute(
        "SELECT id,cents,terminal,kind,loyalty_delta,at>%s AS fresh FROM journal WHERE person=%s AND request_id=%s",
        (booking_cutoff(), person, request_id),
    ).fetchone()
    if existing:
        if not existing["fresh"]:
            raise Problem(409, "Diese Buchungskennung ist abgelaufen.")
        lines = db.execute("SELECT product,quantity,price FROM items WHERE entry=%s ORDER BY product", (existing["id"],))
        if (existing["terminal"] != terminal or existing["kind"] != "purchase"
                or [(row["product"], row["quantity"], row["price"]) for row in lines] != sorted(cart)):
            raise Problem(409, "Die Buchungskennung gehört zu einem anderen Warenkorb.")
        bonus = purchase_bonus(db, existing["id"])
        check_purchase_discount(quoted_discount, sum(line["price"] * line["qty"] for line in bonus))
        return {"entry": existing["id"], "total": -existing["cents"], "balance": balance(db, person), "bonus": bonus,
                "stamps_earned": existing["loyalty_delta"] + LOYALTY_STAMPS * sum(line["qty"] for line in bonus)}

    pricing = purchase_pricing(db, person, cart, terminal)
    check_purchase_discount(quoted_discount, pricing["discount"])
    total = pricing["total"]
    delta = pricing["loyalty_delta"]
    at = now()
    booking = entry(db, person, "purchase", -total, request_id=request_id, terminal=terminal, kiosk_pending=True,
                    at=at, loyalty_delta=delta)
    with db.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO items (entry,product,name,price,quantity,bonus_quantity) VALUES (%s,%s,%s,%s,%s,%s)",
            ((booking, line["id"], line["name"], line["cents"], line["qty"], line["bonus_qty"])
             for line in pricing["lines"]),
        )
    bonus = [{"name": line["name"], "qty": line["bonus_qty"], "price": line["cents"]}
             for line in sorted(pricing["lines"], key=lambda line: line["id"]) if line["bonus_qty"]]
    redeemed = sum(line["qty"] for line in bonus)
    update_loyalty(db, person, delta, redeemed_delta=redeemed)
    add_monthly_sale(db, terminal, at, total, booking, reversal=False)
    return {"entry": booking, "total": total, "balance": balance(db, person), "bonus": bonus,
            "stamps_earned": delta + LOYALTY_STAMPS * redeemed}


def add_monthly_sale(db, terminal, at, cents, purchase, *, reversal):
    month = datetime.fromisoformat(at).astimezone(ZoneInfo("Europe/Berlin")).date().replace(day=1)
    gross, reversed_cents, orders = (0, cents, 0) if reversal else (cents, 0, 1)
    db.execute("""INSERT INTO monthly_sales (month,terminal,gross,reversed,orders) VALUES (%s,%s,%s,%s,%s)
                  ON CONFLICT(month,terminal) DO UPDATE SET gross=monthly_sales.gross+excluded.gross,
                  reversed=monthly_sales.reversed+excluded.reversed, orders=monthly_sales.orders+excluded.orders""",
               (month, terminal, gross, reversed_cents, orders))
    db.execute("""INSERT INTO monthly_products (month,terminal,product,name,sold,returned,net)
                  SELECT %s,%s,product,name,quantity*%s,quantity*%s,CAST(price AS BIGINT)*(quantity-bonus_quantity)*%s
                  FROM items WHERE entry=%s ORDER BY product
                  ON CONFLICT(month,terminal,product,name,name_recorded) DO UPDATE SET sold=monthly_products.sold+excluded.sold,
                  returned=monthly_products.returned+excluded.returned, net=monthly_products.net+excluded.net""",
               (month, terminal, int(not reversal), int(reversal), -1 if reversal else 1, purchase))


def _items_for_page(db, page):
    entry_ids = sorted({row["reverses"] or row["id"] for row in page})
    if not entry_ids:
        return {}
    placeholders = ", ".join(["%s"] * len(entry_ids))
    items = {}
    for line in db.execute(
        f"""SELECT entry,name,price,quantity,bonus_quantity FROM items
            WHERE entry IN ({placeholders}) ORDER BY entry,product""", entry_ids,
    ):
        item = dict(line)
        entry_id = item.pop("entry")
        if not item["bonus_quantity"]:
            item.pop("bonus_quantity")
        items.setdefault(entry_id, []).append(item)
    return items


def list_journal(db, person, before, terminal=None, *, cutoff=None, include_reversals=True):
    cutoff = cutoff if cutoff is not None else booking_cutoff()
    rows = db.execute(
        """SELECT j.*, p.first, p.last, p.department, r.id AS reversed_by, original.id AS retained_reverses, original.kind AS reversed_kind
           FROM journal j JOIN people p ON p.id=j.person LEFT JOIN journal r ON r.reverses=j.id
           LEFT JOIN journal original ON original.id=j.reverses AND original.at>%s
           WHERE j.id<%s AND j.at>%s AND (CAST(%s AS BIGINT) IS NULL OR j.person=%s)
             AND (CAST(%s AS TEXT) IS NULL OR j.terminal=%s) AND (%s OR j.kind <> 'reversal')
           ORDER BY j.id DESC LIMIT 51""",
        (cutoff, before, cutoff, person, person, terminal, terminal, include_reversals),
    ).fetchall()
    page = [dict(row) for row in rows[:50]]
    for row in page:
        row["reverses"] = row.pop("retained_reverses")
    items = _items_for_page(db, page)
    entries = []
    for row in page:
        item = dict(row)
        item.pop("request_id")
        item.pop("kiosk_pending")
        item["items"] = items.get(row["reverses"] or row["id"], [])
        entries.append(item)
    return {"entries": entries, "next": entries[-1]["id"] if len(rows) > 50 else None}


ADMIN_PEOPLE_PAGE_SIZE = 50
ADMIN_PEOPLE_SORTS = ("last", "first", "department", "balance")
_PERSON_BALANCE = "COALESCE(c.cents,0) + COALESCE((SELECT SUM(j.cents) FROM journal j WHERE j.person=p.id),0)"
_PERSON_SEARCH = """NOT EXISTS (
    SELECT FROM unnest(%s::text[]) AS search(word)
    WHERE strpos(lower(concat_ws(' ',p.first,p.last,p.department) COLLATE pg_catalog."de-x-icu"),
                 lower(search.word COLLATE pg_catalog."de-x-icu"))=0
)"""


def _natural_order(column):
    # Normalize case and accents, and pad digit groups so that R 2 sorts before R 10.
    return rf"""COALESCE((
        SELECT string_agg(CASE WHEN segment[1] IS NULL THEN segment[2] ELSE lpad(segment[1],80,'0') END,
                          '' ORDER BY position)
        FROM regexp_matches(regexp_replace(normalize(lower(p.{column} COLLATE pg_catalog."de-x-icu"), NFD),
                                           U&'[\0300-\036F]', '', 'g') COLLATE "C",
                            '([0-9]+)|([^0-9]+)', 'g') WITH ORDINALITY AS parts(segment, position)
    ), '') COLLATE pg_catalog."de-x-icu" """


def admin_summary(db):
    return dict(db.execute(
        """SELECT COALESCE(SUM(GREATEST(-balances.balance,0)),0)::bigint AS outstanding,
                  COALESCE(SUM(GREATEST(balances.balance,0)),0)::bigint AS credit,
                  COUNT(*) FILTER (WHERE balances.active<>0) AS active
           FROM (SELECT p.active, COALESCE(c.cents,0) + COALESCE(j.cents,0) AS balance
                 FROM people p LEFT JOIN carried_balances c ON c.person=p.id
                 LEFT JOIN (SELECT person, SUM(cents) AS cents FROM journal GROUP BY person) j ON j.person=p.id) balances"""
    ).fetchone())


def admin_people_page(db, version, privacy_version, words, sort, descending, page):
    if sort not in ADMIN_PEOPLE_SORTS:
        raise ValueError("Invalid account sort.")
    primary = _PERSON_BALANCE if sort == "balance" else _natural_order(sort)
    direction = "DESC" if descending else "ASC"
    tie_breakers = [_natural_order(key) for key in ("last", "first") if key != sort]
    order = ", ".join([f"{primary} {direction}", *tie_breakers, "p.id"])
    balances_join = "LEFT JOIN carried_balances c ON c.person=p.id" if sort == "balance" else ""
    size = ADMIN_PEOPLE_PAGE_SIZE
    rows = db.execute(
        f"""SELECT p.id FROM people p {balances_join} WHERE {_PERSON_SEARCH}
            ORDER BY {order} LIMIT %s OFFSET %s""",
        (words, size + 1, (page - 1) * size),
    ).fetchall()
    ids = [row["id"] for row in rows[:size]]
    people = []
    if ids:
        for row in db.execute(
            f"""SELECT p.id,p.first,p.last,p.department,p.active,p.created,p.card_type,p.card_medium,p.closed_at,
                       p.card IS NOT NULL AS has_card,
                       EXISTS(SELECT 1 FROM manual_credentials m WHERE m.person=p.id) AS manual_enabled,
                       {_PERSON_BALANCE} AS balance, COALESCE(l.progress,0) AS loyalty_progress,
                       COALESCE(l.redeemed,0) AS loyalty_redeemed,
                       EXISTS(SELECT 1 FROM policy_acceptances a WHERE a.person=p.id AND a.terms_version=%s
                              AND a.privacy_version=%s) AS terms_current
                FROM unnest(%s::bigint[]) WITH ORDINALITY AS page(id, position)
                JOIN people p ON p.id=page.id LEFT JOIN carried_balances c ON c.person=p.id
                LEFT JOIN loyalty_cards l ON l.person=p.id ORDER BY page.position""",
            (version, privacy_version, ids),
        ):
            person = dict(row)
            loyalty = loyalty_card_status(person.pop("loyalty_progress"))
            loyalty["redeemed"] = person.pop("loyalty_redeemed")
            person.update(balance=int(person["balance"]), loyalty=loyalty)
            people.append(person)
    return {"people": people, "page": page, "has_next": len(rows) > size}


def admin_account_options(db, words, page):
    size = ADMIN_PEOPLE_PAGE_SIZE
    rows = db.execute(
        f"""SELECT p.id,p.first,p.last,p.department FROM people p WHERE {_PERSON_SEARCH}
            ORDER BY {_natural_order("last")}, {_natural_order("first")}, p.id LIMIT %s OFFSET %s""",
        (words, size + 1, (page - 1) * size),
    ).fetchall()
    return {"people": [dict(row) for row in rows[:size]], "page": page, "has_next": len(rows) > size}


def people_overview(db, version, privacy_version=None):
    rows = db.execute(
        """SELECT p.id,p.first,p.last,p.department,p.active,p.created,p.card_type,p.card_medium,p.closed_at,
                  EXISTS(SELECT 1 FROM manual_credentials m WHERE m.person=p.id) AS manual_enabled,
                  COALESCE(c.cents,0) + COALESCE((SELECT SUM(j.cents) FROM journal j WHERE j.person=p.id),0) AS balance,
                  COALESCE(l.progress,0) AS loyalty_progress, COALESCE(l.redeemed,0) AS loyalty_redeemed
           FROM people p LEFT JOIN carried_balances c ON c.person=p.id
           LEFT JOIN loyalty_cards l ON l.person=p.id
           ORDER BY LOWER(p.last),LOWER(p.first),p.id"""
    )
    people = {}
    for row in rows:
        person = dict(row)
        loyalty = loyalty_card_status(person.pop("loyalty_progress"))
        loyalty["redeemed"] = person.pop("loyalty_redeemed")
        people[person["id"]] = {**person, "balance": int(person["balance"]), "loyalty": loyalty,
                                "consents": [], "terms_current": False}
    for row in db.execute(
        """SELECT person,terms_version AS version,privacy_version,accepted_at,terminal FROM policy_acceptances
           UNION ALL
           SELECT a.person,a.version,NULL,a.accepted_at,a.terminal FROM terms_acceptances a
           WHERE NOT EXISTS(SELECT 1 FROM policy_acceptances p WHERE p.person=a.person AND
             p.terms_version=a.version AND p.accepted_at=a.accepted_at AND p.terminal=a.terminal)
           ORDER BY accepted_at DESC,version DESC"""
    ):
        person = people[row["person"]]
        person["consents"].append({k: row[k] for k in ("version", "privacy_version", "accepted_at", "terminal")})
        if row["version"] == version and (privacy_version is None or row["privacy_version"] == privacy_version):
            person["terms_current"] = True
    return list(people.values())


def current_terms(db, default):
    row = db.execute("""SELECT t.document FROM settings s JOIN terms_versions t ON t.version=s.value
                      WHERE s.key='published_terms'""").fetchone()
    document = json.loads(row["document"]) if row else default
    if "date" not in document:
        # Previous releases encoded the publication date in the version ID.
        published = re.fullmatch(r"(\d{4})(\d{2})(\d{2})-[a-f0-9]{6}", document["version"])
        document = {**document, "date": "-".join(published.groups()) if published else None}
    return document


def current_privacy(db, default):
    row = db.execute("SELECT value FROM settings WHERE key='published_privacy'").fetchone()
    return json.loads(row["value"]) if row else default


def remember_privacy(db, document):
    payload = json.dumps(document, ensure_ascii=False, sort_keys=True)
    db.execute("INSERT INTO privacy_versions (version,document) VALUES (%s,%s) ON CONFLICT DO NOTHING",
               (document["version"], payload))


def publish_privacy(db, document, actor, previous):
    remember_privacy(db, document)
    db.execute("""INSERT INTO settings VALUES ('published_privacy', %s)
                  ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
               (json.dumps(document, ensure_ascii=False),))
    audit(db, actor, "Datenschutzerklärung aktualisiert.",
          {"Stand": previous["date"], "Text": previous["body"]},
          {"Stand": document["date"], "Text": document["body"]})


def terms_body(document):
    if "body" in document:
        return document["body"]
    return "\n\n".join([f"## {part['title']}\n{part['text']}" for part in document["sections"]] +
                        [f"## Kontakt bei Rückfragen\n**{document['contact']}**\n{document['reach']}"])


def publish_terms(db, body, actor, old_document):
    stand = datetime.now(ZoneInfo("Europe/Berlin")).date().isoformat()
    while True:
        version = datetime.now(timezone.utc).strftime("%Y%m%d") + "-" + secrets.token_hex(3)
        document = {"version": version, "body": body, "date": stand}
        if db.execute("INSERT INTO terms_versions VALUES (%s,%s) ON CONFLICT DO NOTHING",
                      (version, json.dumps(document, ensure_ascii=False, sort_keys=True))).rowcount:
            break
    db.execute("""INSERT INTO settings VALUES ('published_terms', %s)
                 ON CONFLICT(key) DO UPDATE SET value=excluded.value""", (version,))
    audit(db, actor, "Nutzungshinweise veröffentlicht.",
          {"Fassung": old_document["version"], "Text": terms_body(old_document)},
          {"Fassung": version, "Text": body})
    return document


def manual_people(db, term):
    needles = term.casefold().replace("(", " ").replace(")", " ").split()
    rows = db.execute("""SELECT p.id,p.first,p.last,p.department FROM people p
                        JOIN manual_credentials m ON m.person=p.id WHERE p.active=1
                        ORDER BY LOWER(p.last),LOWER(p.first),LOWER(p.department),p.id""")
    matches = []
    for row in rows:
        name = f"{row['first']} {row['last']}"
        searchable = f"{name} {row['department']}".casefold()
        if needles and all(needle in searchable for needle in needles):
            matches.append({"id": row["id"], "name": name, "department": row["department"]})
            if len(matches) == 30:
                break
    return matches


def personal_history(db, person, start, end, before, *, cutoff=None):
    cutoff = cutoff if cutoff is not None else booking_cutoff()
    values = [cutoff, person, start, end, cutoff]
    paging = ""
    if before is not None:
        cursor = db.execute("SELECT at,id FROM journal WHERE person=%s AND id=%s AND at>=%s AND at<%s AND at>%s",
                            (person, before, start, end, cutoff)).fetchone()
        if not cursor:
            raise Problem(400, "Ungültige Buchungsseite.")
        paging = " AND (j.at<%s OR (j.at=%s AND j.id<%s))"
        values.extend((cursor["at"], cursor["at"], before))
    rows = db.execute(
        """SELECT j.id,j.at,j.kind,j.cents,j.terminal,original.id AS reverses,original.kind AS reversed_kind,j.request_id FROM journal j
           LEFT JOIN journal original ON original.id=j.reverses AND original.at>%s
           WHERE j.person=%s AND j.at>=%s AND j.at<%s AND j.at>%s""" + paging +
        " ORDER BY j.at DESC,j.id DESC LIMIT 51", values
    ).fetchall()
    page = rows[:50]
    items = _items_for_page(db, page)
    entries = []
    for row in page:
        item = dict(row)
        request = item.pop("request_id") or ""
        item["method"] = ("Bar" if request.startswith("cash:") else
                          "PayPal" if request.startswith("paypal:") else None)
        item["items"] = items.get(row["reverses"] or row["id"], [])
        entries.append(item)
    return {"entries": entries, "next": entries[-1]["id"] if len(rows) > 50 else None}
