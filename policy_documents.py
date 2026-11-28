"""Build, load and upgrade the published policy documents."""

from pathlib import Path
import re
import secrets

import finance
import store as data
from validation import string


CARD_NOTICE = (
    "Die Kennung deines Dienstausweises (UID) wird nicht im Klartext gespeichert. "
    "Für die Wiedererkennung wird daraus mit einem geheimen Schlüssel ein Prüfwert "
    "(HMAC-SHA-256) gebildet und gespeichert. Die ursprüngliche Kennung wird nur "
    "während des Lese- und Anmeldevorgangs verarbeitet."
)
STORAGE_NOTICE = "Die Datenhaltung auf dem NAS erfolgt auf verschlüsseltem Speicher im internen Netzwerk."
ADMIN_LOGIN_NOTICE = (
    "Das Kassen-Team meldet sich für die Verwaltung mit einem persönlichen Anmeldenamen und Passwort an. "
    "Im Betrieb wird das Passwort verschlüsselt über HTTPS übertragen. Auf dem NAS wird nur ein "
    "Einweg-Prüfwert (scrypt-Hash) mit einem zufälligen Zusatzwert (Salt) gespeichert. "
    "Bei der Anmeldung wird der Prüfwert erneut berechnet und verglichen. "
    "Zum Schutz gegen wiederholte Fehlversuche begrenzt KoSTbar Anmeldungen je Anmeldename und Quell-IP. "
    "Die Zähler werden vorübergehend im Arbeitsspeicher geführt."
)
BOOKING_RETENTION_NOTICE = (
    "Personenbezogene Buchungsdetails zu Einkäufen, Zahlungen, Stornos und Korrekturen werden auf dem NAS "
    "höchstens 90 Tage in der laufenden Anwendung vorgehalten und danach automatisch gelöscht. "
    "Aus älteren Buchungen bleibt je Konto nur der zusammengefasste Saldoübertrag erhalten. "
    "Offene Beträge und Guthaben bleiben erhalten. Monatsauswertungen enthalten auch danach Summen "
    "pro Verkaufspunkt und Produkt ohne Kontozuordnung. Offene PayPal-Meldungen verfallen nach 90 Tagen ohne Gutschrift. "
    "Für bestätigte und abgelehnte Meldungen beginnt die Frist mit der Buchung bzw. Entscheidung. "
    "Zum Schutz vor Doppelbuchungen bleibt ein Prüfwert bestätigter PayPal-Transaktionen ohne Kontozuordnung erhalten. "
    "Geschlossene Konten werden nach dem Saldenausgleich und Ablauf der verbleibenden Buchungs- und PayPal-Fristen gelöscht. "
    "Allgemeine Verwaltungsprotokolle haben eine Frist von 180 Tagen. Sicherungen und Exporte haben eigene Fristen."
)
TERMINAL_STORAGE_NOTICE = (
    "Die Raspberry Pis dienen als Anzeige und Eingabegeräte mit Kartenleser. Sie verarbeiten die für die "
    "Bedienung nötigen KoSTbar-Daten vorübergehend im Arbeitsspeicher. Eine dauerhafte lokale Speicherung "
    "von Personen-, Buchungs- oder Saldodaten findet auf den Terminals nicht statt. "
    "Anwendungslogik und Datenbank laufen zentral auf dem NAS."
)
KIOSK_PAIRING_NOTICE = (
    "Der Browser am Terminal speichert eine Gerätekennung als technisch notwendiges Cookie. "
    "Sie ordnet das Gerät dem Verkaufspunkt zu. Das Kassen-Team kann diese Zuordnung aufheben."
)
LEGACY_TERMINAL_WIFI_NOTICE = (
    "Bei der Ersteinrichtung beziehen die Terminals Systemupdates über ein WLAN mit gemeinsamem Kennwort. "
    "Für den Produktivbetrieb melden sich die Raspberry Pis mit je einem Gerätezertifikat am internen WLAN an "
    "(WPA-Enterprise mit EAP-TLS). Ein zentraler RADIUS-Dienst prüft die Geräteanmeldung. "
    "Die Verbindung der Terminals zur Kasse läuft über HTTPS."
)
TERMINAL_WIFI_NOTICE = (
    "Bei der Ersteinrichtung beziehen die Terminals Systemupdates über ein WLAN mit gemeinsamem Kennwort. "
    "Im Betrieb melden sich die Raspberry Pis mit einem eigenen Benutzernamen und Passwort am internen Terminal-WLAN an "
    "(WPA2-Enterprise mit PEAP/MSCHAPv2). Der RADIUS-Dienst prüft den Zugang. "
    "Die Terminals prüfen das RADIUS-Serverzertifikat und verbinden sich über HTTPS mit der Kasse."
)
TERMINAL_WIFI_PRIVACY_NOTICE = (
    "Für den Zugang zum internen WLAN verwendet jedes Terminal ein technisches Gerätekonto beim RADIUS-Dienst. "
    "Die WLAN-Zugangsdaten werden außerhalb von KoSTbar verwaltet und sind keinem Kassenkonto zugeordnet."
)
LOYALTY_NOTICE = (
    "Für jedes bezahlte Heißgetränk erhältst du einen Stempel, auch wenn du mehrere auf einmal kaufst. "
    "Nach zehn Stempeln wird ein Heißgetränk automatisch gratis. Bei mehreren Heißgetränken im selben "
    "Warenkorb werden zuerst die günstigsten rabattiert. Gratisgetränke bringen keine Stempel. "
    "Die Sammelkarte hat kein Ablaufdatum und gilt an allen Verkaufspunkten. Bei einem Storno "
    "wird die Karte entsprechend korrigiert."
)
LOYALTY_PRIVACY_NOTICE = (
    "Für die Sammelkarte wird der aktuelle Punktestand deinem Konto zugeordnet und ohne Ablaufdatum gespeichert. "
    "Dieser Stand enthält keine Liste von Einkäufen, Produkten, Zeitpunkten oder Verkaufspunkten. "
    "Buchungsbezogene Angaben zu Stempeln und Gratisgetränken werden zusammen mit den Einzelbuchungen "
    "nach 90 Tagen gelöscht. Bei der Löschung des Kontos wird auch der Sammelkartenstand gelöscht."
)
LOYALTY_ADMIN_PRIVACY_NOTICE = (
    "KoSTbar speichert zusätzlich die Gesamtzahl der eingelösten Gratisgetränke ohne Ablaufdatum. "
    "Stornierte Gratisgetränke werden abgezogen. Das Kassen-Team kann beide Zähler pro Konto einsehen. "
    "Bei der Kontolöschung entfällt auch dieser Zähler."
)
PIN_TERMS_NOTICE = (
    "Bei der Registrierung vergibst und bestätigst du eine vierstellige PIN. "
    "Damit meldest du dich über die Namenssuche ohne Karte an. "
    "Wenn du die PIN vergisst, kann das Kassen-Team sie zurücksetzen. "
    "Bei der nächsten Anmeldung mit Karte vergibst du selbst eine neue PIN."
)
TERMS_LIMIT = 16000
DEFAULT_PRIVACY = {
    "version": "vorlage-9",
    "date": "2026-11-24",
    "template": True,
    "body": Path(__file__).with_name("privacy.md").read_text(encoding="utf-8").strip(),
}


