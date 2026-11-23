"""Reject builds with missing or stale paths in the admin API reference."""
import ast
from pathlib import Path

from api_reference import METHODS, READER_PATH

source = "\n".join(Path(__file__).with_name(name).read_text(encoding="utf-8") for name in ("server.py", "web.py"))
paths = {node.value for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Constant)
         and isinstance(node.value, str) and node.value.startswith(("/api/", "/healthz", "/internal/reader"))
         and not node.value.endswith(("/", "-"))}
paths.difference_update(("/internal/reader", "/api/admin", "/api/kiosk"))
paths.add(READER_PATH)
missing = paths - METHODS.keys()
stale = METHODS.keys() - paths
if missing or stale:
    raise SystemExit(f"API-Referenz aktualisieren. Fehlend: {sorted(missing)}. Veraltet: {sorted(stale)}")
