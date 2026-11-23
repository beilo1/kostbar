"""Classify only the PC/SC storage-card descriptors emitted by the reader."""
from functools import reduce
from operator import xor

CARD_TYPES = {
    "classic_1k": "MIFARE Classic 1K-kompatibel",
    "classic_4k": "MIFARE Classic 4K-kompatibel",
    "type2": "NFC Forum Type 2 / Ultralight-kompatibel",
    "ultralight_c": "MIFARE Ultralight C (Lesermeldung)",
    "ultralight_ev1": "MIFARE Ultralight EV1 (Lesermeldung)",
    "mifare_mini": "MIFARE Mini (Lesermeldung)",
    "mifare_plus": "MIFARE Plus (Lesermeldung)",
    "topaz": "Topaz / Jewel",
    "iso14443a": "ISO 14443-A (Teil 3)",
    "iso15693": "ISO 15693",
    "felica": "FeliCa",
}

STORAGE_ATR = bytes.fromhex("3B 8F 80 01 80 4F 0C A0 00 00 03 06")
TYPE_A_CARDS = {
    0x0001: "classic_1k", 0x0002: "classic_4k", 0x0003: "type2", 0x0026: "mifare_mini",
    0x0036: "mifare_plus", 0x0037: "mifare_plus", 0x0038: "mifare_plus", 0x0039: "mifare_plus",
    0x003A: "ultralight_c", 0x003D: "ultralight_ev1",
}


def classify(atr):
    # ACS documents this 20-byte pseudo-ATR, including its PC/SC RID and checksum.
    value = bytes(atr or ())
    if (len(value) != 20 or not value.startswith(STORAGE_ATR)
            or value[15:19] != bytes(4) or reduce(xor, value[1:])):
        return None
    standard, card = value[12], int.from_bytes(value[13:15], "big")
    if card == 0x0030:
        return "topaz"
    if standard == 0x03:
        return TYPE_A_CARDS.get(card, "iso14443a")
    return {0x0B: "iso15693", 0x11: "felica"}.get(standard)
