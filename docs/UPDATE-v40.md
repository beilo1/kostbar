# Laufende KoSTbar-Instanz auf v40.0.2 aktualisieren

Beim Wechsel von v39 oder einer älteren v40-Version auf v40.0.2 genügt der Austausch des App-Containers. Die bestehende Geräte-Kopplung und die Datenbank werden weiterverwendet. Die Schritte gelten für QNAP und Synology.

## 1. Neues Image bauen

Entpacke `KoSTbar_v40.0.2.zip` separat. Auf dem QNAP eignet sich zum Beispiel `/share/docker/kostbar-v40.0.2`. Wechsle in den entpackten Ordner mit der neuen `Dockerfile` und führe dort aus:

```sh
sudo docker build -t kostbar-app:40.0.2 .
```

Das QNAP TVS-872XT benötigt ein Image für `linux/amd64`. Falls du das Image auf einem anderen Rechner baust, folge den [Schritten zum Export und Import](../README.md#app-image-bereitstellen).

## 2. Bisheriges Deployment vorbereiten

Wechsle in den **bisherigen** Compose-Ordner auf deinem NAS. Für das QNAP-Deployment unter `kostbar-v38`:

```sh
cd /share/docker/kostbar-v38/QNAP
sudo docker inspect --format '{{.Config.Image}}' kostbar-app-1
```

Notiere die Ausgabe für den Rückweg. Bei einem abweichenden Compose-Projektnamen verwende den Namen deiner Instanz und den entsprechenden App-Container. Die [Betriebsanleitung](BETRIEB.md#sicherung-und-wiederherstellung) beschreibt die Sicherung der vorhandenen Instanz.

Bearbeite die vorhandene `.env` und setze `KOSTBAR_APP_IMAGE=kostbar-app:40.0.2`. Wenn die Variable schon vorhanden ist, ersetze ihren Wert. Falls ein früherer manueller Schrift-Override das Ziel `/app/static/style.css` überschreibt, entferne diese Mount-Zeile aus `app → volumes`, damit das Image das neue Stylesheet liefert.

## 3. App neu erstellen und prüfen

Im bisherigen Compose-Ordner ausführen:

```sh
sudo docker image inspect kostbar-app:40.0.2 --format '{{.Id}}' &&
sudo env KOSTBAR_APP_IMAGE=kostbar-app:40.0.2 docker compose -p kostbar config --quiet &&
sudo env KOSTBAR_APP_IMAGE=kostbar-app:40.0.2 docker compose -p kostbar \
  up -d --no-deps --force-recreate --pull never app &&
sudo docker compose -p kostbar ps app
```

Wenn der Status zunächst `starting` lautet, `sudo docker compose -p kostbar ps app` wiederholen, bis der Container `healthy` ist. Lade die Kiosk-Seite auf dem Raspberry Pi neu, zum Beispiel über Strg+R mit einer Tastatur. Prüfe die PIN-Anmeldung, das Sortiment und die Zahlungsdialoge. Auch in langen Buchungslisten und Rechtstexten bleibt das X oben rechts erreichbar.

Für den Rückweg setze in `.env` die zuvor notierte Image-Referenz und verwende dieselbe Referenz an beiden Stellen im Compose-Block.
