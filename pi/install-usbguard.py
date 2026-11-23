#!/usr/bin/env python3
"""Set up USBGuard for one directly connected ACS CCID reader on a KoSTbar Pi."""

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import NamedTemporaryFile
from time import sleep

CONFIG = Path("/etc/usbguard/usbguard-daemon.conf")
RULES = CONFIG.with_name("kostbar.rules")
CMDLINE = Path("/boot/firmware/cmdline.txt")
USB_DEFAULT = "usbcore.authorized_default=0"
PORT = r"[0-9]+-[0-9]+"


def run(*command):
    return subprocess.run(command, check=True, text=True, stdout=subprocess.PIPE).stdout


def reader_rule(policy, port):
    location = f' via-port "{port}"'
    candidates = [line for line in policy.splitlines() if location in line]
    if len(candidates) != 1:
        raise ValueError(f"Am Port {port} wurde kein eindeutiges USB-Gerät gefunden.")
    rule = candidates[0]
    interface = re.search(r" with-interface (?:equals )?(\{[^}]+\}|[a-f0-9:]+)(?= with-connect-type |$)", rule)
    if (not re.match(r"allow id 072f:[a-f0-9]{4} ", rule)
            or not re.search(r' hash "[A-Za-z0-9+/=]+"', rule)
            or not re.search(r' parent-hash "[A-Za-z0-9+/=]+"', rule)
            or not interface):
        raise ValueError(f"Am Port {port} wurde keine vollständige Regel für einen ACS-Kartenleser erkannt.")
    classes = interface[1].strip("{}").split()
    if not classes or any(not re.fullmatch(r"0b:[a-f0-9]{2}:[a-f0-9]{2}", item) for item in classes):
        raise ValueError("Der Leser muss im reinen CCID-Modus laufen. HID- und andere Schnittstellen werden gesperrt.")
    return rule[:interface.start()] + " with-interface equals { " + " ".join(classes) + " }" + rule[interface.end():]


def daemon_config(original):
    options = {
        "RuleFile": str(RULES),
        "ImplicitPolicyTarget": "block",
        "PresentDevicePolicy": "apply-policy",
        "PresentControllerPolicy": "keep",
        "InsertedDevicePolicy": "apply-policy",
        "AuthorizedDefault": "none",
        "RestoreControllerDeviceState": "false",
        "DeviceManagerBackend": "uevent",
        "IPCAllowedUsers": "root",
        "HidePII": "true",
    }
    replaced = options.keys() | {"RuleFolder", "IPCAllowedGroups", "IPCAccessControlFiles"}
    lines = [line for line in original.splitlines() if line.partition("=")[0].strip() not in replaced]
    lines.extend(f"{key}={value}" for key, value in options.items())
    return "\n".join(lines) + "\n"


def replace(path, contents, mode=None):
    with NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
        temp = Path(file.name)
        try:
            file.write(contents)
            file.flush()
            os.fsync(file.fileno())
            if mode is not None:
                os.fchmod(file.fileno(), mode)
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)


def install(port):
    cmdline = CMDLINE
    original_boot = cmdline.read_text(encoding="utf-8")
    lines = original_boot.strip().splitlines()
    if len(lines) != 1:
        raise ValueError(f"{cmdline} muss genau eine Zeile mit den Bootparametern enthalten.")
    for mountpoint in ("/", str(cmdline.parent)):
        source = run("findmnt", "-n", "-o", "SOURCE", "--mountpoint", mountpoint).strip()
        if not re.fullmatch(r"/dev/mmcblk[0-9]+p[0-9]+", source):
            raise ValueError(f"{mountpoint} liegt nicht auf microSD. USB-Boot-Datenträger würden gesperrt.")
    boot_args = re.sub(r"(?<!\S)usbcore\.authorized_default=\S+", "", lines[0]).rstrip()

    original_config = CONFIG.read_text(encoding="utf-8")
    original_rules = RULES.read_text(encoding="utf-8") if RULES.is_file() else None
    rule = reader_rule(run("usbguard", "generate-policy", "--with-ports"), port)
    for path in (CONFIG, cmdline):
        backup = path.with_name(path.name + ".pre-kostbar")
        if not backup.exists():
            shutil.copyfile(path, backup)
            if path == CONFIG:
                backup.chmod(0o600)

    service = "usbguard.service"
    was_active = subprocess.run(["systemctl", "is-active", "--quiet", service]).returncode == 0
    was_enabled = subprocess.run(["systemctl", "is-enabled", "--quiet", service]).returncode == 0
    try:
        replace(RULES, rule + "\n", 0o600)
        replace(CONFIG, daemon_config(original_config), 0o600)
        run("systemctl", "restart", service)
        for _ in range(10):
            devices = run("usbguard", "list-devices", "--allowed")
            if any(f' via-port "{port}"' in line and "allow id 072f:" in line for line in devices.splitlines()):
                break
            sleep(0.5)
        else:
            raise ValueError("USBGuard hat den Kartenleser nicht freigegeben. Prüfe Modus, Port und Dienstprotokoll.")
        run("systemctl", "enable", service)
        replace(cmdline, f"{boot_args} {USB_DEFAULT}\n")
    except (OSError, ValueError, subprocess.CalledProcessError):
        replace(CONFIG, original_config, 0o600)
        if original_rules is None:
            RULES.unlink(missing_ok=True)
        else:
            replace(RULES, original_rules, 0o600)
        if not was_enabled:
            subprocess.run(["systemctl", "disable", service], check=False)
        subprocess.run(["systemctl", "restart" if was_active else "stop", service], check=False)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", help="USBGuard-Port des direkt angeschlossenen ACS-Lesers, z. B. 1-2")
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error("Über SSH mit sudo aufrufen.")
    if not re.fullmatch(PORT, args.port):
        parser.error("Der Leser muss direkt am Pi angeschlossen sein. Gib den Port aus via-port an.")
    try:
        install(args.port)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"USB-Schutz konnte nicht eingerichtet werden. {error}\n")
    print("USBGuard ist aktiv. Starte den Pi neu und prüfe Kartenanmeldung und Sperre wie in der Anleitung.")


if __name__ == "__main__":
    main()
