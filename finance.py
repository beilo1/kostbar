"""Local payment workflow, reporting and administrative spreadsheet exports."""
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from io import BytesIO
import math
import re
from zoneinfo import ZoneInfo

import store

CASH_MAX_CENTS = 10_000
EXCEL_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
KINDS = {"purchase": "Kauf", "payment": "Zahlung", "correction": "Korrektur", "reversal": "Storno"}


@dataclass(frozen=True)
class Download:
    content: bytes
    mime: str
    name: str | None = None


@lru_cache(maxsize=16)
def paypal_qr(link):
    import qrcode
    from qrcode.image.svg import SvgPathImage

    output = BytesIO()
    qrcode.make(link, image_factory=SvgPathImage, border=4).save(output)
    return Download(output.getvalue(), "image/svg+xml")


def cash(db, person, terminal, key, cents):
    key = "cash:" + key
    row = db.execute("SELECT id,cents,terminal,at>%s AS fresh FROM journal WHERE person=%s AND request_id=%s",
                     (store.booking_cutoff(), person, key)).fetchone()
    if row:
        if not row["fresh"]:
            raise store.Problem(409, "Diese Buchungskennung ist abgelaufen.")
        if row["terminal"] != terminal or row["cents"] != cents:
            raise store.Problem(409, "Diese Vorgangskennung gehört zu einer anderen Zahlung.")
        booking = row["id"]
    else:
        booking = store.entry(db, person, "payment", cents, note="Barzahlung am Terminal (Selbsteintrag)",
                              request_id=key, terminal=terminal, kiosk_pending=True)
    return {"entry": booking, "total": cents, "balance": store.balance(db, person), "kind": "cash"}


