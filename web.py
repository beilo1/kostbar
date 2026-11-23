"""HTTP routing, request parsing and response handling for Waitress."""
from datetime import datetime, timezone
import hmac
from http import HTTPStatus
from http.cookies import CookieError, SimpleCookie
from ipaddress import ip_address
import json
import logging
from pathlib import Path
import re
import socket
from urllib.parse import parse_qs, urlsplit

from api_reference import METHODS, READER_PATH
from finance import Download
from store import Problem

STATIC = Path(__file__).resolve().parent / "static"
LICENSE = STATIC.parent / "LICENSE"
MIME = {".html": "text/html", ".css": "text/css", ".js": "text/javascript", ".woff2": "font/woff2",
        ".svg": "image/svg+xml"}
ASSETS = {p.name: p for p in STATIC.iterdir() if p.is_file() and p.suffix in (".css", ".js")}
ASSETS["kostbar-logo.svg"] = STATIC / "kostbar-logo.svg"
ASSETS["favicon.svg"] = STATIC / "favicon.svg"
ASSETS["project-qr.svg"] = STATIC / "project-qr.svg"
ASSETS["print-document.html"] = STATIC / "print-document.html"
ASSETS.update({f"fonts/{p.name}": p for p in (STATIC / "fonts").glob("*.woff2") if p.is_file()})
SECURITY = {
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
                               "font-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY", "Cache-Control": "no-store",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def normalized_ip(value):
    address = ip_address(value)
    return str(getattr(address, "ipv4_mapped", None) or address)


def json_value(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat(timespec="seconds")
    raise TypeError(f"Unerwarteter JSON-Typ: {type(value).__name__}")


class WsgiApp:
    def __init__(self, app):
        self.app = app

    def proxy_peer(self, environ):
        peer = normalized_ip(environ["REMOTE_ADDR"])
        # Only the Compose reverse proxy may supply the client IP.
        try:
            addresses = {normalized_ip(info[4][0])
                         for info in socket.getaddrinfo("proxy", None, type=socket.SOCK_STREAM)}
        except OSError as exc:
            raise Problem(503, "Der Verwaltungszugang über den HTTPS-Proxy ist nicht verfügbar.") from exc
        return peer in addresses

    def admin_source_ip(self, environ):
        forwarded = environ.get("HTTP_X_KOSTBAR_CLIENT_IP")
        if forwarded and self.proxy_peer(environ):
            try:
                return normalized_ip(forwarded)
            except ValueError:
                pass
        raise Problem(503, "Der Verwaltungszugang über den HTTPS-Proxy ist nicht verfügbar.")

    @staticmethod
    def body(environ, limit):
        if environ.get("CONTENT_TYPE", "").split(";", 1)[0].strip().lower() != "application/json":
            raise Problem(415, "JSON erwartet.")
        length = int(environ.get("CONTENT_LENGTH") or "0")
        if not 1 <= length <= limit:
            raise Problem(413, "Ungültige Größe der Anfrage.")
        raw = environ["wsgi.input"].read(length)
        if len(raw) != length:
            raise Problem(400, "Unvollständige Anfrage.")
        try:
            result = json.loads(raw)
        except (ValueError, RecursionError) as exc:
            raise Problem(400, "Ungültige JSON-Daten.") from exc
        if not isinstance(result, dict):
            raise Problem(400, "JSON-Objekt erwartet.")
        return result

    def dispatch(self, environ):
        app = self.app
        if environ.get("HTTP_HOST") != app.host:
            raise Problem(421, "Unbekannter Host.")
        method = environ["REQUEST_METHOD"]
        if method not in ("GET", "POST"):
            raise Problem(405, "Diese HTTP-Methode wird nicht unterstützt.")
        # Waitress provides the raw URI, so encoded path separators never become routing delimiters.
        uri = environ.get("REQUEST_URI")
        url = urlsplit(uri) if uri is not None else None
        if url and (url.netloc or url.scheme or url.fragment or not url.path.startswith("/")):
            raise Problem(400, "Ungültige Anfrage.")
        path = url.path if url else environ["PATH_INFO"]
        terminal = None
        if path.startswith("/terminal/"):
            key, _, suffix = path.removeprefix("/terminal/").partition("/")
            terminal = app.terminals.get(key)
            if not terminal or suffix != "internal/reader" or method != "POST":
                raise Problem(404, "Unbekannter Verkaufspunkt.")
            path = "/" + suffix
            if not hmac.compare_digest(environ.get("HTTP_X_TERMINAL_TOKEN", "").encode(), terminal.secret.encode()):
                raise Problem(403, "Terminal nicht autorisiert.")
        if method == "POST" and not terminal and environ.get("HTTP_ORIGIN") != app.origin:
            raise Problem(403, "Anfrage kommt von einer fremden Seite.")
        if method == "GET":
            if path == "/license":
                return LICENSE.read_bytes(), "text/plain; charset=utf-8", None, None
            file = ASSETS.get(path.removeprefix("/static/")) if path.startswith("/static/") else None
            if path == "/privacy":
                file = STATIC / "privacy.html"
            elif path == "/terms":
                file = STATIC / "terms.html"
            elif path in ("/", "/kiosk", "/kiosk/"):
                file = STATIC / "index.html"
            elif path == "/admin":
                file = STATIC / "admin.html"
            if file:
                content = file.read_bytes()
                if file.name == "print-document.html":
                    # The downloaded print document must also work offline.
                    content = content.replace(b"@@LOGO@@", ASSETS["kostbar-logo.svg"].read_bytes(), 1)
                return content, MIME[file.suffix], None, None
        reference_path = READER_PATH if terminal else path
        methods = METHODS.get(reference_path)
        if not methods:
            raise Problem(404, "Seite nicht gefunden.")
        if method not in methods:
            raise Problem(405, "Diese HTTP-Methode wird nicht unterstützt.")
        large_document = not terminal and path in ("/api/admin/terms", "/api/admin/privacy")
        body = self.body(environ, 65536 if large_document else 16384) if method == "POST" else {}
        query = parse_qs(url.query if url else environ["QUERY_STRING"], max_num_fields=8)
        if not terminal and method == "POST" and path == "/api/admin/login":
            payload, cookie = app.login(body, self.admin_source_ip(environ))
        else:
            cookies = SimpleCookie()
            try:
                cookies.load(environ.get("HTTP_COOKIE", ""))
            except CookieError:
                cookies.clear()
            caddy_version = None
            if path == "/api/admin/technical-docs":
                version = environ.get("HTTP_X_KOSTBAR_CADDY_VERSION", "")
                if re.fullmatch(r"v[0-9][0-9A-Za-z.+-]{1,40}", version) and self.proxy_peer(environ):
                    caddy_version = version
            payload, cookie = app.route(terminal, method, path, query, body,
                                        {key: item.value for key, item in cookies.items()}, caddy_version)
        if isinstance(payload, Download):
            return payload.content, payload.mime, cookie, payload.name
        if path == "/api/admin/terminal-preview/page":
            return (STATIC / "index.html").read_bytes(), "text/html", cookie, None
        return self.json_body(payload), "application/json", cookie, None

    @staticmethod
    def json_body(payload):
        return json.dumps(payload, ensure_ascii=False, default=json_value).encode()

    def __call__(self, environ, start_response):
        status, cookie, filename = 200, None, None
        try:
            content, mime, cookie, filename = self.dispatch(environ)
        except Problem as exc:
            status, content, mime = exc.status, self.json_body({"error": str(exc)}), "application/json"
        except ValueError:
            status, content, mime = 400, self.json_body({"error": "Ungültige Anfrage."}), "application/json"
        except Exception as exc:
            logging.getLogger(__name__).error("Interner Fehler: %s", type(exc).__name__)
            status, content, mime = 500, self.json_body({"error": "Interner Fehler. Prüfe das Dienstprotokoll."}), "application/json"
        headers = list(SECURITY.items())
        if mime in ("text/html", "text/css", "text/javascript", "application/javascript", "application/json"):
            mime += "; charset=utf-8"
        headers.extend((("Content-Type", mime), ("Content-Length", str(len(content)))))
        if filename:
            headers.append(("Content-Disposition", f'attachment; filename="{filename}"'))
        if cookie:
            headers.append(("Set-Cookie", cookie))
        if status == 405:
            path = environ.get("PATH_INFO", "")
            allowed = METHODS.get(path)
            headers.append(("Allow", ", ".join(sorted(allowed)) if allowed else "GET, POST"))
        start_response(f"{status} {HTTPStatus(status).phrase}", headers)
        return [content]
