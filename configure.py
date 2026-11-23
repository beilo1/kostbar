"""Generate initial NAS configuration and private Pi device profiles."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
from urllib.parse import urlsplit


def valid_terminal_id(value):
    return (isinstance(value, str) and len(value) <= 32
            and re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", value) is not None)


def device_profile(origin, terminal, secret, ca_file):
    return {"origin": origin, "terminal": terminal, "token": secret,
            "ca_file": ca_file, "reader_match": "ACR"}


def token():
    return secrets.token_urlsafe(32)


def config(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Konfiguration kann nicht gelesen werden: {exc}") from exc


def required_text(value, limit, label):
    if not isinstance(value, str):
        raise ValueError(f"{label} fehlt.")
    value = " ".join(value.split())
    if not value or len(value) > limit or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError(f"{label} muss zwischen 1 und {limit} Zeichen lang sein.")
    return value


def valid_origin(value):
    try:
        url = urlsplit(value)
        host, port = url.hostname, url.port
        if host and re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host) and ".." not in host:
            authority = f"{host}:{port}" if port else host
            if value == f"https://{authority}" and port != 443:
                return authority
    except (TypeError, ValueError):
        pass
    raise SystemExit("origin muss eine kleingeschriebene HTTPS-Adresse ohne Pfad sein. Port 443 dabei weglassen.")


def paypal_url(value):
    if value is None or value == "" or value == "https://paypal.me/test":
        return None
    if not isinstance(value, str) or not re.fullmatch(r"https://paypal\.me/[A-Za-z0-9]{1,100}", value):
        raise ValueError("PayPal-Link muss die Form https://paypal.me/DeinName haben.")
    return value


def write(path, content):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--deployment", required=True, choices=("qnap", "synology"))
    parser.add_argument("--origin", help="HTTPS-Adresse. Pflicht für Synology. QNAP-Standard: https://kostbar.internal.lan:18443")
    parser.add_argument("--nas-ip", type=ipaddress.IPv4Address, help="Feste LAN-IP des QNAP-NAS")
    parser.add_argument("--label-a", default="Verkaufspunkt A")
    parser.add_argument("--label-b", help="Optionalen zweiten Verkaufspunkt gleich einrichten")
    parser.add_argument("--reader-ca", action="store_true", help="Eigene HTTPS-CA auch am Synology-Pi verwenden")
    parser.add_argument("--contact-name", required=True)
    parser.add_argument("--contact-reach", required=True)
    parser.add_argument("--paypal-url")
    args = parser.parse_args()
    if args.deployment == "qnap" and args.nas_ip is None:
        parser.error("--nas-ip ist beim QNAP-Deployment erforderlich.")
    if args.deployment == "synology" and args.nas_ip is not None:
        parser.error("--nas-ip gilt nur für QNAP; Synology bindet intern an 127.0.0.1.")
    base = Path(__file__).resolve().parent / {"qnap": "QNAP", "synology": "Synology"}[args.deployment]
    deployment = config(base / "nas" / "deployment.json")
    external_url = args.origin or deployment.get("default_origin")
    if not external_url:
        parser.error("--origin ist beim Synology-Deployment erforderlich.")
    try:
        payment_link = paypal_url(args.paypal_url)
        contact_name = required_text(args.contact_name, 100, "Ansprechpartner")
        contact_reach = required_text(args.contact_reach, 160, "Erreichbarkeit")
        labels = {key: required_text(label, 60, "Verkaufspunkt")
                  for key, label in (("a", args.label_a), ("b", args.label_b)) if label is not None}
    except ValueError as exc:
        parser.error(str(exc))
    valid_origin(external_url)
    origin = urlsplit(external_url)
    ca_file = "/etc/kaffeekasse-terminal/nas-root.crt" if args.reader_ca else deployment["ca_file"]
    cfg = {"deployment": args.deployment, "origin": external_url, "card_key": secrets.token_hex(32), "self_registration": True,
           "reader_ca_file": ca_file,
           "paypal_url": payment_link,
           "terms": {"version": "6", "payment_notice": True, "department_notice": True, "kostbar_brand": True,
                     "contact_name": contact_name, "contact_reach": contact_reach},
           "terminals": {key: {"label": label, "token": token()} for key, label in labels.items()}}
    environment = [
        f"KASSE_DB_PASSWORD={secrets.token_hex(32)}",
        f"POSTGRES_ADMIN_PASSWORD={secrets.token_hex(32)}",
    ]
    if args.deployment == "synology":
        environment += [f"KASSE_AUTHORITY={origin.netloc}", "KASSE_DSM_PORT=18765", f"KASSE_DSM_PROXY_KEY={secrets.token_hex(32)}"]
    else:
        environment += [f"KASSE_HOST={origin.hostname}", f"KASSE_PORT={origin.port or 443}",
                        f"KASSE_BIND_IP={args.nas_ip}"]
    files = {
        base / ".env": "\n".join(environment),
        base / "config" / "server.json": json.dumps(cfg, ensure_ascii=False, indent=2),
    }
    for key, terminal in cfg["terminals"].items():
        files[base / "config" / f"terminal-{key}.json"] = json.dumps(
            device_profile(external_url, key, terminal["token"], ca_file), indent=2
        )
    if any(path.exists() for path in files):
        raise SystemExit("Eine Zieldatei existiert bereits. Bestehende Konfiguration beibehalten.")
    (base / "config").mkdir(mode=0o700, exist_ok=True)
    for path, content in files.items():
        write(path, content)
    profiles = ", ".join(f"config/terminal-{key}.json" for key in labels)
    print(f"Erstellt in {base.name}/: .env, config/server.json und {profiles}.")


if __name__ == "__main__":
    main()