def document_body(body):
    raw = body.get("body")
    if not isinstance(raw, str):
        raise data.Problem(400, "Text fehlt.")
    draft = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not draft or len(draft) > TERMS_LIMIT or any(ord(c) < 32 and c not in "\n\t" for c in draft):
        raise data.Problem(400, "Der Text muss 1 bis 16.000 Zeichen lang sein.")
    return draft


def terms_document(cfg):
    terms = cfg["terms"]
    version = terms["version"]
    if not isinstance(version, str) or not re.fullmatch(r"[a-zA-Z0-9._-]{1,40}", version):
        raise SystemExit("Ungültige terms.version.")
    document = {
        "version": version,
        "contact": string(terms.get("contact_name"), 100, "Ansprechpartner"),
        "reach": string(terms.get("contact_reach"), 160, "Erreichbarkeit"),
        "sections": [
            {"title": "Freiwillige Nutzung", "text": "Das Terminal vereinfacht und digitalisiert die Abrechnung "
             "der Kaffeekasse. Die Nutzung ist freiwillig. Du kannst weiterhin bar bezahlen. "
             "Das Kassen-Team verbucht erhaltene Zahlungen bei Bedarf auf deinem Kassenkonto."},
            {"title": "Was gespeichert wird", "text": "Die Kaffeekasse speichert Vor- und Nachname, eine "
             "pseudonymisierte Kartenkennung, Einkäufe, Zahlungen, Korrekturen, den jeweiligen Verkaufspunkt "
             "bei Käufen sowie Version und Zeitpunkt der Zustimmung. Der Saldo ergibt sich aus den Buchungen. "
             "Dienstbezogene Daten wie Personalnummer, Arbeitszeiten und Zutrittsprotokolle werden nicht erhoben. "
             "Vom Dienstausweis wird nur die technisch lesbare Kartenkennung verarbeitet. "
             "Du kannst deine eigenen Buchungen am Terminal einsehen. Die Verwaltung der Konten und das gemeinsame Kassenbuch "
             "sind dem Kassen-Team vorbehalten."},
            {"title": "Lokaler Betrieb", "text": "Die Daten werden zentral auf dem NAS im internen Netz gespeichert. "
             "Für Anmeldung, Einkauf und Barzahlung genügt im laufenden Betrieb das lokale Netz mit gültigen HTTPS-Zertifikaten. "
             "Die Ersteinrichtung und die Erneuerung eines öffentlich ausgestellten Zertifikats können Internetzugang benötigen. "
             "PayPal ist optional und wird auf dem eigenen Gerät über das Internet genutzt. "
             "Beide Raspberry Pis greifen per HTTPS auf das NAS zu. Der Kartenleser ist jeweils am Raspberry Pi angeschlossen."},
            {"title": "Verwendete Technik", "text": "Auf dem NAS laufen Docker Compose, Caddy, "
             "ein Python-Backend mit Waitress und Psycopg sowie PostgreSQL. "
             "Die Oberfläche nutzt HTML, CSS und JavaScript. Auf dem Raspberry Pi zeigt Chromium die Kasse an. "
             "Der Kartenleser wird über USB, PC/SC (pcscd und libccid) sowie Python mit pyscard angesprochen."},
        ],
    }

    if terms.get("department_notice"):
        stored = document["sections"][1]
        stored["text"] = stored["text"].replace("Vor- und Nachname, eine", "Vorname, Nachname, Referat, eine")

    if terms.get("payment_notice"):
        document["sections"] += [
            {"title": "Zahlungen", "text": "Eingetragenes Bargeld wird auf Vertrauensbasis sofort gutgeschrieben. "
             "PayPal-Meldungen werden erst nach Prüfung des Zahlungseingangs durch das Kassen-Team gutgeschrieben. "
             "Dabei werden Betrag, Referenz und die PayPal-Transaktions-ID gespeichert. "
             "Der QR-Code öffnet PayPal auf deinem Mobilgerät."},
        ]
    document["sections"].append({"title": "Anmeldung ohne Karte", "text": PIN_TERMS_NOTICE})
    if terms.get("kostbar_brand"):
        for section in document["sections"]:
            section["text"] = section["text"].replace("der Kaffeekasse", "von KoSTbar").replace(
                "Die Kaffeekasse speichert", "KoSTbar speichert"
            )
    return document


