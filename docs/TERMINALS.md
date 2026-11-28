# Raspberry-Pi-Terminals einrichten

Die gemeinsamen Installationsdateien liegen im Hauptordner unter `pi/`. Der Konfigurationsgenerator legt das erste Geräteprofil im NAS-Unterordner unter `config/` ab. Weitere Profile lädt der Super-Admin unter **Verkauf → Verkaufspunkte** herunter. Die Verwaltung der Kopplungen liegt ebenfalls beim Super-Admin. Verwende pro Pi das Profil seines Verkaufspunkts und seiner Installation. [Hardware und Anschluss](HARDWARE.md)

## 1. Raspberry Pi OS vorbereiten

Raspberry Pi OS 64-Bit mit Desktop, labwc/Wayland und LightDM verwenden. Im Raspberry Pi Imager das Wartungskonto, SSH, das WLAN-Land und das vorläufige WPA2-/WPA3-Personal-WLAN (PSK) einrichten. Den SSH-Zugang mit dem separaten Wartungskonto prüfen. Für den Dauerkiosk Screen Blanking deaktivieren. Über das Setup-WLAN alle benötigten Pakete installieren, einschließlich USBGuard für Schritt 5. Danach startet die Umstellung auf das produktive WLAN.

```bash
sudo apt update
sudo apt full-upgrade
sudo rpi-eeprom-update -a
sudo apt install chromium curl unzip pcscd libccid pcsc-tools python3-pyscard \
  libnss3-tools wlr-randr usbguard network-manager openssl nano
sudo reboot
```

Displaymontage und GPIO-Anschluss nur ohne Strom vornehmen. Die vorgesehene Displayausrichtung ist Querformat, Ausgang `DSI-2`, Drehung 270°. Der ACS ACR1252U wird ebenso wie ACR122U und ACR1552U vom mitgelieferten PC/SC-Zugriff berücksichtigt. Die tatsächlich verwendeten Karten an jedem eingerichteten Terminal testen.

