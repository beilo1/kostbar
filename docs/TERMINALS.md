# Raspberry-Pi-Terminals einrichten

Die gemeinsamen Installationsdateien liegen im Hauptordner unter `pi/`. Der Konfigurationsgenerator legt das erste Geräteprofil im NAS-Unterordner unter `config/` ab. Weitere Profile lädt der Super-Admin unter **Verkauf → Verkaufspunkte** herunter. Die Verwaltung der Kopplungen liegt ebenfalls beim Super-Admin. Verwende pro Pi das Profil seines Verkaufspunkts und seiner Installation. [Hardware und Anschluss](HARDWARE.md)

## 1. Raspberry Pi OS vorbereiten

Raspberry Pi OS 64-Bit mit Desktop, labwc/Wayland und LightDM verwenden. Im Raspberry Pi Imager das Wartungskonto, SSH, das WLAN-Land und das vorläufige WPA2-/WPA3-Personal-WLAN (PSK) einrichten. Den SSH-Zugang prüfen. Für den Dauerkiosk Screen Blanking deaktivieren. Über das Setup-WLAN alle benötigten Pakete installieren, einschließlich USBGuard für Schritt 5. Danach startet die Umstellung auf das produktive WLAN.

```bash
sudo apt update
sudo apt full-upgrade
sudo rpi-eeprom-update -a
sudo apt install chromium curl unzip pcscd libccid pcsc-tools python3-pyscard \
  libnss3-tools wlr-randr usbguard network-manager openssl nano
sudo reboot
```

Displaymontage und GPIO-Anschluss nur ohne Strom vornehmen. Die vorgesehene Displayausrichtung ist Querformat, Ausgang `DSI-2`, Drehung 270°. Der ACS ACR1252U wird ebenso wie ACR122U und ACR1552U vom mitgelieferten PC/SC-Zugriff berücksichtigt. Die tatsächlich verwendeten Karten an jedem eingerichteten Terminal testen.

## 2. Produktives WLAN mit WPA-Enterprise und EAP-TLS einrichten

Stelle die Terminals einzeln um. Nutze für den Wechsel die lokale Konsole vor der USBGuard-Sperre oder das eingebaute Ethernet. Beim Aktivieren des neuen WLAN-Profils kann eine laufende SSH-Sitzung über das Setup-WLAN abbrechen.

Bei einem bereits eingerichteten Terminal mit den Paketen aus Schritt 1 kannst du hier beginnen. Danach den HTTPS-Test in Schritt 4 und den Neustarttest in Schritt 6 durchführen.

### Werte und Zertifikate vorbereiten

| Benötigt | Wert aus deiner Infrastruktur |
| --- | --- |
| Produktive SSID | WPA-Enterprise mit 802.1X und EAP-TLS. Der WLAN-Access-Point bzw. Controller leitet die Authentifizierung an RADIUS weiter. |
| EAP-Identität | Vom RADIUS-Betrieb vorgegebene Identität für den Pi, ggf. mit Realm. |
| Client-Zertifikat und privater Schlüssel | Ein Gerätezertifikat je Pi mit zugehörigem privatem Schlüssel, etwa als `.p12` / `.pfx` mit Passphrase oder als getrennte PEM-Dateien. Die PKI stellt ggf. die Zwischenzertifikate für die Client-Kette mit bereit. Liegt nur die öffentliche Zertifikatsdatei vor, bei der PKI das passende Schlüsselmaterial oder ein neues Gerätepaket anfordern. |
| RADIUS-CA und Servername | CA-Zertifikat bzw. die freigegebene CA-Kette zur Prüfung des RADIUS-Serverzertifikats, dazu dessen erwarteter DNS-Name aus dem SAN. Beides über die zuständige PKI oder Netzwerkadministration beziehen. |
| Produktives Netz | Das separate Terminal-VLAN mit IP-Konfiguration, internem DNS und dem vorgesehenen HTTPS-Zugriff auf das NAS. Für die Abnahme den SSH-Wartungsweg aus dem vorgesehenen Administrationsnetz prüfen. |

Die CA für die WLAN-Anmeldung gehört in das NetworkManager-Profil. Das HTTPS-Vertrauen für KoSTbar richtest du separat mit dem NAS-Geräteprofil und ggf. der NAS-CA ein.

