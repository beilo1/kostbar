# KoSTbar auf 40.1.0-rc.3 aktualisieren

Für den Wechsel von **40.1.0-rc.2** auf die dritte Vorabversion. Der NAS-Container aktualisiert das Datenbankschema auf **Version 8**. Das vorhandene Terminal lädt die neue Oberfläche über den Browser. Ein Pi mit RC2-Installer benötigt für diese Änderung keinen erneuten Installerlauf. Für einen noch älteren Pi gilt die [Pi-Anleitung aus RC2](UPDATE-v40.1.md#3-einen-bestehenden-raspberry-pi-aktualisieren).

## 1. Änderungen auf dem RC-Branch übernehmen

Unter Windows PowerShell im bereits geklonten KoSTbar-Repository öffnen. Die Befehle setzen einen sauberen Arbeitsstand und den RC-Branch voraus. Prüfe nach `git status --short`, dass die Ausgabe leer ist. Der Patch enthält die neuen Produktbilder.

```powershell
Set-Location "$env:USERPROFILE\source\KoSTbar-RC"
git fetch origin
git switch refactor/kostbar-backlog
git merge --ff-only origin/refactor/kostbar-backlog
git status --short
git log -1 --oneline
```

Basis des Pakets ist `42cfd2a`. Falls der Branch inzwischen weiter ist, prüfe zuerst den Patch und deine lokalen Änderungen. Die nächsten Befehle führen erst eine Probe durch und legen die Änderungen anschließend in den Index. Sie enden vor dem Commit.

```powershell
$patch = Join-Path $env:USERPROFILE 'Downloads\KoSTbar-40.1.0-rc.3.patch'
git apply --check --index "$patch"
if ($LASTEXITCODE -ne 0) { throw 'Patch passt nicht zum Checkout. Es wurde nichts geändert.' }
git apply --index "$patch"
if ($LASTEXITCODE -ne 0) { throw 'Patch konnte nicht übernommen werden.' }
git diff --cached --check
git diff --cached --stat
```

Nach deiner Prüfung kannst du den Commit mit deiner eingerichteten Git-Identität erstellen und den RC-Branch pushen.

```powershell
git commit -m "Add KoSTbar assortment, reversals and daily exports"
git push origin refactor/kostbar-backlog
```

## 2. App-Image bauen und laufende Instanz sichern

Das Quellcode-ZIP in einen **neuen** Ordner auf dem NAS entpacken, etwa `/share/docker/kostbar-40.1.0-rc.3-src` auf dem TVS-872XT oder `/volume1/docker/kostbar-40.1.0-rc.3-src` auf der DS720+. Die folgenden Befehle gehen vom entpackten Ordner mit `Dockerfile` aus. Bei einem Build auf einem anderen Rechner das Image für `linux/amd64` bauen und [per Archiv importieren](../README.md#app-image-bereitstellen).

```sh
sudo docker build --pull -t kostbar-app:40.1.0-rc.3 . &&
sudo docker image inspect kostbar-app:40.1.0-rc.3 --format '{{.Id}} {{.Os}}/{{.Architecture}}'
```

Den laufenden Compose-Arbeitsordner und das Projekt ermitteln. Wenn der App-Container anders heißt, die tatsächliche ID oder den Namen bei `docker inspect` einsetzen.

```sh
sudo docker ps --filter label=com.docker.compose.service=app \
  --format '{{.Names}}  {{.Image}}  {{.Label "com.docker.compose.project"}}'
sudo docker inspect kostbar-app-1 --format \
  'Arbeitsordner={{index .Config.Labels "com.docker.compose.project.working_dir"}} Dateien={{index .Config.Labels "com.docker.compose.project.config_files"}}'
```

In den **bisherigen** Arbeitsordner wechseln. In einer Standardinstallation endet er in `QNAP` oder `Synology`. Beispielpfad durch die Ausgabe oben ersetzen. Falls für den laufenden Stack zusätzliche Compose-Dateien oder ein separates Env-File benutzt werden, die gleichen Argumente bei den folgenden Compose-Befehlen verwenden und diese Dateien ebenfalls sichern.

```sh
cd '/PFAD/ZUM/AKTUELLEN/COMPOSE-ORDNER'
project=kostbar
sudo docker compose -p "$project" ps
sudo docker compose -p "$project" exec -T app python server.py schema-status
```

Die Nutzung am Terminal pausieren. Das folgende Beispiel sichert Datenbank, Konfiguration und laufendes Image vor Migration 8. Das alte Image erhält einen eindeutigen lokalen Tag. Sichere das Verzeichnis in einem geschützten Bereich.

```sh
(
  set -eu
  umask 077
  stamp=$(date '+%Y%m%d-%H%M%S')
  backup_dir="$PWD/backup-vor-rc3-$stamp"
  rollback_image="kostbar-app:rc3-rollback-$stamp"
  running=$(sudo docker compose -p "$project" ps -q app)
  test -n "$running"
  old_id=$(sudo docker inspect --format '{{.Image}}' "$running")
  mkdir "$backup_dir"
  sudo cp -p .env docker-compose.yml ../compose.common.yml config/server.json "$backup_dir/"
  sudo docker image tag "$old_id" "$rollback_image"
  printf '%s\n' "$rollback_image" > "$backup_dir/rollback-image.txt"
  sudo docker compose -p "$project" stop app
  sudo docker compose -p "$project" exec -T db \
    pg_dump -U postgres -d kaffeekasse -Fc > "$backup_dir/kasse.dump"
  sudo docker compose -p "$project" exec -T db \
    pg_restore --list < "$backup_dir/kasse.dump" > /dev/null
  printf 'Sicherung %s\nRückweg-Image %s\n' "$backup_dir" "$rollback_image"
)
```

## 3. App umstellen und abnehmen

Im bestehenden Compose-Arbeitsordner `.env` bearbeiten und `KOSTBAR_APP_IMAGE` auf `kostbar-app:40.1.0-rc.3` setzen. Die bisherige Konfiguration, Compose-Projektkennung und Volumes weiterverwenden. Falls für CSS oder JavaScript noch eine manuelle Einbindung in den Container existiert, die entsprechende Mount-Zeile aus der bestehenden Compose-Datei entfernen, damit der Container die aktualisierte Oberfläche liefert.

```sh
sudo docker compose -p "$project" config --quiet &&
sudo docker compose -p "$project" config --images &&
sudo docker compose -p "$project" up -d --no-deps --force-recreate --pull never app &&
sudo docker compose -p "$project" ps app
```

Sobald `app` den Zustand `healthy` erreicht, das Schema und die bekannte HTTPS-Adresse mit `/healthz` prüfen. Bei einem Fehler zeigt `sudo docker compose -p "$project" logs --tail=80 app` die Startmeldungen.

```sh
sudo docker compose -p "$project" exec -T app python server.py schema-status
```

Die letzte Zeile muss `8 · catalog_categories_and_order` zeigen. Aktualisiere den Browser am Terminal. Prüfe in der Verwaltung bekannte Produkte wie Knoppers, Oreo und Mentos sowie die Zuordnung von eigenen oder umbenannten Produkten. Die Migration erkennt bekannte Namen, allgemeine oder unbekannte Süßigkeiten bleiben unter **Süßes**. Stückpreise, Verkaufsstellen und frühere Buchungen bleiben erhalten.

- Unter **Verkauf → Sortiment → Getränke** mit den Pfeilen die gewünschte Reihenfolge festlegen. Die Sortierung gilt installationsweit und jeder Verkaufspunkt zeigt daraus seine zugeordneten Produkte.
- In der Terminal-Vorschau die vier Kategorien, die Live-Vorschau eines neuen Produkts und die 20/10/8 Sekunden prüfen. Die Sammelkarte zählt weiter nur die in der Verwaltung als **Heißgetränke** geführten Artikel.
- Am Pi den NFC-Hinweis und einen Benutzerwechsel im Zahlungsdialog prüfen. Das Feld darf keine früheren Eingaben vorschlagen. Ein vorgeschlagener Betrag aus dem aktuellen offenen Saldo gehört weiterhin zum Zahlungsablauf.
- Einen Storno möglichst zuerst auf der Synology-Testinstanz mit einem Testkonto abnehmen. Im Kassenbuch die Buchung stornieren, den Saldo prüfen und **Stornos anzeigen** aktivieren. Für eine tatsächliche PayPal-Rückzahlung den Vorgang separat in PayPal bearbeiten.
- KoSTbar aktualisiert den bisherigen Standardabsatz zu den Abmeldezeiten beim ersten Start. Wurde er vorher individuell umgeschrieben, den Text unter **Verwaltung → Nutzungshinweise** prüfen. Eine geänderte Fassung kann beim nächsten Login erneut zur Bestätigung erscheinen.

## 4. Täglichen Saldenexport einrichten

Den NAS-Zeitplan auf **23:00 Uhr in der Zeitzone Europe/Berlin** einstellen. Das Skript verwendet für den Dateinamen ebenfalls das Berliner Datum. Der separate Aufräumlauf um **23:15 Uhr** entfernt ausschließlich datierte KoSTbar-Saldenexporte ab einem Dateialter von 90 Tagen. Export und Aufräumen laufen auf dem NAS-Host. Ein zusätzlicher Container oder ein Bind-Mount ist dafür nicht erforderlich.

| NAS | Zielordner |
| --- | --- |
| Synology DS720+ | `/volume1/kostbar-backup` |
| QNAP TVS-872XT | `/share/kostbar-backup` |

Den Exportordner bei Bedarf als geschützten Ordner beziehungsweise als NAS-Freigabe anlegen. Der Scheduler-Benutzer braucht Schreibzugriff auf diesen Ordner und Zugriff auf den App-Container. Für die Beispielsjobs wird das NAS-Administratorkonto verwendet. Die XLSX enthält personenbezogene Salden. Setze die Freigabe- und Backup-Berechtigungen entsprechend.

Den entpackten Quellordner oder eine dauerhafte Kopie von `nas/saldenexport.sh` an einem persistenten Pfad aufbewahren. Den Docker-Pfad in der SSH-Sitzung mit `sudo sh -c 'command -v docker'` ermitteln und in den Beispielen einsetzen. Das Skript führt den Export per Compose im bestehenden App-Container aus. Es legt höchstens eine fertige Datei pro Datum an. Ein Fehler vor dem vollständigen Export hinterlässt keine fertige XLSX.

**Synology** unter **Systemsteuerung → Aufgabenplaner → Erstellen → Geplante Aufgabe → Benutzerdefiniertes Skript**. Zwei tägliche Aufgaben anlegen. Im ersten Befehl RC3-Quellpfad, bisherigen Compose-Ordner und Docker-Pfad prüfen.

```sh
# 23:00
/bin/sh /volume1/docker/kostbar-40.1.0-rc.3-src/nas/saldenexport.sh export synology \
  /volume1/docker/kostbar-v40-rc/Synology /usr/local/bin/docker kostbar

# 23:15
/bin/sh /volume1/docker/kostbar-40.1.0-rc.3-src/nas/saldenexport.sh cleanup synology
```

**QNAP** die zwei Zeilen in die persistente Datei `/etc/config/crontab` aufnehmen. Pfade vorher prüfen. Die vorhandenen NAS-Einträge stehen lassen. Dann die Crontab gemäß QNAP neu laden.

```cron
0 23 * * * /bin/sh /share/docker/kostbar-40.1.0-rc.3-src/nas/saldenexport.sh export qnap /share/docker/kostbar/QNAP /PFAD/ZU/docker kostbar
15 23 * * * /bin/sh /share/docker/kostbar-40.1.0-rc.3-src/nas/saldenexport.sh cleanup qnap
```

```sh
sudo crontab /etc/config/crontab &&
sudo /etc/init.d/crond.sh restart
```

Die Ausgabe des ersten geplanten Exports prüfen. Für einen sofortigen Test kann die zugehörige Exportaufgabe manuell gestartet werden. Damit wird bereits die Datei für den heutigen Tag angelegt. Den Dateinamen, den Stichtag in der Tabelle und den Saldo von einem bekannten Testkonto prüfen. Ein späterer Lauf am selben Tag lässt die bereits veröffentlichte Datei bestehen.

Die NAS-Dokumentation beschreibt [QNAP-Cronjobs](https://www.qnap.com/en-us/how-to/faq/article/how-to-add-jobs-to-crontab-to-schedule-a-job) und [benutzerdefinierte Aufgaben in DSM](https://kb.synology.com/en-af/DSM/tutorial/common_mistake_in_task_scheduler_script).

## 5. Rückweg

Bis zur Abnahme die Kasse im Wartungsfenster lassen. Falls Schema 8 bereits angewendet wurde, startet der bisherige RC2-Code erst wieder mit dem passenden alten Datenbankschema. Ein Restore überschreibt nach dem Sicherungspunkt entstandene Buchungen. Den aktuellen Stand vor der Rücksicherung separat sichern und danach entstandene Buchungen berücksichtigen.

Den tatsächlichen Sicherungsordner verwenden. `.env` danach auf den zuvor notierten Rückweg-Tag einstellen. Falls du beim Update einen manuellen Mount entfernt hast, die Compose-Datei anhand der Sicherung wiederherstellen.

```sh
backup_dir='/PFAD/ZUR/SICHERUNG'
previous_image=$(cat "$backup_dir/rollback-image.txt")
test -n "$previous_image" &&
sudo docker image inspect "$previous_image" --format '{{.Id}}' &&
sudo docker compose -p "$project" stop app &&
sudo docker compose -p "$project" exec -T db pg_restore -U postgres -d kaffeekasse \
  --clean --if-exists --single-transaction --exit-on-error < "$backup_dir/kasse.dump" &&
sudo cp -p "$backup_dir/.env" .env
```

Dann die bisherige App starten, `schema-status` und `/healthz` kontrollieren und den Exportjob bis zum erneuten RC3-Wechsel deaktivieren.

```sh
sudo env KOSTBAR_APP_IMAGE="$previous_image" docker compose -p "$project" \
  up -d --no-deps --force-recreate --pull never app &&
sudo docker compose -p "$project" ps app
```
