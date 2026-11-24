#!/bin/sh
set -eu

[ "$(id -un)" = kiosk ] && [ "$(id -u)" -ne 0 ] || exit 1

export XCURSOR_THEME=KoSTbar-Transparent
export LABWC_UPDATE_ACTIVATION_ENV=0
exec labwc --config-dir /etc/kaffeekasse-kiosk/labwc
