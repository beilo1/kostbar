# Laufende KoSTbar-Instanz auf v39 aktualisieren

Diese Anleitung gilt für den historischen Stand v39.0.0. Der [aktuelle Update-Ablauf](UPDATE-v40.1.md) beginnt beim passenden Quellstand.

Beim Wechsel von v38.2.1 auf v39 tauscht Docker Compose nur den App-Container aus. Der Pi-Installer, das Datenbankschema und die veröffentlichten Nutzungs- und Datenschutzhinweise sind identisch. Die Schritte gelten für QNAP und Synology.

## 1. Neues Image bauen

Entpacke `KoSTbar_v39.zip` separat. Auf dem QNAP eignet sich zum Beispiel `/share/docker/kostbar-v39`. Wechsle in den entpackten Ordner mit der neuen `Dockerfile` und führe dort aus:

```sh
sudo docker build -t kostbar-app:39.0.0 .
```

Das QNAP TVS-872XT benötigt ein Image für `linux/amd64`. Exportiere bei einem Build auf einem anderen Rechner mit `docker image save -o kostbar-app-39.0.0.tar kostbar-app:39.0.0`. Übertrage die TAR-Datei auf das NAS und lade sie dort mit `sudo docker image load -i kostbar-app-39.0.0.tar`.

## 2. Bisheriges Deployment vorbereiten

Wechsle in den **bisherigen** Compose-Ordner auf deinem NAS. Für das QNAP-Deployment unter `kostbar-v38`:

```sh
cd /share/docker/kostbar-v38/QNAP
sudo docker inspect --format '{{.Config.Image}}' kostbar-app-1
```

Notiere die Ausgabe für den Rückweg. Bei einem abweichenden Compose-Projektnamen verwende den Namen deiner Instanz und den entsprechenden App-Container. Die [Betriebsanleitung](BETRIEB.md#sicherung-und-wiederherstellung) beschreibt die Sicherung der vorhandenen Instanz.

Bearbeite die vorhandene `.env` und setze `KOSTBAR_APP_IMAGE=kostbar-app:39.0.0`. Wenn die Variable schon vorhanden ist, ersetze ihren Wert. Falls ein früherer manueller Schrift-Override das Ziel `/app/static/style.css` überschreibt, entferne diese Mount-Zeile aus `app → volumes`, damit das Image das neue Stylesheet liefert.

## 3. App neu erstellen und prüfen

Im bisherigen Compose-Ordner ausführen:

```sh
sudo docker image inspect kostbar-app:39.0.0 --format '{{.Id}}' &&
sudo env KOSTBAR_APP_IMAGE=kostbar-app:39.0.0 docker compose -p kostbar config --quiet &&
sudo env KOSTBAR_APP_IMAGE=kostbar-app:39.0.0 docker compose -p kostbar \
  up -d --no-deps --force-recreate --pull never app &&
sudo docker compose -p kostbar ps app
```

Wenn der Status zunächst `starting` lautet, `sudo docker compose -p kostbar ps app` wiederholen, bis der Container `healthy` ist. Lade die Verwaltungsseite im Browser neu und prüfe unter **Benutzer** die getrennten Spalten, beide Sortierrichtungen beim Saldo und einen hinterlegten Kartenträger.

Für den Rückweg setze in `.env` die zuvor notierte Image-Referenz und verwende dieselbe Referenz an beiden Stellen im Compose-Block.
