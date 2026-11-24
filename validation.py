"""Validation shared by HTTP handlers and administration operations."""

import re

from configure import required_text
from store import Problem


def string(value, limit, label):
    try:
        return required_text(value, limit, label)
    except ValueError as exc:
        raise Problem(400, str(exc)) from exc


def number(value, lo, hi, label):
    if type(value) is not int or not lo <= value <= hi:
        raise Problem(400, f"{label} liegt außerhalb des erlaubten Bereichs.")
    return value


def flag(value):
    if type(value) is not bool:
        raise Problem(400, "Ungültiger Status.")
    return int(value)


def request_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{32}", value):
        raise Problem(400, "Ungültige Vorgangskennung.")
    return value


def terminal_pin(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}", value):
        raise Problem(400, "Gib eine PIN mit genau vier Ziffern ein.")
    return value


def admin_name(value):
    if not re.fullmatch(r"[a-z][a-z0-9._-]{2,31}", value):
        raise ValueError("Adminname: 3–32 Zeichen, Kleinbuchstaben, Ziffern, Punkt, Minus, Unterstrich.")
    return value
