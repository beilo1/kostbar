"""Prepare labwc autostart and LightDM autologin on a Raspberry Pi desktop."""
import argparse
import os
from pathlib import Path
import re
import shutil
import struct
from tempfile import NamedTemporaryFile
from xml.dom import Node, minidom

LAUNCHER = "/opt/kaffeekasse-terminal/start-kiosk.sh"
MANAGED = re.compile(rf"\s*(?:KIOSK_SCALE=([0-9.]+)\s+)?{re.escape(LAUNCHER)}\s*&\s*")
SEATS = {"[Seat:*]", "[Seat:seat0]"}
CURSOR_THEME = "KoSTbar-Transparent"


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

    target = home / ".config/labwc/environment"
    default = Path("/etc/xdg/labwc/environment")
    source = target if target.is_file() else default
    current = source.read_text(encoding="utf-8") if source.is_file() else ""
    setting = f"XCURSOR_THEME={CURSOR_THEME}"
    lines = [line for line in current.splitlines() if line.strip() != setting]
    desired = "\n".join([*lines, setting]) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    if source != target or current != desired:
        target.write_text(desired, encoding="utf-8")


def enable_touch(home):
    target = home / ".config/labwc/rc.xml"
    default = Path("/etc/xdg/labwc/rc.xml")
    source = target if target.is_file() else default
    document = minidom.parse(str(source)) if source.is_file() else minidom.parseString("<labwc_config/>")
    root = document.documentElement
    devices = [child for child in root.childNodes
               if child.nodeType == Node.ELEMENT_NODE and child.localName == "touch"]
    if not devices:
        devices = [root.appendChild(document.createElement("touch"))]

    changed = not target.is_file()
    for device in devices:
        options = [child for child in device.childNodes
                   if child.nodeType == Node.ELEMENT_NODE and child.localName == "mouseEmulation"]
        for option in options:
            if option.firstChild and option.firstChild.nodeValue == "no":
                continue
            while option.firstChild:
                option.removeChild(option.firstChild)
            option.appendChild(document.createTextNode("no"))
            changed = True
        if (device.hasAttribute("mouseEmulation") or not options) and device.getAttribute("mouseEmulation") != "no":
            device.setAttribute("mouseEmulation", "no")
            changed = True

    if changed:
        backup = target.with_name("rc.xml.pre-kostbar-touch")
        if target.is_file() and not backup.exists():
            shutil.copy2(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(dir=target.parent, delete=False) as temp:
            temp_path = Path(temp.name)
            temp.write(document.toxml(encoding="UTF-8") + b"\n")
        try:
            temp_path.replace(target)
        finally:
            temp_path.unlink(missing_ok=True)


def autostart(home, scale):
    target = home / ".config/labwc/autostart"
    default = Path("/etc/xdg/labwc/autostart")
    source = target if target.is_file() else default
    lines = source.read_text().splitlines() if source.is_file() else []
    managed = [match for line in lines if (match := MANAGED.fullmatch(line))]
    scale = scale or next((match[1] for match in managed if match[1]), "")
    if scale and not re.fullmatch(r"(?:0\.[5-9]|[12](?:\.[0-9])?|3(?:\.0)?)", scale):
        raise SystemExit("KIOSK_SCALE muss zwischen 0.5 und 3.0 liegen, mit höchstens einer Nachkommastelle.")
    prefix = f"KIOSK_SCALE={scale} " if scale else ""
    kept = [line for line in lines if not MANAGED.fullmatch(line)]
    desired = "\n".join(kept + [f"{prefix}{LAUNCHER} &"]) + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.is_file() or target.read_text() != desired:
        target.write_text(desired)


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
    start = sub.add_parser("autostart")
    start.add_argument("home", type=Path)
    start.add_argument("scale", nargs="?", default="")
    login = sub.add_parser("lightdm")
    login.add_argument("user")
    login.add_argument("session")
    args = parser.parse_args()
    if args.action == "autostart":
        autostart(args.home, args.scale)
        hide_cursor(args.home)
        enable_touch(args.home)
    else:
        lightdm(args.user, args.session)


if __name__ == "__main__":
    main()