```bash
systemctl is-active NetworkManager
nmcli device status
nmcli -f NAME,UUID,TYPE,DEVICE connection show --active
timedatectl status
install -d -m 0700 ~/kostbar-setup ~/kostbar-setup/eap-tls
```

Die UUID des Setup-WLAN-Profils notieren. Prüfe die Systemzeit vor dem Wechsel, damit NetworkManager die Gültigkeit der Zertifikate korrekt prüfen kann. Übertrage die WLAN-Dateien über einen vertrauten administrativen Weg in den privaten Ordner. Im Beispiel heißen sie `radius-ca.pem` und `terminal.p12`. Eine `.pfx`-Datei kannst du unter demselben Zielnamen ablegen.

```bash
sudo install -d -o root -g root -m 0700 /etc/NetworkManager/kostbar
sudo install -o root -g root -m 0600 ~/kostbar-setup/eap-tls/radius-ca.pem \
  /etc/NetworkManager/kostbar/radius-ca.pem
sudo install -o root -g root -m 0600 ~/kostbar-setup/eap-tls/terminal.p12 \
  /etc/NetworkManager/kostbar/terminal.p12
sudo openssl pkcs12 -in /etc/NetworkManager/kostbar/terminal.p12 -info -noout
```

OpenSSL fragt die Passphrase interaktiv ab. Prüfe, dass das Paket ein Zertifikat und einen Schlüssel enthält. Bei getrennten PEM-Dateien im zweiten `install`-Aufruf stattdessen `terminal.crt` und anschließend `terminal.key` auf dieselbe Weise kopieren.

### Systemweites WLAN-Profil anlegen

```bash
profile=/etc/NetworkManager/system-connections/KoSTbar-Produktiv.nmconnection
cat /proc/sys/kernel/random/uuid
sudo touch "$profile"
sudo chown root:root "$profile"
sudo chmod 0600 "$profile"
sudo nano --ignorercfiles "$profile"
```

Trage die ausgegebene UUID, SSID, EAP-Identität und den exakten RADIUS-Servernamen ein. Bei einem vorhandenen Produktivprofil dessen UUID beibehalten. Das Beispiel verwendet `wlan0` und automatische IP-Konfiguration. Übernimm den Schnittstellennamen aus `nmcli device status`, falls er abweicht.

```ini
[connection]
id=KoSTbar-Produktiv
uuid=HIER_ERZEUGTE_UUID_EINTRAGEN
type=wifi
interface-name=wlan0
autoconnect=false

[wifi]
mode=infrastructure
ssid=PRODUKTIV-SSID

[wifi-security]
key-mgmt=wpa-eap
proto=rsn;

[802-1x]
eap=tls;
identity=TERMINAL-IDENTITAET
ca-cert=/etc/NetworkManager/kostbar/radius-ca.pem
domain-match=radius.example.invalid
client-cert=/etc/NetworkManager/kostbar/terminal.p12
private-key=/etc/NetworkManager/kostbar/terminal.p12
private-key-password=HIER_PKCS12_PASSPHRASE_EINTRAGEN
private-key-password-flags=0

[ipv4]
method=auto

[ipv6]
method=auto
```

Bei mehreren freigegebenen RADIUS-Servernamen die vollständigen Namen mit Semikolons in `domain-match` aufzählen. Bei getrennten PEM-Dateien `client-cert` auf `terminal.crt` und `private-key` auf `terminal.key` ändern. Für einen verschlüsselten PEM-Schlüssel dessen Passphrase einsetzen. Für einen unverschlüsselten PEM-Schlüssel die Zeile `private-key-password` entfernen und die Flags auf `4` setzen.

Das Profil speichert eine benötigte Passphrase für die automatische Anmeldung beim Boot im Klartext in der geschützten Root-Datei. Gib sie direkt im Editor ein. Einen wörtlichen Backslash als `\\` und führende Leerzeichen als `\s` eingeben. Profile, Schlüssel und Passphrasen vertraulich behandeln.

Das Beispiel gilt für WPA-Enterprise mit `wpa-eap`. Falls der Controller WPA3-Enterprise im 192-Bit-Modus erzwingt, WLAN-Modus und Client-Unterstützung vor der Umstellung separat abgleichen.

