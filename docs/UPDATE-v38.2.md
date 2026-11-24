# KoSTbar v38.2.1 auf eine bestehende Installation anwenden

Von v38.2 auf v38.2.1 genügt der Austausch des App-Images (Schritte 1 und 2). Der PayPal-Dialog gibt dem vollständigen Link mehr Platz und zeigt ihn einzeilig. Außergewöhnlich lange Links lassen sich in ihrer Zeile seitlich verschieben.

Die v38.2-Reihe übernimmt die größere Terminal-Schrift ins App-Image. Auf dem Pi konfiguriert der Installer native Touch-Ereignisse und schaltet die Passwort-Speicherabfrage von Chromium aus. KoSTbar verwendet ab v38.0.1 dasselbe Datenbankschema. Die vorhandene Konfiguration, PostgreSQL-Daten und Terminalkopplung kannst du übernehmen.

## 1. App-Image bauen

Das neue Projektarchiv in einen separaten Ordner entpacken. Im entpackten Hauptordner mit der neuen `Dockerfile` bauen:

```bash
sudo docker build -t kostbar-app:38.2.1 .
```

Wenn du auf einem anderen Rechner baust, das Image wie in der [Installationsanleitung](../README.md#app-image-bereitstellen) beschrieben exportieren und auf dem NAS laden. Das QNAP TVS-872XT benötigt `linux/amd64`.

## 2. Vorhandenen App-Container aktualisieren

In den **bisherigen** QNAP-Ordner wechseln, zum Beispiel `kostbar-v38/QNAP`. In der Synology-Variante entsprechend den bisherigen Synology-Ordner verwenden. Die bestehende Konfiguration und Datenbank nach der [Betriebsanleitung](BETRIEB.md#backup-und-wiederherstellung) sichern.

```bash
sudo docker inspect --format '{{.Config.Image}}' kostbar-app-1
```

Die ausgegebene bisherige Image-Referenz für den Rückweg notieren. Falls du beim früheren Schrift-Update `KoSTbar_Terminal_Schrift.css` unter `app → volumes` manuell auf `/app/static/style.css` gemountet hast, entferne jetzt genau diesen Zusatz. Sonst liefert der Container weiterhin das alte Stylesheet aus. Der Mount für `config/server.json` wird für den Betrieb benötigt.

In der vorhandenen `.env` die Zeile `KOSTBAR_APP_IMAGE=kostbar-app:38.2.1` setzen. Falls der Schlüssel schon existiert, seinen Wert ersetzen. Anschließend nur den App-Dienst neu erstellen:

```bash
sudo docker image inspect kostbar-app:38.2.1 --format '{{.Id}}' &&
sudo env KOSTBAR_APP_IMAGE=kostbar-app:38.2.1 docker compose -p kostbar config --quiet &&
sudo env KOSTBAR_APP_IMAGE=kostbar-app:38.2.1 docker compose -p kostbar \
  up -d --no-deps --force-recreate --pull never app &&
sudo docker compose -p kostbar ps app
```

Sobald die App `healthy` ist, `/healthz`, die Verwaltung und das Terminal prüfen. v38.2 aktualisiert beim Wechsel von v38.0.x dieselben WLAN-Hinweise wie v38.1. Falls das Backend dadurch eine neue Fassung publiziert, wird diese beim nächsten Zugriff bestätigt.

Für den Rückweg die zuvor notierte Image-Referenz in der `.env` verwenden und den obigen Compose-Start mit diesem Image ausführen. Falls gewünscht, dabei auch den vorherigen CSS-Mount wieder eintragen.

## 3. Bestehenden Raspberry Pi aktualisieren

Diesen Schritt ausführen, wenn auf dem Pi noch ein Installer vor v38.2 verwendet wurde.

Den neuen Projektordner `pi/` zum Beispiel als `~/kostbar-setup/pi-v38.2/` auf den Pi kopieren. Auf **`kostbar-terminal`** per SSH mit dem bereits verwendeten Geräteprofil und der bisherigen QNAP-CA ausführen:

```bash
cd ~/kostbar-setup
sudo bash pi-v38.2/install.sh terminal-a.json caddy-root.crt &&
sudo systemctl restart lightdm
```

Bei einem Synology-Profil mit öffentlich vertrauenswürdigem HTTPS-Zertifikat das zweite Argument weglassen. Der Installer übernimmt den bereits gesetzten `KIOSK_SCALE`, sofern du beim Aufruf keinen neuen Wert vorgibst. WLAN und die Zuordnung zum Verkaufspunkt werden über das bestehende System und Geräteprofil weiter genutzt.

Im Betrieb einmal in den Nutzungshinweisen, in der Datenschutzerklärung, in einer längeren Produktliste und in einem gefüllten Warenkorb wischen. Kontrolle am Display in allen Ecken durchführen. Bei einem bestehenden eigenen labwc-Profil liegt die ursprüngliche Konfiguration nach der Änderung unter `~kiosk/.config/labwc/rc.xml.pre-kostbar-touch`. Falls nötig, diese mit Eigentümer `kiosk` wieder als `rc.xml` übernehmen. Wenn zuvor keine eigene `rc.xml` vorhanden war, kann die neu erzeugte Datei umbenannt werden. Anschließend `lightdm` neu starten.
