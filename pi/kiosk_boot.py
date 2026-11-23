"""Prepare labwc autostart and LightDM autologin on a Raspberry Pi desktop."""
import argparse
import os
from pathlib import Path
import re
import shutil
from tempfile import NamedTemporaryFile

LAUNCHER = "/opt/kaffeekasse-terminal/start-kiosk.sh"
MANAGED = re.compile(rf"\s*(?:KIOSK_SCALE=([0-9.]+)\s+)?{re.escape(LAUNCHER)}\s*&\s*")
SEATS = {"[Seat:*]", "[Seat:seat0]"}


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
    else:
        lightdm(args.user, args.session)


if __name__ == "__main__":
    main()