### Umschalten und nach Neustart prüfen

```bash
sudo nmcli connection load "$profile"
sudo nmcli --wait 45 connection up id KoSTbar-Produktiv
nmcli -f NAME,UUID,TYPE,DEVICE connection show --active
nmcli device show wlan0
getent hosts kostbar.internal.lan
```

Prüfe, dass `KoSTbar-Produktiv` am WLAN-Interface aktiv ist und RADIUS den Pi angenommen hat. Prüfe Erreichbarkeit und Namensauflösung aus dem produktiven WLAN. Für Synology den Namen aus dem Geräteprofil verwenden. Wenn zusätzlich Ethernet steckt, für die Abnahme den NAS- und SSH-Zugriff gezielt über das WLAN prüfen. Auf einem QNAP-Pi zeigt `ip route get 192.168.3.110` zum Beispiel die verwendete Schnittstelle. Ersetze die Beispiel-IP durch die LAN-IP deines NAS.

Nach erfolgreichem Test die Startprofile setzen. Ersetze die Beispiel-UUID durch die notierte Setup-UUID.

```bash
setup_uuid='HIER-SETUP-PROFIL-UUID'
sudo nmcli connection modify id KoSTbar-Produktiv connection.autoconnect yes
sudo nmcli connection modify uuid "$setup_uuid" connection.autoconnect no
sudo reboot
```

Nach dem Neustart das aktive WLAN-Profil, den RADIUS-Erfolg und den SSH-Zugang ohne weitere Eingabe prüfen. Die private Zwischenkopie nach erfolgreicher Einrichtung vom Pi entfernen. Sobald auch der HTTPS-Test aus Schritt 4 gelingt, das Setup-Profil mit `sudo nmcli connection delete uuid "$setup_uuid"` entfernen, falls es für die Wartung nicht gebraucht wird. Nach einer neuen Anmeldung die Variable dazu erneut mit der notierten UUID setzen.

**Rückweg während der Einrichtung.** Über die lokale Konsole oder Ethernet `sudo nmcli connection modify id KoSTbar-Produktiv connection.autoconnect no` ausführen. Danach das noch gespeicherte Setup-Profil mit `sudo nmcli connection modify uuid "$setup_uuid" connection.autoconnect yes` und `sudo nmcli connection up uuid "$setup_uuid"` wieder aktivieren, sofern die Setup-SSID erreichbar ist. Bei einer abgelehnten WLAN-Anmeldung `sudo journalctl -b -u NetworkManager -u wpa_supplicant --no-pager -n 80` und das RADIUS-Protokoll prüfen. Typische Prüfpunkte sind Systemzeit, Zertifikatsablauf, CA-Kette, RADIUS-Servername und Zuordnung des Gerätezertifikats in der RADIUS-Richtlinie.

