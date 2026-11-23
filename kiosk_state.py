"""Phase transitions for the kiosk session owned by one terminal."""
from enum import StrEnum


class Stage(StrEnum):
    IDLE = "idle"
    MANUAL = "manual"
    REGISTER = "register"
    CONSENT = "consent"
    PIN_SETUP = "pin-setup"
    SHOP = "shop"
    RECEIPT = "receipt"


ACTIVITY_STAGES = frozenset((Stage.MANUAL, Stage.REGISTER, Stage.CONSENT, Stage.PIN_SETUP, Stage.SHOP))
STAGE_ACTIONS = {
    "/api/kiosk/register": Stage.REGISTER,
    "/api/kiosk/accept-terms": Stage.CONSENT,
    "/api/kiosk/pin-setup": Stage.PIN_SETUP,
}


def reset(session, notice=None):
    session.update(stage=Stage.IDLE, until=0, card=None, card_type=None, user=None, receipt=None,
                   notice=notice, visit=None, committed=None, receipt_cart=None, manual_pin_hash=None)


def account_stage(account):
    if not account["accepted"]:
        return Stage.CONSENT
    if not account["pin_hash"]:
        return Stage.PIN_SETUP
    return Stage.SHOP
