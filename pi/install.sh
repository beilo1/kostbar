#!/bin/bash
set -euo pipefail
if [ "$(id -u)" -ne 0 ] || [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
  echo "Aufruf: sudo bash pi/install.sh terminal-device.json [nas-root.crt]" >&2
  exit 1
fi
device=$(realpath -- "$1")
cert=
if [ "$#" -eq 2 ]; then
  cert=$(realpath -- "$2")
fi
cd -- "$(dirname -- "$0")"
test -f "$device"
ca_path=$(/usr/bin/python3 -c 'import json, sys; print(json.load(open(sys.argv[1])).get("ca_file") or "")' "$device")
if [ -n "$ca_path" ]; then
  if [ "$ca_path" != /etc/kaffeekasse-terminal/nas-root.crt ] || [ "$#" -ne 2 ]; then
    echo "Dieses Geräteprofil benötigt nas-root.crt als zweites Argument." >&2
    exit 1
  fi
  test -f "$cert"
  if ! command -v certutil >/dev/null; then
    echo "Installiere libnss3-tools für die Zertifikatsprüfung in Chromium." >&2
    exit 1
  fi
elif [ "$#" -eq 2 ]; then
  echo "Dieses Geräteprofil nutzt den System-Vertrauensspeicher. Nur das Geräteprofil übergeben." >&2
  exit 1
fi
if ! /usr/bin/python3 -c 'import smartcard.scard'; then
  echo "Installiere zuerst python3-pyscard, pcscd und libccid." >&2
  exit 1
fi
for command in chromium lightdm labwc curl flock wlr-randr; do
  if ! command -v "$command" >/dev/null; then
    echo "Raspberry Pi OS mit Desktop, Wayland und labwc ist erforderlich. Fehlt: $command" >&2
    exit 1
  fi
done
session=
for candidate in rpd-labwc LXDE-pi-labwc; do
  if [ -f "/usr/share/wayland-sessions/$candidate.desktop" ]; then
    session="$candidate"
    break
  fi
done
if [ -z "$session" ] || [ ! -f /etc/lightdm/lightdm.conf ]; then
  echo "Keine unterstützte Raspberry-Pi-Desktop-Sitzung gefunden." >&2
  exit 1
fi
if ! getent passwd kiosk >/dev/null; then
  adduser --disabled-password --gecos "" kiosk
fi
if id -nG kiosk | grep -Eq '(^| )(sudo|wheel|docker)( |$)'; then
  echo "Das Desktopkonto kiosk hat administrative Rechte. Verwende ein unprivilegiertes Kioskkonto." >&2
  exit 1
fi
kiosk_home=$(getent passwd kiosk | cut -d: -f6)
if getent group autologin >/dev/null; then
  usermod -aG autologin kiosk
fi
if ! getent passwd kaffeekasse >/dev/null; then
  useradd --system --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin kaffeekasse
fi
install -d -m 0750 -o root -g kaffeekasse /etc/kaffeekasse-terminal
install -d -m 0750 -o root -g "$(id -gn kiosk)" /etc/kaffeekasse-kiosk
install -d -m 0755 /opt/kaffeekasse-terminal /etc/polkit-1/rules.d
install -m 0640 -o root -g kaffeekasse "$device" /etc/kaffeekasse-terminal/device.json
if [ -n "$ca_path" ]; then
  install -m 0644 "$cert" "$ca_path"
  install -m 0644 "$cert" /etc/kaffeekasse-kiosk/nas-root.crt
fi
install -m 0644 reader.py card_types.py device.py kiosk_boot.py versions.py /opt/kaffeekasse-terminal/
install -m 0755 start-kiosk.sh /opt/kaffeekasse-terminal/
install -m 0644 kaffeekasse-terminal-reader.service /etc/systemd/system/
install -m 0644 49-kaffeekasse-pcsc.rules /etc/polkit-1/rules.d/
install -D -m 0644 chromium-policy.json /etc/chromium/policies/managed/90-kostbar-kiosk.json
origin=$(cd /opt/kaffeekasse-terminal && runuser -u kaffeekasse -- /usr/bin/python3 -B -c 'from device import Device; print(Device().settings["origin"])')
instance_file=/etc/kaffeekasse-terminal/reader-instance
if [ ! -e "$instance_file" ]; then
  /usr/bin/python3 -c 'import secrets; print(secrets.token_hex(32))' |
    install -m 0640 -o root -g kaffeekasse /dev/stdin "$instance_file"
fi
{ printf '%s\n' "$origin"; cat "$instance_file"; } |
  install -m 0640 -o root -g "$(id -gn kiosk)" /dev/stdin /etc/kaffeekasse-kiosk/browser.conf
if [ -n "$ca_path" ]; then
  for nss in "$kiosk_home/.pki/nssdb" "$kiosk_home/.local/share/pki/nssdb"; do
    runuser -u kiosk -- mkdir -p "$nss"
    if [ ! -f "$nss/cert9.db" ]; then
      runuser -u kiosk -- certutil -N -d "sql:$nss" --empty-password
    fi
    runuser -u kiosk -- certutil -D -d "sql:$nss" -n "KoSTbar NAS CA" 2>/dev/null || true
    runuser -u kiosk -- certutil -A -d "sql:$nss" -n "KoSTbar NAS CA" -t "C,," -i /etc/kaffeekasse-kiosk/nas-root.crt
  done
else
  rm -f /etc/kaffeekasse-kiosk/nas-root.crt
  if command -v certutil >/dev/null; then
    for nss in "$kiosk_home/.pki/nssdb" "$kiosk_home/.local/share/pki/nssdb"; do
      if [ -f "$nss/cert9.db" ]; then
        runuser -u kiosk -- certutil -D -d "sql:$nss" -n "KoSTbar NAS CA" 2>/dev/null || true
      fi
    done
  fi
fi
boot=/opt/kaffeekasse-terminal/kiosk_boot.py
runuser -u kiosk -- /usr/bin/python3 -B "$boot" autostart "$kiosk_home" "${KIOSK_SCALE:-}"
/usr/bin/python3 -B "$boot" lightdm kiosk "$session"
systemctl enable lightdm.service
systemctl set-default graphical.target
systemctl daemon-reload
systemctl enable --now pcscd.socket kaffeekasse-terminal-reader.service
systemctl restart kaffeekasse-terminal-reader.service
echo "Kiosk-Autostart eingerichtet. Starte den Pi neu und bestätige den Kopplungscode in der Verwaltung."