[Raspberry Pi OS · Netzwerkverwaltung](https://www.raspberrypi.com/documentation/computers/configuration.html#networking) · [NetworkManager · Dateiformat](https://networkmanager.dev/docs/api/1.44.0/nm-settings-keyfile.html) · [NetworkManager · 802.1X-Einstellungen](https://networkmanager.dev/docs/api/latest/settings-802-1x.html)

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

`pi/install.sh` richtet auf jedem Pi automatisch den unprivilegierten Desktopbenutzer `kiosk`, das LightDM-Autologin, den Boot in die grafische Oberfläche und den Chromium-Autostart in labwc ein. Der Kartenleser startet als Systemdienst. Nach der Installation neu starten:

```bash
sudo reboot
```

Chromium öffnet die im Geräteprofil konfigurierte NAS-Adresse (QNAP standardmäßig `https://kostbar.internal.lan:18443/`, Synology mit der bei `--origin` angegebenen Adresse). Sobald sich der Leserdienst gemeldet hat, zeigt der Kiosk seinen Verkaufspunkt und einen achtstelligen Code, der fünf Minuten gültig ist. Öffne am Arbeitsplatz die passende NAS-Adresse mit `/admin` und wähle **Verkauf → Verkaufspunkte → Koppeln** beim angezeigten Standort. Vergleiche den Standort mit der physischen Aufstellung und bestätige den Code. Danach wechselt der Pi automatisch zur Kasse. Wiederhole die Schritte an jedem weiteren Pi.

Bei einem Neustart bleibt die Kopplung erhalten. Im laufenden Betrieb verlängert KoSTbar die Gültigkeit des Geräte-Cookies. Ist das Cookie nach längerer Inaktivität abgelaufen, löse die Zuordnung und kopple den Pi erneut. Unter **Verkauf → Verkaufspunkte → Kopplung lösen** widerrufst du die bisherige Browser- und Leserzuordnung. Wenn Chromium beendet wird oder das NAS beim Start noch fehlt, wartet der Launcher auf den Healthcheck und startet den Browser erneut.

### Verlorenen Pi ersetzen und Lesertoken wechseln

1. Unter **Verkauf → Verkaufspunkte** die Zuordnung des betroffenen Geräts lösen. Das WLAN-Gerätezertifikat gemäß dem vorgesehenen PKI-Prozess sperren.
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

4. In der Verwaltung ein frisches Pi-Profil für den Standort herunterladen. Das Profil und ein eigenes WLAN-Gerätezertifikat auf dem Ersatz-Pi installieren und den Pi neu koppeln. Ältere Kopien des Profils enthalten noch den früheren Token.

### Autostart prüfen

Mit `sudo lightdm --show-config` lässt sich der wirksame Desktop-Autologin prüfen. Die ursprüngliche LightDM-Konfiguration wird einmal unter `/etc/lightdm/lightdm.conf.pre-kaffeekasse` gesichert. Die Skalierung aus dem Installationsaufruf bleibt im Kiosk-Autostart hinterlegt. Für das 10,1-Zoll-Display im Querformat ist `KIOSK_SCALE=1.5` der Ausgangswert. Bei Bedarf den Wert beim erneuten Aufruf von `pi/install.sh` anpassen. [Offizielle Kioskanleitung](https://www.raspberrypi.com/tutorials/how-to-use-a-raspberry-pi-in-kiosk-mode/)

### Displaydrehung und Chromium

Der Launcher läuft bei jedem Start der grafischen Sitzung des Kiosk-Kontos. Er setzt `wlr-randr --output DSI-2 --transform 270` vor der ersten Verbindungsprüfung zum NAS. So wird die Drehung auch nach einem Neustart erneut angewendet. Bei einem abweichenden Anschlussnamen zeigt `wlr-randr` in der laufenden labwc-Sitzung den tatsächlichen Ausgang. Den Namen bei Bedarf in `pi/start-kiosk.sh` anpassen. Kann die Drehung nicht angewendet werden, läuft der Kioskstart weiter.

Chromium verwendet mit `--password-store=basic` den einfachen Passwortspeicher für das KoSTbar-Kiosk-Profil. Damit entfällt der Keyring-Dialog beim Start.


Bei einer Neuinstallation mit leerer Datenbank jeden Pi mit dem neuen Geräteprofil und gegebenenfalls der neuen CA einrichten und neu koppeln. Bei einem Upgrade mit übernommener Datenbank und Konfiguration können die bestehenden Profile und Kopplungen weiterverwendet werden. Falls der Pi bei einer Neuinstallation keine Kopplung anbietet, Geräteprofil, NAS-Ziel, Dienststatus und gegebenenfalls eine bereits hinterlegte Zuordnung unter **Verkaufspunkte** prüfen.

## 6. Am echten Display abnehmen

Nach einem vollständigen Neustart automatische WLAN-Anmeldung per EAP-TLS, den HTTPS-Zugriff aus dem produktiven WLAN sowie Orientierung und Touch an allen Ecken prüfen. Registrierung mit Vorname, Nachname, Referat einschließlich Ziffern sowie Zustimmungsfeld öffnen. Tastatur, Formular und Bestätigung müssen bei der gewählten Skalierung passen. Manuelle Anmeldung mit Groß- und Kleinbuchstaben testen. Nach 15 Sekunden ohne Eingabe muss die Sitzung enden; nach einem erfolgreichen Kauf beträgt die Anzeigezeit fünf Sekunden. Kartenleser nach Abziehen und erneutem Anstecken am freigegebenen Port prüfen. Danach die Schritte an jedem weiteren Pi wiederholen.
