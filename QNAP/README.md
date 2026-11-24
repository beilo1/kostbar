# QNAP TVS-872XT mit QTS – Neuinstallation

Container Station und Docker Compose müssen vorhanden sein. Per SSH mit deinem Wartungskonto arbeiten. **Den gesamten Projektordner** auf das NAS kopieren, beispielsweise nach `/share/Kaffeekasse/kostbar`; darin müssen unter anderem `configure.py`, `compose.common.yml`, `pi/` und `QNAP/` liegen.

## 0. Altinstallation entfernen

Für eine bestehende v35-, v36- oder v37-Instanz gilt die [Upgrade-Anleitung](../README.md#upgrade-einer-bestehenden-installation). Falls du eine Altinstanz für eine Neuinstallation entfernen möchtest, folge der [Löschanleitung](../docs/ALTINSTALLATION-ENTFERNEN.md).

In diesem Setup liefert Caddy HTTPS direkt aus. Mit dem alten Caddy-Datenvolume verschwindet auch die lokale CA dieser Instanz. Verwende für die Neuinstallation die neu erzeugte öffentliche Root-CA aus Schritt 4 und ersetze die alte KoSTbar-CA auf Admin-PC und Terminals. Bei gleichem Hostnamen kannst du den DNS-Eintrag für die neue Instanz verwenden. Prüfe vor dem Start, dass der vorgesehene HTTPS-Port auf der NAS-IP frei ist.

## 1. Netzwerk vorbereiten

Dem NAS die feste LAN-IP `192.168.3.110` zuweisen und den internen DNS-Eintrag `kostbar.internal.lan` auf diese IP setzen. Die eingerichteten Pis und der Admin-PC müssen den Namen auflösen und TCP **18443** erreichen. Die QNAP-Verwaltung kann ihren bisherigen Port behalten. `18443` muss auf dieser NAS-IP frei sein. DNS und HTTPS-Zugriff auch aus dem produktiven WPA-Enterprise-WLAN und dessen zugewiesenem VLAN prüfen.

## 2. Konfiguration einmalig erzeugen

Auf dem NAS wird kein lokal installiertes Python benötigt. Im Hauptordner ausführen:

```bash
cd /share/Kaffeekasse/kostbar
sudo docker compose version
sudo docker run --rm \
  --user "$(id -u):$(id -g)" \
  --volume "$(pwd -P):/project" \
  --workdir /project \
  python:3.13-slim-bookworm \
  python configure.py --deployment qnap \
    --nas-ip '192.168.3.110' \
    --contact-name 'Kassen-Team' \
    --contact-reach 'Interne E-Mail oder Durchwahl'
```

Kontaktdaten durch eure echten Angaben ersetzen. Optional `--origin 'https://kasse.internal.lan:18443'`, `--label-a`, `--label-b` oder `--paypal-url 'https://paypal.me/DeinName'` ergänzen. Standard ist `https://kostbar.internal.lan:18443`. IP, öffentlicher Port und DNS müssen zusammenpassen.

Erzeugt werden **QNAP/.env**, **QNAP/config/server.json** und ein privates Geräteprofil für A. Mit `--label-b` wird auch B eingerichtet. Bestehende Zieldateien werden nicht überschrieben. Keine Beispieltokens oder Kennwörter sind im Paket enthalten. Das Skript einmal ausführen. Weitere Verkaufspunkte lassen sich in der Verwaltung hinzufügen.

## 3. Dienste starten

Zuerst das [gemeinsame App-Image bereitstellen](../README.md#app-image-bereitstellen). Danach im QNAP-Unterordner arbeiten.

```bash
cd /share/Kaffeekasse/kostbar/QNAP
sudo chmod 600 .env config/server.json
sudo chown 10001:10001 config/server.json
sudo chmod 755 ../nas/init-db.sh
sudo docker compose -p kostbar config --quiet
sudo docker compose -p kostbar up -d
sudo docker compose -p kostbar ps
```

Falls nur `docker-compose` verfügbar ist, dieses Kommando durchgängig anstelle von `docker compose` verwenden und die Konfigurationsprüfung ausführen. Kein Docker-Swarm-Deployment verwenden. Die App läuft als UID/GID `10001:10001` und muss die eingebundene Datei lesen können. PostgreSQL startet mit einem eigenen persistenten Volume. Die App wendet die versionierten Schema-Migrationen automatisch an. Es wird genau eine App-Instanz betrieben.

Alle drei Dienste müssen gesund bzw. gestartet sein. Bei Fehlern:

```bash
sudo docker compose -p kostbar logs --tail=80 db app proxy
sudo docker compose -p kostbar exec app python server.py schema-status
```

`schema-status` muss die Versionen **1 bis 6** mit `v35_baseline` als erster Version anzeigen. Bei `address already in use` den Portbeleg prüfen oder einen freien Port über `--origin` bei der erstmaligen Konfiguration wählen. Bei `password authentication failed` zusammen mit `Skipping initialization` wurden alte DB-Daten mit neuen Zugangsdaten vermischt. Prüfe dann, zu welcher Installation das Volume gehört. Bei einer bestätigten Altinstallation folge Schritt 0. Prüfe anschließend, dass das Projekt `kostbar` mit einem leeren Datenvolume startet.

## 4. Super-Admin und HTTPS-Vertrauen

```bash
sudo docker compose -p kostbar exec app python server.py set-super-admin kassenadmin
umask 077
sudo docker compose -p kostbar exec -T proxy \
  cat /data/caddy/pki/authorities/local/root.crt > caddy-root.crt
test -s caddy-root.crt
openssl x509 -in caddy-root.crt -noout -subject -fingerprint -sha256
```

Das Admin-Kennwort wird verdeckt abgefragt. Die Caddy-Root-CA kann beim ersten Proxy-Start kurz auf sich warten lassen; bei noch fehlender Datei den Proxy-Status prüfen und den Export wiederholen. Übertrage ausschließlich die **öffentliche** `caddy-root.crt` über deinen vertrauten Wartungsweg. Den SHA-256-Fingerabdruck vergleichen. Die CA im vom Admin-Browser verwendeten Vertrauensspeicher installieren. Der private CA-Schlüssel verbleibt im Caddy-Volume.

Die Caddy-CA gehört zu dieser neuen Installation. Bei neuen Volumes muss sie auf den Pis und am Admin-PC neu installiert werden. Danach öffnen:

`https://kostbar.internal.lan:18443/admin`

Die Oberfläche muss ohne Zertifikatswarnung öffnen. Zum Test auf dem NAS mit der gerade exportierten Datei:

```bash
curl -fsS --max-time 10 --cacert ./caddy-root.crt \
  https://kostbar.internal.lan:18443/healthz
```

Erwartet: `{"ok": true}`. Falls das NAS seine eigene gebundene LAN-IP nicht erreicht, denselben Test vom Admin-PC mit der exportierten CA ausführen und die NAS-Netzwerkregeln prüfen.

## 5. Terminals einrichten

Die Paketinstallation im PSK-WLAN und die Umstellung auf WPA2-Enterprise mit PEAP/MSCHAPv2 nach der [Terminal-Anleitung](../docs/TERMINALS.md) durchführen. Den gemeinsamen Ordner `pi/` aus dem Hauptverzeichnis, die öffentliche `caddy-root.crt` und das passende Pi-Profil übertragen. Das bei der Installation erzeugte Profil für A liegt in `QNAP/config/terminal-a.json`. In **Verkauf → Verkaufspunkte** kannst du weitere Standorte anlegen und das jeweilige Profil herunterladen.

Der bekannte Zertifikatstest auf dem fertig eingerichteten Pi lautet:

```bash
getent hosts kostbar.internal.lan
sudo -u kaffeekasse -- curl -fsS --max-time 10 \
  --cacert /etc/kaffeekasse-terminal/nas-root.crt \
  https://kostbar.internal.lan:18443/healthz
```

Das Dienstkonto ist erforderlich, weil `/etc/kaffeekasse-terminal` absichtlich `root:kaffeekasse` und Modus `0750` hat. Ein Aufruf als normaler Wartungsbenutzer kann deshalb `curl: (77)` liefern. Die Verzeichnisrechte dafür nicht öffnen und die Zertifikatsprüfung nicht abschalten.

Danach [Betrieb und Abnahme](../docs/BETRIEB.md) durchführen. Das Docker-Datenvolume und Sicherungen müssen am tatsächlichen NAS-Speicherort in das gewünschte Verschlüsselungs- und Backupkonzept einbezogen sein.
