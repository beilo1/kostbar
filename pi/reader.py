"""PC/SC bridge for a contactless CCID reader. Runs locally on the Raspberry Pi."""
import argparse
import hashlib
import hmac
import json
import logging
from pathlib import Path
import secrets
import time
from urllib.error import URLError

from device import CONFIG, INSTANCE_FILE, Device
from card_types import classify, CARD_TYPES
from versions import installed_packages

from smartcard import scard as pcsc

GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]
DEFAULT_CONFIG = CONFIG


class ReaderError(Exception):
    pass


def checked(result, label):
    status, *outputs = result
    if status != pcsc.SCARD_S_SUCCESS:
        raise ReaderError(f"{label}: {pcsc.SCardGetErrorMessage(status)}")
    return outputs


def contactless_reader(context, match):
    status, names = pcsc.SCardListReaders(context, [])
    if status == pcsc.SCARD_E_NO_READERS_AVAILABLE:
        return None
    names, = checked((status, names), "Leser auflisten")
    matches = [name for name in names if match.casefold() in name.casefold()
               and "sam" not in name.casefold()]
    contactless = [name for name in matches if any(
        part in name.casefold() for part in ("picc", "contactless", "cl reader")
    )]
    candidates = contactless or matches
    if len(candidates) > 1:
        raise ReaderError("Mehrere Leser passen. reader_match auf den eindeutigen PC/SC-Namen setzen.")
    return candidates[0] if candidates else None


def read_uid(context, reader):
    handle, protocol = checked(pcsc.SCardConnect(context, reader, pcsc.SCARD_SHARE_SHARED,
                                                pcsc.SCARD_PROTOCOL_T0 | pcsc.SCARD_PROTOCOL_T1),
                               "Karte öffnen")
    try:
        result, = checked(pcsc.SCardTransmit(handle, protocol, GET_UID), "UID lesen")
    finally:
        pcsc.SCardDisconnect(handle, pcsc.SCARD_LEAVE_CARD)
    if result[-2:] != [0x90, 0x00] or not 4 <= len(result) - 2 <= 10:
        return None, "Die Kartenkennung konnte nicht gelesen werden."
    uid = bytes(result[:-2])
    if len(uid) == 4 and uid[0] == 0x08:
        return None, "Der Ausweis meldet eine wechselnde Kartenkennung."
    return uid, None


def send(device, body):
    try:
        with device.request("POST", "/internal/reader", json.dumps(body).encode(),
                            {"Content-Type": "application/json"}, timeout=2) as response:
            return response.status == 200
    except (URLError, OSError):
        return False


def watch(settings, probe, device, instance):
    mask_key = secrets.token_bytes(32)
    reader = None
    context = None
    present = False
    pending = None
    heartbeat = 0
    last_error = None
    next_inventory = 0
    while True:
        try:
            if context is None:
                context, = checked(pcsc.SCardEstablishContext(pcsc.SCARD_SCOPE_SYSTEM), "PC/SC starten")
            selected = contactless_reader(context, settings.get("reader_match", "ACR"))
            if selected != reader:
                reader, present, pending, heartbeat = selected, False, None, 0
                logging.info("Leser: %s", reader or "kein passender Leser")
            if reader:
                changes, = checked(pcsc.SCardGetStatusChange(context, 0, [(reader, pcsc.SCARD_STATE_UNAWARE)]),
                                   "Kartenstatus lesen")
                _, flags, atr = changes[0]
                card_present = bool(flags & pcsc.SCARD_STATE_PRESENT)
                if card_present and not present:
                    uid, issue = read_uid(context, reader)
                    card_type = classify(atr)
                    if probe:
                        if issue:
                            print(issue, flush=True)
                        else:
                            masked = hmac.new(mask_key, uid, hashlib.sha256).hexdigest()[:12]
                            print(f"Karte erkannt · {len(uid)} Byte · Testkennung {masked}"
                                  f" · {CARD_TYPES.get(card_type, 'Typ nicht bestimmt')}", flush=True)
                    else:
                        pending = {"issue": issue} if issue else {"uid": uid.hex().upper()}
                        if not issue and card_type:
                            pending["card_type"] = card_type
                if not card_present:
                    pending = None
                present = card_present
            if not probe and (pending or time.monotonic() - heartbeat >= 2):
                payload = {"instance": instance, "connected": bool(reader), **(pending or {})}
                report_inventory = time.monotonic() >= next_inventory
                if report_inventory:
                    payload["packages"] = installed_packages()
                if send(device, payload):
                    pending = None
                    if report_inventory:
                        next_inventory = time.monotonic() + 60
                heartbeat = time.monotonic()
            last_error = None
            time.sleep(0.25 if reader else 1)
        except ReaderError as exc:
            if str(exc) != last_error:
                logging.warning("%s", exc)
                last_error = str(exc)
            if context is not None:
                pcsc.SCardReleaseContext(context)
            context, reader, present, pending = None, None, False, None
            if not probe:
                send(device, {"instance": instance, "connected": False})
            time.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--probe", action="store_true", help="Nur prüfen. Kartenkennungen werden vor der Anzeige maskiert.")
    parser.add_argument("--match", help="PC/SC-Lesername oder eindeutiger Teil davon (nur mit --probe).")
    args = parser.parse_args()
    if args.match and not args.probe:
        parser.error("--match erfordert --probe")
    device = None if args.probe else Device(args.config)
    instance = None if args.probe else INSTANCE_FILE.read_text(encoding="ascii").strip()
    settings = {"reader_match": args.match or "ACR"} if args.probe else device.settings
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.probe:
        print("Ausweis kurz anhalten, entfernen und erneut anhalten. Beenden mit Strg+C.", flush=True)
    try:
        watch(settings, args.probe, device, instance)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
