"""Generate the dedicated Wayland session and configure LightDM autologin."""
import argparse
import json
import math
import os
import re
import shutil
import struct
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

LAUNCHER = "/opt/kaffeekasse-terminal/start-kiosk.sh"
MANAGED = re.compile(rf"\s*(?:KIOSK_SCALE=([0-9.]+)\s+)?{re.escape(LAUNCHER)}\s*&\s*")
SEATS = {"[Seat:*]", "[Seat:seat0]"}
CURSOR_THEME = "KoSTbar-Transparent"
SCALE = re.compile(r"(?:0\.[5-9]|[12](?:\.[0-9])?|3(?:\.0)?)")
ORIGIN = re.compile(r"https://([a-z0-9](?:[a-z0-9.-]*[a-z0-9])?)(?::[1-9][0-9]{0,4})?")
SOURCE = Path(__file__).resolve().parent


def hide_cursor(home):
    theme = home / ".icons" / CURSOR_THEME
    cursors = theme / "cursors"
    cursors.mkdir(parents=True, exist_ok=True)
    (theme / "index.theme").write_text("[Icon Theme]\nName=KoSTbar Transparent\n", encoding="utf-8")

    # Xcursor header, one image entry, one fully transparent ARGB pixel.
    image_type = 0xfffd0002
    header = struct.pack("<4sIII", b"Xcur", 16, 0x10000, 1)
    entry = struct.pack("<3I", image_type, 24, 28)
    image = struct.pack("<10I", 36, image_type, 24, 1, 1, 1, 0, 0, 0, 0)
    # Include the installed themes' cursor names, including PiXflat aliases.
    names = {"default", "left_ptr", "arrow", "pointer", "hand2", "text", "xterm"}
    names.update(path.name for path in Path("/usr/share/icons").glob("*/cursors/*") if path.is_file())
    for name in sorted(names):
        (cursors / name).write_bytes(header + entry + image)


def kiosk_rc(home):
    config = ET.parse(SOURCE / "kiosk-rc.xml").getroot()
    legacy = home / ".config/labwc/rc.xml"
    if not legacy.is_file():
        legacy = Path("/etc/xdg/labwc/rc.xml")
    previous = ET.parse(legacy).getroot() if legacy.is_file() else ET.Element("labwc_config")
    touch_devices = previous.findall("{*}touch")
    for device in touch_devices:
        # Carry over display mappings only. The desktop configuration stays unused.
        attributes = {"mouseEmulation": "no"}
        for name in ("deviceName", "mapToOutput"):
            value = device.get(name) or device.findtext(f"{{*}}{name}")
            if value:
                attributes[name] = value.strip()
        ET.SubElement(config, "touch", attributes)
    if not touch_devices:
        ET.SubElement(config, "touch", mouseEmulation="no")
    calibrations = ET.Element("libinput")
    for device in previous.findall("{*}libinput/{*}device"):
        matrix = (device.get("calibrationMatrix") or device.findtext("{*}calibrationMatrix", "")).split()
        try:
            valid = len(matrix) == 6 and all(math.isfinite(float(value)) for value in matrix)
        except ValueError:
            valid = False
        if valid:
            category = device.get("category") or device.findtext("{*}category", "") or "default"
            target = ET.SubElement(calibrations, "device", category=category)
            ET.SubElement(target, "calibrationMatrix").text = " ".join(matrix)
    if len(calibrations):
        config.append(calibrations)
    ET.indent(config)
    return ET.tostring(config, encoding="unicode")


def saved_scale(path):
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            match = MANAGED.fullmatch(line)
            if match and match[1] and SCALE.fullmatch(match[1]):
                return match[1]
    return ""


def autostart(scale):
    if scale and not SCALE.fullmatch(scale):
        raise SystemExit("KIOSK_SCALE muss zwischen 0.5 und 3.0 liegen, mit höchstens einer Nachkommastelle.")
    prefix = f"KIOSK_SCALE={scale} " if scale else ""
    return f"{prefix}{LAUNCHER} &"


def chromium_policy(origin):
    if not isinstance(origin, str) or not ORIGIN.fullmatch(origin):
        raise SystemExit("Das Geräteprofil benötigt eine HTTPS-Adresse ohne Pfad.")
    address = urlsplit(origin)
    try:
        host, port = address.hostname, address.port or 443
    except ValueError as exc:
        raise SystemExit("Ungültiger HTTPS-Port im Geräteprofil.") from exc
    if ".." in host:
        raise SystemExit("Ungültiger Hostname im Geräteprofil.")
    terminal = f"https://.{host}:{port}"
    policy = json.loads((SOURCE / "chromium-policy.json").read_text(encoding="utf-8"))
    policy["URLBlocklist"] += [f"{terminal}/admin", f"{terminal}/api/admin"]
    policy["URLAllowlist"].insert(0, terminal)
    return policy


def update_seats(text, user, session):
    settings = {"autologin-user": user, "autologin-user-timeout": "0",
                "autologin-session": session, "autologin-guest": "false"}
    output = []
    group = ""
    seen = set()
    for line in text.splitlines():
        clean = line.strip()
        if clean.startswith("[") and clean.endswith("]"):
            group = clean
            output.append(line)
            if group in SEATS:
                seen.add(group)
                output.extend(f"{name}={value}" for name, value in settings.items())
        elif group not in SEATS or clean.partition("=")[0].strip() not in settings:
            output.append(line)
    if "[Seat:*]" not in seen:
        # Place the fallback before any specific seats.
        output = ["[Seat:*]", *(f"{name}={value}" for name, value in settings.items()), "", *output]
    return "\n".join(output) + "\n"


def lightdm(user, session):
    conf = Path("/etc/lightdm/lightdm.conf").resolve()
    text = conf.read_text()
    desired = update_seats(text, user, session)
    if text == desired:
        return
    backup = conf.with_name(conf.name + ".pre-kaffeekasse")
    if not backup.exists():
        shutil.copy2(conf, backup)
    previous = conf.with_name(conf.name + ".pre-kostbar-kiosk-session")
    if not previous.exists():
        shutil.copy2(conf, previous)
    permissions = conf.stat()
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=conf.parent, delete=False) as temp:
        target = Path(temp.name)
        try:
            temp.write(desired)
            temp.flush()
            os.fchown(temp.fileno(), permissions.st_uid, permissions.st_gid)
            os.fchmod(temp.fileno(), permissions.st_mode & 0o777)
            os.replace(target, conf)
        finally:
            target.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("cursor", "rc"):
        sub.add_parser(action).add_argument("home", type=Path)
    sub.add_parser("saved-scale").add_argument("autostart", type=Path)
    sub.add_parser("autostart").add_argument("scale")
    sub.add_parser("policy").add_argument("profile", type=Path)
    login = sub.add_parser("lightdm")
    login.add_argument("user")
    login.add_argument("session")
    args = parser.parse_args()
    if args.action == "cursor":
        hide_cursor(args.home)
    elif args.action == "rc":
        print(kiosk_rc(args.home))
    elif args.action == "saved-scale":
        print(saved_scale(args.autostart))
    elif args.action == "autostart":
        print(autostart(args.scale))
    elif args.action == "policy":
        profile = json.loads(args.profile.read_text(encoding="utf-8"))
        print(json.dumps(chromium_policy(profile["origin"]), indent=2))
    else:
        lightdm(args.user, args.session)


if __name__ == "__main__":
    main()