def paypal_prepare(db, person, terminal, key, cents, *, link=None):
    while True:
        row = db.execute("SELECT *, created>%s AS fresh FROM paypal_requests WHERE person=%s AND request_id=%s",
                         (store.booking_cutoff(), person, key)).fetchone()
        if row:
            if (row["terminal"] != terminal or row["cents"] != cents
                    or (row["recipient_link"] is not None and row["recipient_link"] != link)):
                raise store.Problem(409, "Diese Vorgangskennung gehört zu einer anderen Zahlung.")
            if row["status"] != "pending":
                raise store.Problem(409, "Diese PayPal-Meldung wurde bereits bearbeitet.")
            if not row["fresh"]:
                raise store.Problem(409, "Diese PayPal-Meldung ist abgelaufen.")
            return row["reference"]
        seq = db.execute("""INSERT INTO settings VALUES ('paypal_reference_counter','1')
                            ON CONFLICT(key) DO UPDATE SET value=CAST(CAST(settings.value AS BIGINT)+1 AS TEXT)
                            RETURNING value""").fetchone()["value"]
        reference = "KK-" + seq
        if db.execute("""INSERT INTO paypal_requests (person,terminal,request_id,reference,cents,created,recipient_link)
                         VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                      (person, terminal, key, reference, cents, store.now(), link)).rowcount:
            return reference


def paypal_for_person(db, person):
    return [dict(row) for row in db.execute(
        """SELECT reference,cents,status,recipient_link FROM paypal_requests
           WHERE person=%s AND status='pending' AND COALESCE(resolved,created)>%s
           ORDER BY id DESC LIMIT 20""", (person, store.booking_cutoff())
    )]


def paypal_overview(db, status, before):
    rows = [dict(row) for row in db.execute(
        """SELECT r.id,r.reference,r.terminal,r.cents,r.created,r.status,r.resolved,r.actor,r.note,r.transaction_ref,r.recipient_link,
                  p.first,p.last,p.department,j.cents AS credited
           FROM paypal_requests r JOIN people p ON p.id=r.person LEFT JOIN journal j ON j.id=r.journal_id
           WHERE r.status=%s AND r.id<%s AND COALESCE(r.resolved,r.created)>%s
           ORDER BY r.id DESC LIMIT 51""", (status, before, store.booking_cutoff())
    )]
    return {"payments": rows[:50], "next": rows[49]["id"] if len(rows) > 50 else None}


def paypal_resolve(db, payment, actor, cents=None, transaction=None, note=None, *, key):
    account = db.execute("""SELECT p.id FROM people p JOIN paypal_requests r ON r.person=p.id
                            WHERE r.id=%s FOR NO KEY UPDATE OF p""", (payment,)).fetchone()
    if not account:
        raise store.Problem(404, "Zahlung nicht gefunden.")
    row = db.execute("SELECT * FROM paypal_requests WHERE id=%s AND COALESCE(resolved,created)>%s FOR UPDATE",
                     (payment, store.booking_cutoff())).fetchone()
    if not row:
        raise store.Problem(404, "Zahlung nicht gefunden.")
    if row["status"] != "pending":
        # An identical confirmation is harmless when the first response was lost.
        if row["status"] == "confirmed" and transaction == row["transaction_ref"]:
            saved = db.execute("SELECT cents FROM journal WHERE id=%s", (row["journal_id"],)).fetchone()
            if saved["cents"] == cents:
                return
        raise store.Problem(409, "Dieser PayPal-Vorgang ist bereits bearbeitet.")
    resolved = store.now()
    if transaction:
        if db.execute("""SELECT 1 FROM paypal_requests WHERE transaction_ref=%s
                         UNION ALL SELECT 1 FROM paypal_used_fingerprints WHERE digest=%s""",
                      (transaction, store.paypal_fingerprint(key, transaction))).fetchone():
            raise store.Problem(409, "Diese PayPal-Transaktions-ID wurde bereits verbucht.")
        description = f"PayPal bestätigt · {row['reference']}"
        booking = store.entry(db, row["person"], "payment", cents, actor, description,
                              request_id=f"paypal:{payment}", terminal=row["terminal"], at=resolved)
        db.execute("""UPDATE paypal_requests SET status='confirmed',resolved=%s,actor=%s,
                      transaction_ref=%s,journal_id=%s WHERE id=%s""",
                   (resolved, actor, transaction, booking, payment))
        store.audit(db, actor, f"PayPal-Zahlung {row['reference']} bestätigt.",
                    {"Status": "Offen", "Gemeldet (Cent)": row["cents"]},
                    {"Status": "Bestätigt", "Gemeldet (Cent)": row["cents"], "Gutgeschrieben (Cent)": cents},
                    booking_detail=True, person=row["person"], at=resolved)
    else:
        db.execute("UPDATE paypal_requests SET status='rejected',resolved=%s,actor=%s,note=%s WHERE id=%s",
                   (resolved, actor, note, payment))
        store.audit(db, actor, f"PayPal-Zahlung {row['reference']} abgelehnt.",
                    {"Status": "Offen", "Gemeldet (Cent)": row["cents"]},
                    {"Status": "Abgelehnt", "Gemeldet (Cent)": row["cents"], "Begründung": note},
                    booking_detail=True, person=row["person"], at=resolved)


def local_date(value):
    stamp = datetime.fromisoformat(value) if isinstance(value, str) else value
    return stamp.astimezone(ZoneInfo("Europe/Berlin"))


def month_bounds(month):
    berlin = ZoneInfo("Europe/Berlin")
    if not month:
        month = datetime.now(berlin).strftime("%Y-%m")
    if not isinstance(month, str) or not re.fullmatch(r"20[0-9]{2}-(?:0[1-9]|1[0-2])", month):
        raise store.Problem(400, "Monat im Format JJJJ-MM angeben.")
    year, period = map(int, month.split("-"))
    first = datetime(year, period, 1, tzinfo=berlin)
    last = datetime(year + (period == 12), period % 12 + 1, 1, tzinfo=berlin)
    start, end = (value.astimezone(timezone.utc).isoformat(timespec="seconds") for value in (first, last))
    return month, start, end


def monthly(db, month, terminal):
    month, start, end = month_bounds(month)
    month_start = f"{month}-01"
    cutoff = store.booking_cutoff()
    coverage = "expired" if end <= cutoff else "partial" if start <= cutoff else "complete"
    totals = db.execute(
        """SELECT COALESCE(SUM(gross),0) AS gross, COALESCE(SUM(reversed),0) AS reversed,
                  COALESCE(SUM(orders),0) AS orders
           FROM monthly_sales WHERE month=%s AND (CAST(%s AS TEXT) IS NULL OR terminal=%s)""",
        (month_start, terminal, terminal),
    ).fetchone()
    products = db.execute(
        """SELECT m.product AS id,m.name,m.name_recorded,SUM(m.sold) AS sold,SUM(m.returned) AS returned,SUM(m.net) AS net
           FROM monthly_products m
           WHERE m.month=%s AND (CAST(%s AS TEXT) IS NULL OR m.terminal=%s)
           GROUP BY m.product,m.name,m.name_recorded ORDER BY sold DESC,LOWER(m.name),m.product,m.name_recorded""",
        (month_start, terminal, terminal),
    )
    amounts = {key: int(totals[key]) for key in ("gross", "reversed", "orders")}
    rows = [{"id": row["id"], "name": row["name"] if row["name_recorded"] else f"Historische Bezeichnung unbekannt (Produkt #{row['id']})",
             "name_recorded": row["name_recorded"],
             **{key: int(row[key]) for key in ("sold", "returned", "net")}} for row in products]
    return {"month": month, "coverage": coverage, **amounts, "products": rows,
            "unallocated": max(0, sum(row["net"] for row in rows) - amounts["gross"] + amounts["reversed"])}


def workbook(title, stamp, detail=False):
    from xlsxwriter import Workbook

    output = BytesIO()
    book = Workbook(output, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False})
    sheet = book.add_worksheet("Kontoauszug" if detail else "Salden")
    sheet.set_paper(9)
    if detail:
        sheet.set_landscape()
    sheet.set_margins(0.32, 0.32, 0.53, 0.53)
    sheet.fit_to_pages(1, 0)
    sheet.set_header(f"&L&B{title}&B&RStichtag {stamp:%d.%m.%Y %H:%M}", {"margin": 0.22})
    sheet.set_footer("&LKoSTbar&RSeite &P von &N", {"margin": 0.22})
    sheet.repeat_rows(0, 3)
    sheet.freeze_panes(4, 0)
    sheet.hide_gridlines(2)
    text = {"font_name": "Calibri", "font_size": 11, "valign": "vcenter", "text_wrap": True}
    band = {"bg_color": "#E7F2E9"}
    styles = {
        "title": book.add_format({**text, "bold": True, "font_size": 17, "font_color": "#163C31"}),
        "meta": book.add_format({**text, "font_color": "#31544A"}),
        "head": book.add_format({**text, "bold": True, "bg_color": "#21483B", "font_color": "#FFFFFF"}),
        "text": book.add_format(text),
        "date": book.add_format({**text, "num_format": "dd.mm.yyyy hh:mm"}),
        "money": book.add_format({**text, "num_format": '#,##0.00 "€";[Red]-#,##0.00 "€";0.00 "€"'}),
        "band": book.add_format({**text, **band}),
        "band_date": book.add_format({**text, **band, "num_format": "dd.mm.yyyy hh:mm"}),
        "band_money": book.add_format({**text, **band, "num_format": '#,##0.00 "€";[Red]-#,##0.00 "€";0.00 "€"'}),
    }
    sheet.set_row(0, 27)
    sheet.set_row(3, 23)
    return output, book, sheet, styles


def sheet_columns(sheet, style, headers, widths):
    for col, width in enumerate(widths):
        sheet.set_column(col, col, width)
    sheet.write_row(3, 0, headers, style)


def balances_export(db, stamp):
    rows = db.execute(
        """SELECT p.id,p.first,p.last,p.department,p.active,
                  COALESCE(c.cents,0) + COALESCE((SELECT SUM(j.cents) FROM journal j WHERE j.person=p.id),0) AS balance
           FROM people p LEFT JOIN carried_balances c ON c.person=p.id
           ORDER BY LOWER(p.last),LOWER(p.first),p.id"""
    ).fetchall()
    output, book, sheet, style = workbook("Saldenliste", stamp)
    sheet.merge_range(0, 0, 0, 5, "Saldenliste aller Konten", style["title"])
    sheet.merge_range(1, 0, 1, 5, f"Stichtag {stamp:%d.%m.%Y %H:%M} · Saldo unter null bedeutet offener Betrag", style["meta"])
    sheet_columns(sheet, style["head"], ["Nachname", "Vorname", "Referat", "Status", "Saldo", "Offen"],
                  [19, 16, 19, 11, 13, 13])
    outstanding = 0
    for i, row in enumerate(rows, 4):
        balance = int(row["balance"])
        outstanding += max(0, -balance)
        sheet.set_row(i, 15 * max(math.ceil(len(row["last"]) / 17), math.ceil(len(row["first"]) / 14),
                                  math.ceil(len(row["department"]) / 17), 1))
        sheet.write_row(i, 0, [row["last"], row["first"], row["department"], "Aktiv" if row["active"] else "Gesperrt"],
                        style["text"])
        sheet.write_number(i, 4, balance / 100, style["money"])
        sheet.write_number(i, 5, max(0, -balance) / 100, style["money"])
    last = 4 + len(rows)
    sheet.merge_range(last, 0, last, 4, "Summe offene Beträge", style["band"])
    sheet.write_number(last, 5, outstanding / 100, style["band_money"])
    sheet.print_area(0, 0, last, 5)
    book.close()
    return Download(output.getvalue(), EXCEL_MIME, f"Salden-{stamp:%Y-%m-%d}.xlsx")


def account_export(db, person, terminals, stamp):
    profile = db.execute("SELECT first,last,department FROM people WHERE id=%s", (person,)).fetchone()
    if not profile:
        raise store.Problem(404, "Konto nicht gefunden.")
    cutoff = store.booking_cutoff(stamp.astimezone(timezone.utc))
    carried = store.carried_balance(db, person) + int(db.execute(
        "SELECT COALESCE(SUM(cents),0) AS total FROM journal WHERE person=%s AND at<=%s", (person, cutoff)
    ).fetchone()["total"])
    entries = db.execute("""SELECT j.id,j.kind,j.cents,j.at,j.note,purchase.id AS reverses,j.terminal
                          FROM journal j LEFT JOIN journal purchase ON purchase.id=j.reverses AND purchase.at>%s
                          WHERE j.person=%s AND j.at>%s ORDER BY j.id""", (cutoff, person, cutoff)).fetchall()
    details = {}
    for row in db.execute(
        """SELECT j.id,i.name,i.price,i.quantity,i.bonus_quantity FROM journal j
           LEFT JOIN journal purchase ON purchase.id=j.reverses AND purchase.at>%s
           JOIN items i ON i.entry=COALESCE(purchase.id,j.id)
           WHERE j.person=%s AND j.at>%s ORDER BY j.id,i.product""", (cutoff, person, cutoff)
    ):
        details.setdefault(row["id"], []).append(row)
    output, book, sheet, style = workbook("Kontoauszug", stamp, detail=True)
    name = f"{profile['first']} {profile['last']}"
    sheet.merge_range(0, 0, 0, 7, f"Kontoauszug · {name}", style["title"])
    sheet.merge_range(1, 0, 1, 6, f"Stichtag {stamp:%d.%m.%Y %H:%M} · Saldo zum Stichtag", style["meta"])
    sheet.write_number(1, 7, (carried + sum(row["cents"] for row in entries)) / 100, style["band_money"])
    sheet.merge_range(2, 0, 2, 7, "Referat · " + (profile["department"] or "—") +
                      " · Einzelbuchungen der letzten 90 Tage", style["meta"])
    sheet_columns(sheet, style["head"], ["Zeitpunkt", "Buchung", "Verkaufspunkt", "Details / Artikel",
                  "Menge", "Stückpreis", "Betrag", "Saldo"], [21, 15, 20, 33, 8, 13, 13, 14])
    i, balance = 4, carried
    if carried:
        sheet.merge_range(i, 0, i, 6, "Saldoübertrag aus älteren Buchungen", style["band"])
        sheet.write_number(i, 7, carried / 100, style["band_money"])
        i += 1
    for row in entries:
        balance += row["cents"]
        label = (f"Zu Kauf #{row['reverses']} · " if row["reverses"] else "") + (row["note"] or "")
        terminal = terminals.get(row["terminal"], "")
        sheet.set_row(i, 15 * max(math.ceil(len(label) / 30), math.ceil(len(terminal) / 17), 1))
        sheet.write_datetime(i, 0, local_date(row["at"]).replace(tzinfo=None), style["band_date"])
        sheet.write_row(i, 1, [f"{KINDS[row['kind']]} #{row['id']}", terminal, label], style["band"])
        for col in (4, 5):
            sheet.write_blank(i, col, None, style["band"])
        sheet.write_number(i, 6, row["cents"] / 100, style["band_money"])
        sheet.write_number(i, 7, balance / 100, style["band_money"])
        i += 1
        for detail in details.get(row["id"], ()):
            bonus = detail["bonus_quantity"]
            positions = ((detail["name"], detail["quantity"] - bonus, detail["price"]),
                         (detail["name"] + " · Sammelkartenbonus", bonus, 0))
            for name, quantity, price in positions:
                if quantity:
                    sheet.set_row(i, 15 * max(math.ceil(len(name) / 30), 1))
                    sheet.write(i, 3, name, style["text"])
                    sheet.write_number(i, 4, quantity, style["text"])
                    sheet.write_number(i, 5, price / 100, style["money"])
                    i += 1
    if not entries:
        sheet.merge_range(i, 0, i, 7, "Für dieses Konto liegen keine Einzelbuchungen der letzten 90 Tage vor.", style["text"])
        i += 1
    sheet.print_area(0, 0, i - 1, 7)
    book.close()
    return Download(output.getvalue(), EXCEL_MIME, f"Kontoauszug-{person}-{stamp:%Y-%m-%d}.xlsx")