Vor der Installation `labwc --help 2>&1 | grep -F -- --config-dir` ausführen. Die Option muss vorhanden sein. Das Wartungskonto braucht funktionierenden SSH- und sudo-Zugang, damit die Sitzung nach der Umstellung geprüft und bei Bedarf über SSH wiederhergestellt werden kann. Für ein bestehendes Terminal die [Schritte für Update und Rückweg](UPDATE-v40.1.md#3-einen-bestehenden-raspberry-pi-aktualisieren) verwenden. [labwc-Handbuch](https://labwc.github.io/labwc.1.html)

## 2. Produktives WLAN mit WPA2-Enterprise und RADIUS einrichten

Stelle die Terminals einzeln um und verwende Ethernet oder die lokale Konsole vor der USBGuard-Sperre. Beim Aktivieren des neuen Profils kann eine SSH-Sitzung über WLAN abbrechen. Ein bereits funktionierendes PEAP/MSCHAPv2-Profil kannst du beim Update weiterverwenden.

### RADIUS und Terminal-VLAN vorbereiten

| Einstellung | Vorgabe |
| --- | --- |
| Produktive SSID | In UniFi bzw. auf dem WLAN-Controller WPA2-Enterprise und das RADIUS-Profil auswählen. Die SSID dem separaten Terminal-VLAN zuordnen. Falls RADIUS die VLAN-ID liefert, muss die Zuordnung zum vorgesehenen VLAN passen. |
| RADIUS-Konto | Pro Terminal einen eigenen technischen Benutzernamen und ein eigenes Passwort hinterlegen. |
| RADIUS-CA und Servername | Die vertrauenswürdige RADIUS-CA und den erwarteten exakten Namen aus der Netzwerkadministration beziehen. Den DNS-Namen aus dem SAN einsetzen. Wenn das Zertifikat keinen DNS-SAN enthält, prüft NetworkManager den Common Name (CN). Beim getesteten integrierten UniFi-RADIUS lautet der CN `UbiOS RADIUS Server Certificate`. |
| Terminal-VLAN | DHCP, internes DNS, HTTPS zum NAS und den vorgesehenen SSH-Wartungsweg prüfen. |

Die RADIUS-CA dient der WLAN-Anmeldung in NetworkManager. Für KoSTbar-HTTPS verwendest du das NAS-Geräteprofil und je nach Deployment die NAS-CA aus Schritt 3.

```bash
systemctl is-active NetworkManager
nmcli device status
nmcli -f NAME,UUID,TYPE,DEVICE connection show --active
timedatectl status
```

Notiere die UUID des bisherigen WLAN-Profils und prüfe die Systemzeit. Übertrage die RADIUS-CA über einen vertrauenswürdigen Administrationsweg nach `~/kostbar-setup/`. Im Beispiel heißt sie `radius-ca.pem`. Vergleiche den SHA-256-Fingerabdruck mit dem von der Netzwerkadministration bestätigten Wert.

```bash
openssl x509 -in ~/kostbar-setup/radius-ca.pem -noout -sha256 -fingerprint
sudo install -d -o root -g root -m 0700 /etc/NetworkManager/kostbar
sudo install -o root -g root -m 0600 ~/kostbar-setup/radius-ca.pem \
  /etc/NetworkManager/kostbar/peap-radius-ca.pem
```

### PEAP/MSCHAPv2-Profil anlegen

Verwende beim Wechsel ein eigenes Profil, damit das bisherige WLAN als Rückweg verfügbar bleibt. Falls ein Profil namens `KoSTbar-UniFi` bereits existiert, wähle für das neue Profil einen anderen Dateinamen und verwende seine neue Profil-ID auch in den folgenden Befehlen. Das Beispiel geht von `wlan0` aus. Übernimm bei Bedarf den Schnittstellennamen aus `nmcli device status`.

```bash
profile=/etc/NetworkManager/system-connections/KoSTbar-UniFi.nmconnection
cat /proc/sys/kernel/random/uuid
sudo touch "$profile"
sudo chown root:root "$profile"
sudo chmod 0600 "$profile"
sudo nano --ignorercfiles "$profile"
```

Trage die erzeugte UUID, die SSID, den RADIUS-Benutzernamen und das Passwort ein. Setze `domain-match` auf den bestätigten exakten RADIUS-Servernamen. Das Beispiel verwendet den CN des bereits getesteten UniFi-Zertifikats. Setze `hidden=false` für eine sichtbare SSID.

```ini
[connection]
id=KoSTbar-UniFi
uuid=HIER_ERZEUGTE_UUID_EINTRAGEN
type=wifi
interface-name=wlan0
autoconnect=false

[wifi]
mode=infrastructure
ssid=PRODUKTIV-SSID
hidden=true

[wifi-security]
key-mgmt=wpa-eap
proto=rsn;

[802-1x]
eap=peap;
identity=TERMINAL-BENUTZERNAME
phase2-auth=mschapv2
ca-cert=/etc/NetworkManager/kostbar/peap-radius-ca.pem
domain-match=UbiOS RADIUS Server Certificate
password=HIER_RADIUS_PASSWORT_EINTRAGEN
password-flags=0

[ipv4]
method=auto

[ipv6]
method=auto
```

Für die automatische Anmeldung speichert NetworkManager das Passwort in der systemweiten, nur für root lesbaren Profildatei. Gib es direkt im Editor ein. Im Keyfile einen wörtlichen Backslash als `\` und führende Leerzeichen als `\s` schreiben. Die Profildatei enthält Zugangsdaten und gehört in eine geschützte Sicherung.

### Verbindung und automatischen Start prüfen

```bash
sudo nmcli connection load "$profile"
sudo nmcli --wait 45 connection up id KoSTbar-UniFi
nmcli -f NAME,UUID,TYPE,DEVICE connection show --active
nmcli -f GENERAL.CONNECTION,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS device show wlan0
getent hosts kostbar.internal.lan
```

Prüfe die IP-Adresse im vorgesehenen Terminal-VLAN und die erfolgreiche Anmeldung im RADIUS-Protokoll. Die Aktivierung ohne `--ask` bestätigt, dass das gespeicherte Passwort verwendet werden kann. Für Synology den NAS-Namen aus dem Geräteprofil verwenden. Bei gestecktem Ethernet die Route zum NAS prüfen, etwa mit `ip route get 192.168.3.110` für die QNAP-Beispiel-IP. Die Route für die WLAN-Abnahme muss über `wlan0` führen.

Wenn das neue Profil funktioniert, aktiviere dessen Autoconnect und deaktiviere ihn für das bisherige WLAN-Profil. Ersetze die Beispiel-UUID. Falls weitere WLAN-Profile beim Boot konkurrieren, prüfe auch deren Autoconnect-Einstellungen.

```bash
previous_uuid='HIER-BISHERIGE-PROFIL-UUID'
sudo nmcli connection modify id KoSTbar-UniFi connection.autoconnect yes
sudo nmcli connection modify uuid "$previous_uuid" connection.autoconnect no
sudo reboot
```

Prüfe nach dem Neustart das aktive Profil, die VLAN-IP, den RADIUS-Erfolg und den SSH-Zugang. Führe anschließend den HTTPS-Test aus Schritt 4 durch. Entferne oder sperre das alte RADIUS-Gerätekonto erst nach erfolgreicher Abnahme, sofern es abgelöst wurde. Bei der Ablösung eines EAP-TLS-Profils das frühere Gerätezertifikat nach dem vorgesehenen PKI-Verfahren außer Betrieb nehmen.

**Rückweg während der Einrichtung.** Über Ethernet oder die lokale Konsole `sudo nmcli connection modify id KoSTbar-UniFi connection.autoconnect no` ausführen. Danach das bisherige Profil mit `sudo nmcli connection modify uuid "$previous_uuid" connection.autoconnect yes` und `sudo nmcli connection up uuid "$previous_uuid"` wieder aktivieren. Nach einer neuen Anmeldung die Variable erneut setzen. Bei Fehlern `sudo journalctl -b -u NetworkManager -u wpa_supplicant --no-pager -n 80` und das RADIUS-Protokoll prüfen. Typische Prüfpunkte sind Uhrzeit, CA-Kette, Servername, PEAP/MSCHAPv2, Zugangsdaten und VLAN-Zuordnung.

[Raspberry Pi OS · Netzwerkverwaltung](https://www.raspberrypi.com/documentation/computers/configuration.html#networking) · [NetworkManager · Dateiformat](https://networkmanager.dev/docs/api/latest/nm-settings-keyfile.html) · [NetworkManager · 802.1X-Einstellungen](https://networkmanager.dev/docs/api/latest/settings-802-1x.html)

## 3. Dateien übertragen und installieren

Auf dem Pi einen privaten Ordner `~/kostbar-setup` anlegen. Den gesamten gemeinsamen Ordner `pi/` und das passende Geräteprofil per vertrautem SSH-Weg hinein kopieren. Den ersten Pi mit `terminal-a.json` einrichten. Weitere Verkaufspunkte unter **Verkauf → Verkaufspunkte** anlegen und dort ihr privates Pi-Profil herunterladen. Bei QNAP zusätzlich das öffentliche, per Fingerabdruck geprüfte `caddy-root.crt` übertragen. Bei Synology mit eigener CA die öffentliche CA-Datei nach [Synology-Anleitung](../Synology/README.md#4-super-admin-und-terminals) verwenden. Das zugehörige Profil muss `ca_file: "/etc/kaffeekasse-terminal/nas-root.crt"` enthalten.

Auf Pi A mit QNAP oder eigener CA:

```bash
cd ~/kostbar-setup
umask 077
sudo env KIOSK_SCALE=1.5 bash pi/install.sh terminal-a.json caddy-root.crt
sudo systemctl --no-pager status kaffeekasse-terminal-reader.service
```

Für Synology mit öffentlich vertrauenswürdigem Zertifikat (`ca_file: null`) ohne zweites Argument:

```bash
cd ~/kostbar-setup
sudo env KIOSK_SCALE=1.5 bash pi/install.sh terminal-a.json
sudo systemctl --no-pager status kaffeekasse-terminal-reader.service
```

Auf weiteren Pis jeweils `terminal-<kennung>.json` des zugeordneten Verkaufspunkts verwenden. Bei 1920 × 1200 Pixeln ergibt eine Skalierung von 1,5 etwa 1280 × 800 CSS-Pixel. Beim Transfer die Installationsdateien vor Zugriff durch andere Benutzer schützen. Private Zwischenkopien nach erfolgreicher Einrichtung entfernen und Geräteprofile geschützt sichern.

## 4. Verbindung mit dem Dienstkonto prüfen

QNAP-Standard oder eigene CA (Adresse bei Synology anpassen):

```bash
getent hosts kostbar.internal.lan
sudo -u kaffeekasse -- curl -fsS --max-time 10 \
  --cacert /etc/kaffeekasse-terminal/nas-root.crt \
  https://kostbar.internal.lan:18443/healthz
sudo journalctl -b -u kaffeekasse-terminal-reader --no-pager -n 80
```

Synology mit öffentlichem Zertifikat:

```bash
sudo -u kaffeekasse -- curl -fsS --max-time 10 https://kostbar.example.org/healthz
```

Erwartet ist `{"ok": true}`. Ohne `sudo -u kaffeekasse` kann der Zugriff auf die geschützte CA-Datei mit Fehler 77 scheitern: Das Verzeichnis `/etc/kaffeekasse-terminal` ist absichtlich nur für root und die Dienstgruppe zugänglich. Rechte beibehalten. Kein `curl -k` verwenden.

Bei Leserproblemen `lsusb`, `apt policy libccid` und `sudo pcsc_scan` prüfen. Für die maskierte UID-Probe den Leserdienst kurz anhalten:

```bash
sudo systemctl stop kaffeekasse-terminal-reader.service
sudo -u kaffeekasse /usr/bin/python3 -B /opt/kaffeekasse-terminal/reader.py --probe
# Strg+C beendet die Probe.
sudo systemctl start kaffeekasse-terminal-reader.service
```

Dieselbe Karte mehrfach vollständig entfernen und erneut anhalten. Die maskierte Kennung muss innerhalb desselben Testlaufs gleich bleiben. Bei mehreren passenden Lesern in `/etc/kaffeekasse-terminal/device.json` einen eindeutigen `reader_match` setzen und den Dienst neu starten.

## 5. USBGuard und Kiosk-Kopplung

### USB-Geräte mit USBGuard absichern

Auf jedem Terminal separat einrichten. Verwende dafür den vorgesehenen Pi mit Raspberry Pi OS auf microSD, DSI-Touchscreen und integriertem LAN oder WLAN. Prüfe den SSH-Zugang mit deinem Wartungskonto, bevor du die Sperre aktivierst. Ziehe USB-Tastaturen, Datenträger, Hubs und sonstige Geräte ab. Der ACS-Kartenleser bleibt direkt an dem USB-Port, den er im Betrieb nutzen soll. Prüfe den Leser im CCID-/PC/SC-Modus wie oben beschrieben.

```bash
sudo usbguard list-devices
```

Suche den ACS-Leser in der Ausgabe und übernimm den Wert hinter `via-port`. Im Beispiel ist es `1-2`. Im Verzeichnis oberhalb von `pi/` ausführen:

```bash
sudo python3 pi/install-usbguard.py 1-2
sudo usbguard list-devices --allowed
sudo reboot
```

Der Helfer erstellt eine Regel mit Geräte-ID, Deskriptor-Hash, USB-Port und den tatsächlich vorhandenen CCID-Schnittstellen. Die USB-Root-Hubs bleiben aktiv. Andere USB-Geräte werden blockiert, auch wenn sie sich als Tastatur, Massenspeicher, Netzwerkadapter oder Kombigerät melden. Der Helfer setzt in `/boot/firmware/cmdline.txt` außerdem `usbcore.authorized_default=0`, damit der Kernel Geräte schon vor dem Start von USBGuard standardmäßig deaktiviert. Die USBGuard-Verwaltung ist auf root beschränkt. [USBGuard-Regeln](https://manpages.debian.org/trixie/usbguard/usbguard-rules.conf.5.en.html) · [USB-Autorisierung im Linux-Kernel](https://www.kernel.org/doc/html/v6.5/usb/authorization.html)

Prüfe nach dem Neustart mit `cat /sys/module/usbcore/parameters/authorized_default` den Wert `0`. Teste Touch und Anmeldung mit einer Karte. Ziehe den Leser einmal ab und stecke ihn am selben Port wieder ein. Prüfe in der Kasse, ob er wieder erkannt wird. Prüfe dann mit einem leeren Teststick und einer gewöhnlichen USB-Tastatur, dass `sudo usbguard list-devices --blocked` beide Geräte aufführt. Der Teststick darf kein Laufwerk bereitstellen und die Tastatur keine Eingaben auslösen. Wiederhole die Prüfung an weiteren Terminals.

USBGuard bewertet Geräte anhand ihrer USB-Merkmale. Portschlösser bleiben als physischer Schutz sinnvoll. Die USB-Sperre greift im Betriebssystem. Wenn du auch den USB-Start über die Firmware unterbinden willst, setze am Pi 5 im EEPROM `BOOT_ORDER=0xf1` für Start von microSD. [Raspberry Pi · EEPROM-Bootreihenfolge](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#BOOT_ORDER)

**Leser ersetzen oder Port wechseln.** Den neuen Leser direkt anschließen, den Port über `sudo usbguard list-devices` ablesen und den Einrichtungsbefehl mit diesem Port erneut ausführen. Das Skript ersetzt die bisherige Leserregel. Nach einem Firmware- oder Systemupdate den Kartenleser nach einem Neustart erneut prüfen.

**Rückweg per SSH.** Auf dem Pi lassen sich die Änderungen mit den bei der ersten Einrichtung erzeugten Sicherungen zurücknehmen. Vor dem folgenden Ablauf die USB-Ports wieder physisch sichern.

```bash
sudo systemctl disable --now usbguard.service
sudo cp /etc/usbguard/usbguard-daemon.conf.pre-kostbar /etc/usbguard/usbguard-daemon.conf
sudo cp /boot/firmware/cmdline.txt.pre-kostbar /boot/firmware/cmdline.txt
sudo reboot
```

### Grafischen Kiosk starten

`pi/install.sh` richtet LightDM für die separate Sitzung `kostbar-kiosk` ein. Sie startet labwc mit einer root-eigenen Konfiguration unter `/etc/kaffeekasse-kiosk/labwc/` und öffnet Chromium nativ unter Wayland. Die Sitzung lädt weder Pi-Panel noch Anwendungsmenü oder normale Desktop-Tastenkürzel. Das Konto `kiosk` hat ein gesperrtes Passwort. Zulässig sind die eigene Gruppe und gegebenenfalls `autologin`. Beim Upgrade entfernt der Installer eine vorhandene Mitgliedschaft in Debians allgemeiner Gruppe `users`. Er prüft auch explizite sudo-Rechte. Polkit verweigert diesem Konto privilegierte Aktionen. Der Kartenleser läuft als Systemdienst unter `kaffeekasse` und liest seine Konfiguration aus einem eigenen Verzeichnis. Für die Wartung bleibt das getrennte SSH-Konto vorgesehen.

Ein transparentes Cursor-Theme blendet den Mauszeiger aus. labwc gibt native Touch-Ereignisse direkt an Chromium weiter. Nach der Installation den Pi neu starten.

```bash
sudo reboot
```

Chromium öffnet die im Geräteprofil konfigurierte NAS-Adresse (QNAP standardmäßig `https://kostbar.internal.lan:18443/`, Synology mit der bei `--origin` angegebenen Adresse). Sobald sich der Leserdienst gemeldet hat, zeigt der Kiosk seinen Verkaufspunkt und einen achtstelligen Code, der fünf Minuten gültig ist. Öffne am Arbeitsplatz die passende NAS-Adresse mit `/admin` und wähle **Verkauf → Verkaufspunkte → Koppeln** beim angezeigten Standort. Vergleiche den Standort mit der physischen Aufstellung und bestätige den Code. Danach wechselt der Pi automatisch zur Kasse. Wiederhole die Schritte an jedem weiteren Pi.

Bei einem Neustart bleibt die Kopplung erhalten. Im laufenden Betrieb verlängert KoSTbar die Gültigkeit des Geräte-Cookies. Ist das Cookie nach längerer Inaktivität abgelaufen, löse die Zuordnung und kopple den Pi erneut. Unter **Verkauf → Verkaufspunkte → Kopplung lösen** widerrufst du die bisherige Browser- und Leserzuordnung. Wenn Chromium beendet wird oder das NAS beim Start noch fehlt, wartet der Launcher auf den Healthcheck und startet den Browser erneut.

### Verlorenen Pi ersetzen und Lesertoken wechseln

1. Unter **Verkauf → Verkaufspunkte** die Zuordnung des betroffenen Geräts lösen. Das technische WLAN-Konto des betroffenen Terminals beim RADIUS-Dienst sperren.
2. Einen neuen zufälligen Token erzeugen, etwa mit `openssl rand -hex 32`. In `config/server.json` unter `terminals` beim betroffenen Standort den Wert `token` ersetzen. Bei einem in der Verwaltung angelegten Standort ohne bisherigen Konfigurationseintrag dort seine vorhandene Kennung mit `label` und neuem `token` ergänzen. Der Eintrag für einen Standort namens `etage-2` sieht innerhalb von `terminals` so aus.

   ```json
   "etage-2": {
     "label": "Etage 2",
     "token": "HIER_DEN_NEU_ERZEUGTEN_TOKEN_EINTRAGEN"
   }
   ```

   Den `card_key` beibehalten. Die Konfigurationsdatei muss weiterhin der App-UID `10001` zugänglich sein.
3. Im NAS-Unterordner die App mit dem tatsächlich verwendeten Projektnamen neu erstellen. Beispiel für das Projekt `kostbar`.

   ```bash
   sudo docker compose -p kostbar up -d --no-deps --force-recreate app
   sudo docker compose -p kostbar ps app
   ```

4. In der Verwaltung ein frisches Pi-Profil für den Standort herunterladen. Das Profil auf dem Ersatz-Pi installieren, ein eigenes RADIUS-Konto nach Schritt 2 einrichten und den Pi neu koppeln. Ältere Kopien des Profils enthalten noch den früheren Token.

### Autostart prüfen

Mit `sudo lightdm --show-config` den wirksamen Autologin `kiosk` und `autologin-session=kostbar-kiosk` prüfen. Die Skalierung steht in `/etc/kaffeekasse-kiosk/labwc/autostart`. Der Installer übernimmt beim Upgrade einen vorhandenen Skalierungswert sowie Touch-Zuordnungen und Kalibrierungsmatrizen aus der bisherigen labwc-Konfiguration. Für das Referenzdisplay ist `KIOSK_SCALE=1.5` der Ausgangswert. Bei Bedarf den Wert beim erneuten Aufruf von `pi/install.sh` setzen. [labwc-Konfiguration](https://labwc.github.io/labwc-config.5.html)

### Displaydrehung und Chromium

Der Launcher setzt `wlr-randr --output DSI-2 --transform 270` vor der ersten Verbindungsprüfung zum NAS. `wlr-randr` zeigt in einem Terminalfenster einer laufenden grafischen Wayland-Sitzung den tatsächlichen Ausgang. Den Namen möglichst vor der Kiosk-Umstellung aus der normalen Sitzung ermitteln. Bei abweichendem Namen den Ausgang in `pi/start-kiosk.sh` anpassen und den Installer erneut ausführen. Kann die Drehung nicht angewendet werden, läuft der Kioskstart weiter. Dann die Ausrichtung und Touch-Zuordnung vor der Freigabe korrigieren.

Die Pflicht-Richtlinien in `/etc/chromium/policies/managed/90-kostbar-kiosk.json` gelten für Chromium auf dem gesamten Terminal-Pi. Sie erlauben die KoSTbar-Adresse aus dem Geräteprofil und den Projektpfad auf GitHub. Die Verwaltungsoberfläche und die Admin-API werden als Navigationsziele gesperrt. Datei-Auswahldialoge, Downloads, Drucken, Entwicklerwerkzeuge, Remote-Debugging und Erweiterungsinstallationen sind deaktiviert. Die Lizenz bleibt lokal in KoSTbar lesbar. Zahlungen per PayPal-QR werden auf einem separaten Gerät geöffnet. Die GitHub-Seite benötigt Internetzugang auf dem Pi. Chromium startet mit dem bestehenden persistenten Kiosk-Profil, damit die Gerätezuordnung erhalten bleibt. [Chromium-URL-Filter](https://www.chromium.org/administrators/url-blocklist-filter-format/)

Bei einer Neuinstallation mit leerer Datenbank jeden Pi mit dem neuen Geräteprofil und gegebenenfalls der neuen CA einrichten und neu koppeln. Bei einem Upgrade mit übernommener Datenbank und Konfiguration können die bestehenden Profile und Kopplungen weiterverwendet werden. Falls der Pi bei einer Neuinstallation keine Kopplung anbietet, Geräteprofil, NAS-Ziel, Dienststatus und gegebenenfalls eine bereits hinterlegte Zuordnung unter **Verkaufspunkte** prüfen.

## 6. Am echten Display abnehmen

Für ein [manuell angelegtes Konto](BETRIEB.md#benutzer-manuell-anlegen) die vollständige erste Anmeldung mit einem freien Testausweis prüfen. Nach der Start-PIN müssen Zustimmung, Kartenzuordnung und der Wechsel auf eine andere, bestätigte PIN vor dem Sortiment erfolgen.

Nach einem vollständigen Neustart die automatische WLAN-Anmeldung per PEAP/MSCHAPv2 und den HTTPS-Zugriff über das Terminal-VLAN prüfen. Vor der ersten Berührung kontrollieren, dass bereits beim Sitzungsstart kein Mauszeiger sichtbar ist. Danach die Orientierung und den Touch an allen Ecken prüfen. In Nutzungsbedingungen, Datenschutzerklärung, Produktliste und Warenkorb mit einem Finger wischen. Im PayPal-Dialog Betrag, Tastatur, QR-Code und Schaltfläche auf gleichzeitige Sichtbarkeit prüfen. Registrierung mit Vorname, Nachname, Referat einschließlich Ziffern sowie Zustimmungsfeld öffnen. Tastatur, Formular und Bestätigung müssen bei der gewählten Skalierung passen. Manuelle Anmeldung mit Groß- und Kleinbuchstaben testen. Nach 20 Sekunden ohne Eingabe muss die Sitzung enden. Der Beleg bleibt nach einem Kauf zehn Sekunden und nach einer Barzahlung acht Sekunden sichtbar. Kartenleser nach Abziehen und erneutem Anstecken am freigegebenen Port prüfen. Prüfe außerdem am Startbildschirm und in Nutzungsbedingungen sowie Projektdialog, dass keine Desktop-Oberfläche, Datei-Auswahl oder Entwicklerwerkzeuge erreichbar sind. Prüfe den lokalen Lizenztext und bei freigegebenem Internetzugang den Projektlink. Kontrolliere vom Wartungsrechner den SSH-Zugang und die Verwaltung. Danach die Schritte an jedem weiteren Pi wiederholen.
