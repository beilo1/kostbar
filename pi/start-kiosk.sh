#!/bin/sh
set -eu
# Run inside the graphical user's labwc session.
exec 9>"${XDG_RUNTIME_DIR:-/tmp}/kaffeekasse-kiosk-$(id -u).lock"
flock -n 9 || exit 0
# Apply the display orientation inside labwc on each graphical login.
wlr-randr --output DSI-2 --transform 270 || true

umask 077
profile="$HOME/.local/share/kostbar-chromium"
mkdir -p "$profile"
cache=$(mktemp -d /dev/shm/kostbar-chromium.XXXXXX)
trap 'rm -rf -- "$cache"' EXIT
trap 'exit 0' HUP INT TERM
origin=$(sed -n '1p' /etc/kaffeekasse-kiosk/browser.conf)
instance=$(sed -n '2p' /etc/kaffeekasse-kiosk/browser.conf)
ca=/etc/kaffeekasse-kiosk/nas-root.crt
set --
if [ -f "$ca" ]; then
  set -- --cacert "$ca"
fi
while :; do
  if curl "$@" --fail --silent --max-time 3 "$origin/healthz" >/dev/null; then
    chromium --kiosk --password-store=basic --no-first-run --noerrdialogs --disable-session-crashed-bubble \
      --disable-background-networking --disable-sync --disable-component-update \
      --ozone-platform=wayland --force-device-scale-factor="${KIOSK_SCALE:-1}" \
      --user-data-dir="$profile" --disk-cache-dir="$cache" "$origin/#setup=$instance" || :
  fi
  sleep 2
done
