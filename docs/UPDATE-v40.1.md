# Update auf KoSTbar v40.1

Der Release-Kandidat `40.1.0-rc.1` verwendet bei einer bestehenden Installation ab v39 dieselbe Datenbank, NAS-Konfiguration und Gerätezuordnung. Die NAS-Anwendung und die grafische Sitzung auf den Terminals können einzeln aktualisiert werden.

## 1. NAS-Anwendung aktualisieren

1. Die [bestehende Instanz sichern](BETRIEB.md#sicherung-und-wiederherstellung) und die laufende Image-Referenz mit `sudo docker inspect --format '{{.Config.Image}}' kostbar-app-1` notieren. Bei einem eigenen Projektnamen den entsprechenden Container verwenden.
2. Das [neue App-Image bauen und bereitstellen](../README.md#app-image-bereitstellen).
3. Im **bestehenden** QNAP- oder Synology-Compose-Ordner in `.env` den Wert `KOSTBAR_APP_IMAGE=kostbar-app:40.1.0-rc.1` setzen. Falls dort ein früherer manueller Mount für `/app/static/style.css` eingerichtet ist, die betreffende Zeile unter `app → volumes` entfernen, damit das Stylesheet des Images verwendet wird.
4. Im selben Ordner die App neu erstellen. Bei einem eigenen Compose-Projektnamen `kostbar` in den Befehlen ersetzen.

   ```bash
   sudo docker image inspect kostbar-app:40.1.0-rc.1 --format '{{.Id}}' &&
   sudo env KOSTBAR_APP_IMAGE=kostbar-app:40.1.0-rc.1 docker compose -p kostbar config --quiet &&
   sudo env KOSTBAR_APP_IMAGE=kostbar-app:40.1.0-rc.1 docker compose -p kostbar \
     up -d --no-deps --force-recreate --pull never app &&
   sudo docker compose -p kostbar ps app
   ```

5. Auf `healthy` warten und die [Erstabnahme](BETRIEB.md#erstabnahme) durchführen. In der Verwaltung auch die Benutzerliste, den Storno-Filter, die Zahlungsvorgänge und die Terminal-Vorschau prüfen.

Für den Rückweg die zuvor notierte Image-Referenz in `.env` wiederherstellen und sie in Schritt 4 einsetzen. Datenbank, Proxy und Volumes bleiben beim Austausch des App-Containers bestehen.

## 2. Bestehenden Raspberry Pi aktualisieren

1. Mit dem separaten Wartungskonto per SSH anmelden. Den aktuellen Ordner `pi/` auf den Pi übertragen. Das vorhandene private Geräteprofil des Verkaufspunkts bereithalten. Bei QNAP wird auch die bisherige NAS-CA benötigt.
2. In `~/kostbar-setup` mit `sudo bash pi/install.sh terminal-a.json caddy-root.crt` (QNAP oder eigene CA) beziehungsweise `sudo bash pi/install.sh terminal-a.json` (Synology mit öffentlichem Zertifikat) aktualisieren. Dateinamen bei Bedarf an den jeweiligen Verkaufspunkt anpassen. Die vorhandene Kopplung, das Chromium-Profil und die Skalierung bleiben erhalten. Für eine andere Skalierung `KIOSK_SCALE` wie in der [Terminal-Anleitung](TERMINALS.md#3-dateien-übertragen-und-installieren) übergeben.
3. Per SSH `sudo lightdm --show-config` prüfen. Für den Kiosk-Autologin muss `kostbar-kiosk` wirksam sein. Den Pi neu starten und die [Abnahme am Touchdisplay](TERMINALS.md#6-am-echten-display-abnehmen) durchführen.

### Rückweg für die grafische Sitzung

Über das Wartungskonto per SSH auf den Pi gehen. Die Sicherung `lightdm.conf.pre-kostbar-kiosk-session` stammt von unmittelbar vor der ersten Einrichtung der neuen Sitzung. Falls der Pi schon einen KoSTbar-Kiosk hatte, aktiviert diese Sicherung dessen frühere Sitzung und die dazugehörige Autostart-Datei. Bei einer Neuinstallation stellt sie den vorherigen LightDM-Stand wieder her.

```bash
sudo cp -p /etc/lightdm/lightdm.conf.pre-kostbar-kiosk-session /etc/lightdm/lightdm.conf
sudo rm -f /etc/polkit-1/rules.d/10-kostbar-kiosk.rules
if sudo test -f /etc/kaffeekasse-kiosk/chromium-policy.pre-kostbar-kiosk-session.json; then
  sudo install -m 0644 /etc/kaffeekasse-kiosk/chromium-policy.pre-kostbar-kiosk-session.json \
    /etc/chromium/policies/managed/90-kostbar-kiosk.json
else
  sudo rm -f /etc/chromium/policies/managed/90-kostbar-kiosk.json
fi
sudo reboot
```