def _mark_notice(conn, marker):
    return conn.execute("INSERT INTO settings (key,value) VALUES (%s,'1') ON CONFLICT DO NOTHING",
                        (marker,)).rowcount


def _load_privacy(conn):
    privacy = data.current_privacy(conn, DEFAULT_PRIVACY)
    data.remember_privacy(conn, privacy)
    privacy_body = privacy["body"]
    for marker, heading, notice in (
        ("loyalty_privacy_notice_v1", "Sammelkarte", LOYALTY_PRIVACY_NOTICE),
        ("loyalty_admin_privacy_notice_v1", "Sammelkarte im Admin-Bereich", LOYALTY_ADMIN_PRIVACY_NOTICE),
        ("terminal_wifi_privacy_notice_v1", "Netzzugang der Terminals", TERMINAL_WIFI_PRIVACY_NOTICE),
    ):
        added = _mark_notice(conn, marker)
        if added and notice not in privacy_body:
            privacy_body += f"\n\n## {heading}\n{notice}"
    if privacy_body != privacy["body"]:
        previous = privacy
        privacy = {**previous, "version": secrets.token_hex(12),
                   "date": finance.local_date(data.now()).date().isoformat(), "body": privacy_body}
        data.publish_privacy(conn, privacy, "System", previous)
    return privacy


