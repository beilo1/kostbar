"""Build and runtime facts for the authenticated administration view."""
from importlib import metadata
import os
from pathlib import Path
import platform
import re

from api_reference import OPERATIONS
from pi.versions import PI_PACKAGES

ROOT = Path(__file__).resolve().parent


def checked_packages(payload):
    if not isinstance(payload, dict):
        return {}
    return {name: value for name in PI_PACKAGES
            if isinstance((value := payload.get(name)), str) and re.fullmatch(r"[0-9A-Za-z.+:~_-]{1,120}", value)}


def versions(db, terminals, caddy_version, deployment):
    compose = (ROOT / "compose.common.yml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    images = [("Python-Basisimage", re.search(r"^FROM\s+(\S+)", dockerfile, re.M)[1])]
    images.extend((name.split(":")[0], name) for name in re.findall(r"^\s+image:\s+(\w\S*)", compose, re.M))
    app_image = os.environ.get("KOSTBAR_APP_IMAGE")
    if app_image:
        images.append(("KoSTbar-App", app_image))
    pins = {}
    for line in requirements.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        requirement, pinned = line.strip().split("==", 1)
        pins[requirement.partition("[")[0].lower()] = (requirement, pinned)
    dependencies = []
    for dist in sorted(metadata.distributions(), key=lambda item: item.name.lower()):
        name = dist.name
        if name.lower() not in ("pip", "setuptools", "wheel"):
            label, pinned = pins.get(name.lower(), (name, "Abhängigkeit"))
            dependencies.append({"name": label, "pinned": pinned, "installed": dist.version})
    return {
        "python": platform.python_version(),
        "caddy": caddy_version,
        "pi_packages": PI_PACKAGES,
        "postgresql": db.execute("SHOW server_version").fetchone()["server_version"],
        "images": [{"name": name, "tag": tag} for name, tag in images],
        "dependencies": dependencies,
        "terminals": {key: terminal.reader_packages for key, terminal in terminals.items()},
        "terminal_reported_at": {key: terminal.reader_packages_at for key, terminal in terminals.items()},
        "deployment": {"qnap": "QNAP", "synology": "Synology"}[deployment],
        "operations": OPERATIONS,
    }
