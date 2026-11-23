"""Settings and HTTPS client shared by the Raspberry Pi bridge and reader."""
import json
from pathlib import Path
import re
import ssl
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler, HTTPRedirectHandler, ProxyHandler, Request, build_opener

CONFIG = Path("/etc/kaffeekasse-terminal/device.json")
INSTANCE_FILE = CONFIG.with_name("reader-instance")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class Device:
    def __init__(self, config=CONFIG):
        self.settings = json.loads(config.read_text(encoding="utf-8"))
        origin = self.settings["origin"]
        site = self.settings["terminal"]
        key = self.settings["token"]
        parsed = urlsplit(origin)
        if parsed.scheme != "https" or not parsed.hostname or origin != "https://" + parsed.netloc or parsed.username:
            raise ValueError("origin muss eine interne HTTPS-Adresse ohne Pfad sein.")
        if (not isinstance(site, str) or len(site) > 32
                or not re.fullmatch(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*", site)
                or not isinstance(key, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{43,120}", key)):
            raise ValueError("Verkaufspunktkennung und Gerätetoken prüfen.")
        context = ssl.create_default_context(cafile=self.settings.get("ca_file"))
        self.opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPSHandler(context=context))
        self.base = f"{origin}/terminal/{site}"
        self.token = key

    def request(self, method, path, body=None, headers=None, timeout=4):
        return self.opener.open(Request(self.base + path, method=method, data=body,
                                        headers={**(headers or {}), "X-Terminal-Token": self.token}), timeout=timeout)