def _timeout_notice(session_idle, receipt_seconds, cash_receipt_seconds):
    return (
        f"Am gemeinsam genutzten Terminal endet deine Sitzung nach {session_idle} Sekunden ohne Eingabe. "
        f"Nach einem gebuchten Einkauf wirst du nach {receipt_seconds} Sekunden, nach einer gebuchten Barzahlung "
        f"nach {cash_receipt_seconds} Sekunden "
        "automatisch abgemeldet. Dadurch sind deine Kontodaten für die nächste Person am Terminal nicht mehr sichtbar."
    )


def _upgrade_terms(conn, terms, deployment, *, session_idle, receipt_seconds, cash_receipt_seconds):
    timeout_notice = _timeout_notice(session_idle, receipt_seconds, cash_receipt_seconds)
    original_body = body = data.terms_body(terms)
    if _mark_notice(conn, "kiosk_timeout_notice_v2"):
        legacy = (
            "Am gemeinsam genutzten Terminal endet deine Sitzung nach 15 Sekunden ohne Eingabe. "
            "Nach einem gebuchten Einkauf oder einer gebuchten Barzahlung wirst du nach 5 Sekunden "
            "automatisch abgemeldet. Dadurch sind deine Kontodaten für die nächste Person am Terminal nicht mehr sichtbar."
        )
        body = body.replace(legacy, timeout_notice).replace(_timeout_notice(15, 8, 5), timeout_notice)
    if _mark_notice(conn, "terminal_wifi_notice_v2"):
        body = body.replace(LEGACY_TERMINAL_WIFI_NOTICE, TERMINAL_WIFI_NOTICE)
    for marker, title, notices in (
        ("card_storage_notice_v1", "Schutz deiner Ausweiskennung und Daten", (CARD_NOTICE, STORAGE_NOTICE)),
        ("admin_login_notice_v1", "Schutz der Verwaltungszugänge", (ADMIN_LOGIN_NOTICE,)),
        ("booking_retention_notice_v2", "Aufbewahrung von Buchungen", (BOOKING_RETENTION_NOTICE,)),
        ("loyalty_terms_notice_v1", "Sammelkarte", (LOYALTY_NOTICE,)),
        ("terminal_storage_notice_v1", "Datenspeicherung auf den Terminals", (TERMINAL_STORAGE_NOTICE,)),
        ("kiosk_timeout_notice_v1", "Automatische Abmeldung am Terminal", (timeout_notice,)),
        ("kiosk_pairing_notice_v1", "Zuordnung der Terminals", (KIOSK_PAIRING_NOTICE,)),
        ("terminal_wifi_notice_v1", "Netzzugang der Terminals", (TERMINAL_WIFI_NOTICE,)),
        ("reader_and_runtime_notice_v1", "Karten und technischer Betrieb",
         ("KoSTbar speichert zusätzlich zum Prüfwert den vom Leser gemeldeten Kartentyp, sofern er bestimmbar ist. "
          "Das Kassen-Team kann hinterlegen, ob ein Dienstausweis, ein NFC-Schlüsselanhänger oder ein anderer Träger verwendet wird.",
          ("HTTPS endet bei diesem NAS am DSM Reverse Proxy. Caddy leitet die Anfragen intern an das Backend weiter."
           if deployment == "synology" else "Caddy stellt HTTPS mit seiner lokalen Zertifizierungsstelle bereit."),)),
    ):
        added = _mark_notice(conn, marker)
        if added and marker == "reader_and_runtime_notice_v1":
            body = body.replace(
                "Vom Dienstausweis wird nur die technisch lesbare Kartenkennung verarbeitet.",
                "Zur Anmeldung verarbeitet KoSTbar die technisch lesbare Kartenkennung.",
            )
        missing = [notice for notice in notices if notice not in body]
        if added and missing:
            body += f"\n\n## {title}\n" + "\n\n".join(missing)
    if body != original_body:
        terms = data.publish_terms(conn, body, "System", terms)
    return terms


def load_documents(conn, default_terms, deployment, *, session_idle, receipt_seconds, cash_receipt_seconds):
    terms = data.current_terms(conn, default_terms)
    privacy = _load_privacy(conn)
    terms = _upgrade_terms(conn, terms, deployment, session_idle=session_idle, receipt_seconds=receipt_seconds,
                           cash_receipt_seconds=cash_receipt_seconds)
    return terms, privacy
