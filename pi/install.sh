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
for command in chromium lightdm labwc curl flock wlr-randr sudo; do
  if ! command -v "$command" >/dev/null; then
    echo "Raspberry Pi OS mit Desktop, Wayland und labwc ist erforderlich. Fehlt: $command" >&2
    exit 1
  fi
done
labwc_help=$(labwc --help 2>&1 || true)
if [[ "$labwc_help" != *--config-dir* ]] || [ ! -f /etc/lightdm/lightdm.conf ] ||
   [ ! -d /usr/share/wayland-sessions ]; then
  echo "LightDM mit Wayland und labwc mit --config-dir sind erforderlich." >&2
  exit 1
fi

work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
/usr/bin/python3 -B kiosk_boot.py policy "$device" > "$work/chromium.json"

if ! getent passwd kiosk >/dev/null; then
  useradd --create-home --user-group --shell /bin/bash kiosk
fi
if [ "$(id -u kiosk)" -eq 0 ] || [ "$(id -gn kiosk)" != kiosk ] ||
   [ "$(LC_ALL=C passwd -S kiosk | cut -d' ' -f2)" != L ]; then
  echo "kiosk benötigt eine eigene Primärgruppe und ein gesperrtes Passwort." >&2
  exit 1
fi
read -r -a kiosk_groups <<< "$(id -nG kiosk)"
for group in "${kiosk_groups[@]}"; do
  if [ "$group" != kiosk ] && [ "$group" != autologin ] && [ "$group" != users ]; then
    echo "Unerwartete Gruppe für kiosk: $group. Erlaubt sind kiosk und autologin." >&2
    exit 1
  fi
done
if LC_ALL=C sudo -n -l -U kiosk >/dev/null 2>&1; then
  echo "Für kiosk sind sudo-Rechte vergeben. Entferne sie vor der Installation." >&2
  exit 1
fi
kiosk_home=$(getent passwd kiosk | cut -d: -f6)
if [[ " ${kiosk_groups[*]} " == *" users "* ]]; then
  # Older Debian-based installs could add kiosk to the generic users group.
  gpasswd --delete kiosk users
fi
if getent group autologin >/dev/null; then
  usermod -aG autologin kiosk
fi

session_config=/etc/kaffeekasse-kiosk/labwc
policy=/etc/chromium/policies/managed/90-kostbar-kiosk.json
policy_backup=/etc/kaffeekasse-kiosk/chromium-policy.pre-kostbar-kiosk-session.json
install -d -m 0755 -o root -g root /opt/kaffeekasse-terminal
install -m 0644 -o root -g root kiosk_boot.py kiosk-rc.xml /opt/kaffeekasse-terminal/
boot=/opt/kaffeekasse-terminal/kiosk_boot.py
scale=${KIOSK_SCALE:-}
if [ -z "$scale" ]; then
  scale=$(/usr/bin/python3 -B "$boot" saved-scale "$session_config/autostart")
fi
if [ -z "$scale" ]; then
  scale=$(runuser -u kiosk -- /usr/bin/python3 -B "$boot" saved-scale "$kiosk_home/.config/labwc/autostart")
fi
/usr/bin/python3 -B "$boot" autostart "$scale" > "$work/autostart"
runuser -u kiosk -- /usr/bin/python3 -B "$boot" rc "$kiosk_home" > "$work/rc.xml"
runuser -u kiosk -- /usr/bin/python3 -B "$boot" cursor "$kiosk_home"
printf '%s\n' '<openbox_menu/>' > "$work/menu.xml"

if ! getent passwd kaffeekasse >/dev/null; then
  useradd --system --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin kaffeekasse
fi
install -d -m 0750 -o root -g kaffeekasse /etc/kaffeekasse-terminal
install -d -m 0750 -o root -g kiosk /etc/kaffeekasse-kiosk "$session_config"
install -m 0640 -o root -g kaffeekasse "$device" /etc/kaffeekasse-terminal/device.json
if [ -n "$ca_path" ]; then
  install -m 0644 "$cert" "$ca_path"
  install -m 0644 "$cert" /etc/kaffeekasse-kiosk/nas-root.crt
fi
install -m 0644 -o root -g root reader.py card_types.py device.py versions.py /opt/kaffeekasse-terminal/
install -m 0755 -o root -g root start-kiosk.sh kiosk-session.sh /opt/kaffeekasse-terminal/
install -m 0644 -o root -g root kaffeekasse-terminal-reader.service /etc/systemd/system/
install -D -m 0644 -o root -g root 49-kaffeekasse-pcsc.rules /etc/polkit-1/rules.d/49-kaffeekasse-pcsc.rules
install -m 0644 -o root -g root 10-kostbar-kiosk.rules /etc/polkit-1/rules.d/
origin=$(cd /opt/kaffeekasse-terminal && runuser -u kaffeekasse -- /usr/bin/python3 -B -c 'from device import Device; print(Device().settings["origin"])')
instance_file=/etc/kaffeekasse-terminal/reader-instance
if [ ! -e "$instance_file" ]; then
  /usr/bin/python3 -c 'import secrets; print(secrets.token_hex(32))' |
    install -m 0640 -o root -g kaffeekasse /dev/stdin "$instance_file"
fi
if runuser -u kiosk -- test -r /etc/kaffeekasse-terminal/device.json ||
   runuser -u kiosk -- test -r "$instance_file"; then
  echo "kiosk kann die private Leserkonfiguration lesen. Berechtigungen prüfen." >&2
  exit 1
fi
{ printf '%s\n' "$origin"; cat "$instance_file"; } |
  install -m 0640 -o root -g kiosk /dev/stdin /etc/kaffeekasse-kiosk/browser.conf
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
if [ -f "$policy" ] && [ ! -e "$policy_backup" ] && [ ! -f "$session_config/autostart" ]; then
  install -m 0600 -o root -g root "$policy" "$policy_backup"
fi
install -D -m 0644 -o root -g root "$work/chromium.json" "$policy"
install -m 0640 -o root -g kiosk "$work/autostart" "$work/rc.xml" "$work/menu.xml" "$session_config/"
for file in environment shutdown; do
  install -m 0640 -o root -g kiosk /dev/null "$session_config/$file"
done
install -m 0644 -o root -g root kostbar-kiosk.desktop /usr/share/wayland-sessions/
/usr/bin/python3 -B "$boot" lightdm kiosk kostbar-kiosk
systemctl enable lightdm.service
systemctl set-default graphical.target
systemctl daemon-reload
systemctl enable --now pcscd.socket kaffeekasse-terminal-reader.service
systemctl restart kaffeekasse-terminal-reader.service
echo "KoSTbar-Kiosksitzung eingerichtet. Starte den Pi neu und prüfe die Kopplung am Display."
