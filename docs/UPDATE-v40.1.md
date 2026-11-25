# KoSTbar auf v40.1.0-rc.2 aktualisieren

Dieser Ablauf beginnt mit dem Import des Kandidaten auf Windows, aktualisiert eine bestehende QNAP-Installation und endet mit dem Merge auf GitHub. Für Synology steht die Abweichung jeweils beim betreffenden Schritt. Bei einem bereits ausgecheckten Kandidaten kannst du direkt beim NAS-Update einsteigen.

Der Ablauf gilt für v40.0.2 und v40.1.0-rc.1. Der zweite Kandidat ergänzt Datenbankmigration 7 für manuell angelegte Benutzer. Sichere vor dem Start die Datenbank aus dem bisherigen Stand. Bereits veröffentlichte Nutzungsbedingungen behalten ihren Text und ihre Fassung. Falls darin eine feste Kaufbelegzeit genannt ist, kannst du sie vor Freigabe unter **Verwaltung → Nutzungshinweise** auf acht Sekunden aktualisieren.

| Reihenfolge | Wo | Ergebnis |
| --- | --- | --- |
| 1 | Windows und GitHub | Kandidaten-Branch gepusht und Quellcode für den Build exportiert |
| 2 | NAS und Admin-Rechner | App-Image gebaut, Bestand gesichert, App ausgetauscht und geprüft |
| 3 | Raspberry Pi | Neue Kiosksitzung auf einem Terminal installiert und geprüft |
| 4 | GitHub | Geprüfte Commits nach `main` gemergt |

Die Befehle verwenden das Compose-Projekt `kostbar` und ein QNAP TVS-872XT. Prüfe die tatsächlichen Namen und Pfade anhand der Ausgabe. Für den App-Wechsel ein kurzes Wartungsfenster einplanen. NAS und Pi separat aktualisieren, damit die Ursache bei einem Fehler erkennbar bleibt.

## 1. Kandidaten-Branch importieren und pushen

### Frischen Checkout in PowerShell anlegen

Das aktuelle `KoSTbar-Backlog.bundle` nach `Downloads` laden. Es enthält den Import der produktiven Basis v40.0.2 und die einzelnen Commits für den Kandidaten. Das öffentliche Repo liefert die gemeinsame Git-Historie. Der folgende Zielordner soll noch frei sein. Die Befehle der Reihe nach ausführen und bei einer Fehlermeldung anhalten.

```powershell
$checkout = Join-Path $env:USERPROFILE 'source\KoSTbar-RC'
$bundle = Join-Path $env:USERPROFILE 'Downloads\KoSTbar-Backlog.bundle'

git clone https://github.com/beilo1/kostbar.git "$checkout"
Set-Location "$checkout"
git bundle verify "$bundle"
git fetch "$bundle" "refs/heads/refactor/kostbar-backlog"
git switch --create refactor/kostbar-backlog FETCH_HEAD
git log --oneline origin/main..HEAD
git show HEAD:Dockerfile | Select-String 'image.version='
git status --short
```

Die Commit-Liste muss den v40.0.2-Basisimport und die anschließenden Refactoring- und Dokumentationsänderungen zeigen. Im Dockerfile muss `40.1.0-rc.2` stehen. `git status --short` soll leer sein. Falls dein Browser den Dateinamen mit einem Zusatz gespeichert hat, den Pfad in `$bundle` anpassen.

### Bestehenden RC-Checkout aktualisieren

Falls `KoSTbar-RC` bereits existiert, lade das aktuelle Bundle und führe im bestehenden Checkout einen Fast-Forward aus. Prüfe mit `git status --short`, dass der Arbeitsbaum sauber ist. Fahre danach mit dem Push und Quellcode-Export fort.

```powershell
$bundle = Join-Path $env:USERPROFILE 'Downloads\KoSTbar-Backlog.bundle'
git switch refactor/kostbar-backlog
git bundle verify "$bundle"
git fetch "$bundle" refs/heads/refactor/kostbar-backlog
git merge --ff-only FETCH_HEAD
```

### Branch veröffentlichen und Quellcode exportieren

Im selben Checkout ausführen.

```powershell
git push -u origin refactor/kostbar-backlog
git rev-parse HEAD
$archive = Join-Path $env:USERPROFILE 'Downloads\KoSTbar-40.1.0-rc.2-Quellcode.zip'
git archive --format=zip --output="$archive" HEAD
```

Den ausgegebenen vollständigen Commit-Hash für den Image-Build notieren. Ein regulärer Push kann einen älteren Stand desselben Branches auf GitHub fortschreiben. Wird der Push wegen abweichender Commits abgelehnt, zuerst die Historie vergleichen und die Abweichung klären. Einen Force-Push vermeiden.

Auf GitHub unter **Pull requests → New pull request** `base: main` und `compare: refactor/kostbar-backlog` wählen und einen Entwurf öffnen. Die Register **Commits** und **Files changed** prüfen. In den Branch gehören Quellcode und Dokumentation. `.env`, `config/server.json`, private Pi-Profile, NAS-Sicherungen und Zertifikatsschlüssel bleiben in der Betriebsumgebung. Das ZIP aus `git archive` enthält die von Git erfassten Dateien des ausgewählten Commits.

## 2. Bestehende NAS-Anwendung aktualisieren

### 2.1 App-Image separat bauen

In QNAP File Station das Quellcode-ZIP in einen neuen Ordner hochladen und dort entpacken, zum Beispiel in `/share/docker/kostbar-40.1.0-rc.2-src`. Das `Dockerfile` liegt direkt in diesem Build-Ordner. Die bestehende Installation liegt unter `/share/docker/kostbar`. Auf dem NAS per SSH ausführen und den Commit-Hash sowie bei Bedarf den Build-Pfad ersetzen.

```bash
rc_commit='VOLLSTAENDIGEN_COMMIT_HASH_EINTRAGEN'
cd /share/docker/kostbar-40.1.0-rc.2-src &&
test -f Dockerfile &&
test "${#rc_commit}" -eq 40 &&
grep -F 'org.opencontainers.image.version="40.1.0-rc.2"' Dockerfile &&
sudo docker build --pull \
  --label "org.opencontainers.image.revision=$rc_commit" \
  -t kostbar-app:40.1.0-rc.2 . &&
sudo docker image inspect kostbar-app:40.1.0-rc.2 \
  --format '{{.Id}} {{.Os}}/{{.Architecture}} {{index .Config.Labels "org.opencontainers.image.revision"}}'
```

Erwartet sind eine Image-ID, `linux/amd64` und der notierte Commit-Hash. Der Build startet keinen Container. Alternativ das Image auf einem Docker-Rechner für `linux/amd64` bauen und mit [Image-Export und -Import](../README.md#app-image-bereitstellen) bereitstellen. Bei Synology DS720+ gilt ebenfalls `linux/amd64`.

### 2.2 Laufende Instanz identifizieren

Auf dem NAS den Compose-Projektnamen, Arbeitsordner und die verwendeten Compose-Dateien ermitteln.

```bash
sudo docker ps --filter label=com.docker.compose.service=app \
  --format '{{.Names}}  {{.Image}}  {{.Label "com.docker.compose.project"}}'
sudo docker inspect kostbar-app-1 --format \
  'Ordner={{index .Config.Labels "com.docker.compose.project.working_dir"}} Dateien={{index .Config.Labels "com.docker.compose.project.config_files"}} Image={{.Config.Image}}'
```

Bei dir sollte das App-Image v40.0.2 oder v40.1.0-rc.1 angezeigt werden. Falls Container oder Projekt anders heißen, den tatsächlichen Namen verwenden. Im QNAP-Beispiel liegt die Compose-Datei unter `/share/docker/kostbar/QNAP`. Zeigt `docker inspect` einen anderen Arbeitsordner an, verwende den angezeigten Pfad. Bei Synology in den angezeigten `Synology/`-Ordner wechseln. Bei einem Deployment mit zusätzlichen `-f`-Dateien oder `--env-file` diese bei allen Compose-Befehlen entsprechend ergänzen und die betreffenden Dateien ebenfalls sichern.

```bash
project=kostbar
cd /share/docker/kostbar/QNAP &&
pwd &&
sudo docker compose version &&
sudo docker compose -p "$project" ps &&
sudo docker compose -p "$project" exec -T app python server.py schema-status
```

Erwartet sind die laufenden Dienste `db`, `app` und `proxy` sowie Migrationsversionen **1 bis 6**. Am Arbeitsplatz die bekannte HTTPS-Adresse mit `/healthz` öffnen. Sie muss `{"ok": true}` liefern. Die Admin-Anmeldung prüfen und einen bestehenden Verkaufspunkt für den späteren Vergleich notieren. Ab hier im selben SSH-Fenster und im produktiven Compose-Ordner bleiben.

### 2.3 Zustand und Rückweg sichern

Für die kurze Umschaltung die Nutzung an den Terminals pausieren. Der Block sichert Datenbank und Konfiguration und versieht exakt das laufende App-Image mit einem lokalen Rückweg-Tag. Bei QNAP sichert er zusätzlich die Caddy-Daten mit der internen CA. Auf Synology werden Zertifikat und DSM-Regel separat im [Betriebshandbuch](BETRIEB.md#sicherung-und-wiederherstellung) gesichert.

```bash
(
  set -eu
  umask 077
  stamp=$(date +%Y%m%d-%H%M%S)
  backup_dir="$PWD/backup-vor-40.1.0-rc.2-$stamp"
  rollback_image="kostbar-app:rollback-$stamp"
  app_id=$(sudo docker compose -p "$project" ps -q app)
  test -n "$app_id"
  old_ref=$(sudo docker inspect --format '{{.Config.Image}}' "$app_id")
  old_id=$(sudo docker inspect --format '{{.Image}}' "$app_id")

  mkdir "$backup_dir"
  sudo cp -p .env config/server.json docker-compose.yml ../compose.common.yml "$backup_dir/"
  sudo docker image tag "$old_id" "$rollback_image"
  printf '%s\n' "$old_ref" > "$backup_dir/bisheriges-image.txt"
  printf '%s\n' "$rollback_image" > "$backup_dir/rollback-image.txt"

  sudo docker compose -p "$project" exec -T db \
    pg_dump -U postgres -d kaffeekasse -Fc > "$backup_dir/kasse.dump"
  sudo docker compose -p "$project" exec -T db \
    pg_restore --list < "$backup_dir/kasse.dump" > /dev/null

  case "${PWD##*/}" in
    QNAP)
      sudo docker compose -p "$project" exec -T proxy \
        tar -C /data -czf - . > "$backup_dir/caddy.tar.gz"
      tar -tzf "$backup_dir/caddy.tar.gz" > /dev/null
      ;;
    Synology) ;;
    *) printf '%s\n' 'Plattformordner prüfen.' >&2; exit 1 ;;
  esac

  printf 'Sicherung: %s\nRückweg-Image: %s\n' "$backup_dir" "$rollback_image"
)
```

Den ausgegebenen Sicherungspfad und den Rückweg-Tag notieren. Das Verzeichnis enthält vertrauliche Daten und bleibt im geschützten Sicherungsbereich. `pg_restore --list` prüft, ob das Archiv gelesen werden kann. Eine vollständige Wiederherstellungsprobe erfolgt separat. Bei einem Fehler in diesem Block den laufenden App-Container noch nicht austauschen.

### 2.4 Nur den Dienst `app` austauschen

Im **bisherigen** Compose-Ordner die vorhandene `.env` öffnen und den Eintrag `KOSTBAR_APP_IMAGE` auf genau diese eine Zeile setzen.

```dotenv
KOSTBAR_APP_IMAGE=kostbar-app:40.1.0-rc.2
```

Zum Editieren auf dem NAS eignet sich `sudo vi .env`. Mit `i` bearbeiten, mit `Esc` und `:wq` speichern. Ein früherer optionaler Bind-Mount auf `/app/static/style.css` kann das neue Stylesheet verdecken. Falls dieser Eintrag existiert, die betreffende Zeile unter `app → volumes` vor dem Start auskommentieren. Der Mount von `config/server.json` wird für den Betrieb benötigt.

```bash
sudo docker compose -p "$project" config --images
```

In der Ausgabe muss `kostbar-app:40.1.0-rc.2` stehen. Dann ausführen.

```bash
sudo docker compose -p "$project" config --quiet &&
sudo docker compose -p "$project" up -d --no-deps --force-recreate --pull never app &&
sudo docker compose -p "$project" ps app
```

Bei `starting` nur `sudo docker compose -p "$project" ps app` wiederholen, bis die App `healthy` meldet. PostgreSQL und Caddy laufen mit den vorhandenen Volumes weiter. Bei `unhealthy` oder einem Neustart in Schleife `sudo docker compose -p "$project" logs --tail=80 app` prüfen. Falls nötig direkt den NAS-Rückweg unten verwenden.

### 2.5 Bestehende Installation prüfen

```bash
sudo docker compose -p "$project" exec -T app python server.py schema-status &&
sudo docker inspect --format '{{.Config.Image}} {{.Image}}' \
  "$(sudo docker compose -p "$project" ps -q app)"
```

Die App ergänzt **Version 7 (`manual_account_setup`)** und zeigt anschließend die Versionen **1 bis 7**. Der gestartete Container muss das in Schritt 2.1 gebaute Image verwenden. Danach diese Prüfungen durchführen.

1. Die bekannte NAS-Adresse mit `/healthz` aufrufen. Die Antwort enthält `{"ok": true}`. In `/admin` anmelden und den vorhandenen Verkaufspunkt, Konten und Salden mit dem bisherigen Zustand abgleichen.
2. Im **Kassenbuch** den Filter **Konto**, den Verkaufspunkt und **Stornos anzeigen** prüfen. Für den Vergleich eine vorhandene Stornobuchung verwenden, sofern es bereits eine gibt. Unter **Benutzer** Suche, Sortierung, Spalten und bei genügend Konten den Seitenwechsel prüfen.
3. Unter **Verkauf → Terminal-Vorschau** den Ablauf mit dem Testkonto **Test Gast**, PIN `1234` durchspielen. Damit lassen sich Einkauf, Sammelkarte und Zahlungen simulieren. Die Vorschau ändert keine produktiven Salden. Einen echten Ende-zu-Ende-Buchungstest gegebenenfalls in einer separaten Testinstanz durchführen.
4. Am unveränderten physischen Pi den vorhandenen Verkaufspunkt und die Anmeldung mit NFC und PIN prüfen. Die alte Zuordnung weiterverwenden. Nach der Abmeldung den Abschnitt **Projekt und Lizenz** in den Nutzungshinweisen und den gleichnamigen Dialog aus der Fußzeile öffnen.
5. Die [erste Anmeldung eines manuell angelegten Testkontos](BETRIEB.md#benutzer-manuell-anlegen) mit einem freien Testausweis prüfen. In der Terminal-Vorschau muss der Kaufbeleg acht Sekunden sichtbar sein.

Wenn diese Prüfung erfolgreich ist, den NAS-Stand beibehalten und mit einem Pi weitermachen.

### NAS-Rückweg

Im selben produktiven Compose-Ordner arbeiten. Bei einer neuen SSH-Sitzung dorthin wechseln und `project` wie in Schritt 2.2 setzen. Im folgenden Beispiel den Sicherungspfad ersetzen. Wenn für das Upgrade ein CSS-Mount entfernt wurde, die betroffene Zeile anhand der Sicherung wieder eintragen.

```bash
backup_dir='/PFAD/ZUR/SICHERUNG'
previous_image=$(cat "$backup_dir/rollback-image.txt")
test -n "$previous_image" &&
sudo docker image inspect "$previous_image" --format '{{.Id}}' &&
sudo cp -p "$backup_dir/.env" .env
```

In `.env` `KOSTBAR_APP_IMAGE` auf den oben gesicherten Rückweg-Tag setzen. Den Tag zeigt `cat "$backup_dir/rollback-image.txt"`.

Wenn die Datenbank bereits auf Version 7 aktualisiert wurde, braucht v40.0.2 beziehungsweise v40.1.0-rc.1 die Sicherung **vor** dem Wechsel. Pausiere die Kasse und sichere vor einer Rücksicherung zusätzlich den aktuellen Datenstand. Beim Zurückspielen des früheren Dumps gehen danach entstandene Änderungen und Buchungen verloren. Prüfe bei Zweifeln zuerst das Schema des vorhandenen Datenbestands.

```bash
sudo docker compose -p "$project" stop proxy app &&
sudo docker compose -p "$project" exec -T db pg_restore -U postgres -d kaffeekasse \
  --clean --if-exists --single-transaction --exit-on-error < "$backup_dir/kasse.dump"
```

Nach erfolgreicher Rücksicherung die alte App starten. Wenn der Kandidat Migration 7 noch nicht angewendet hatte, genügt der folgende Image-Wechsel.

```bash
sudo env KOSTBAR_APP_IMAGE="$previous_image" docker compose -p "$project" config --quiet &&
sudo env KOSTBAR_APP_IMAGE="$previous_image" docker compose -p "$project" \
  up -d --no-deps --force-recreate --pull never app &&
sudo docker compose -p "$project" up -d --pull never proxy &&
sudo docker compose -p "$project" ps app
```

`schema-status`, `/healthz`, Verwaltung und Terminal erneut prüfen. Die alte Version muss wieder die Schema-Versionen 1 bis 6 zeigen. [Sicherung und Wiederherstellung](BETRIEB.md#sicherung-und-wiederherstellung)

## 3. Einen bestehenden Raspberry Pi aktualisieren

Diesen Schritt beginnen, wenn die NAS-Abnahme erfolgreich war. Den vollständigen Ordner `pi/` aus **demselben Quellcode-ZIP** übertragen. In PowerShell entpacken und kopieren. Den Beispiel-Hostnamen und das Wartungskonto bei Bedarf ändern.

```powershell
$archive = Join-Path $env:USERPROFILE 'Downloads\KoSTbar-40.1.0-rc.2-Quellcode.zip'
$piSources = Join-Path $env:USERPROFILE 'Downloads\KoSTbar-RC-Quellen'
Expand-Archive -LiteralPath "$archive" -DestinationPath "$piSources"
ssh stf3@kostbar-terminal 'mkdir -p -m 700 "$HOME/kostbar-rc-pi"'
scp -r "$piSources/pi" stf3@kostbar-terminal:kostbar-rc-pi/
```

Beim QNAP die vorhandenen Dateien `terminal-a.json` und `caddy-root.crt` im bisherigen Setup-Ordner weiterverwenden. Bei mehreren Pis mit einem beginnen.

### 3.1 Vorprüfung und Installation

Per SSH mit dem Wartungskonto anmelden, zum Beispiel `ssh stf3@kostbar-terminal`. `labwc --help` muss `--config-dir` aufführen. Die bisherigen Werte für `autologin-user` und `autologin-session` aus `sudo lightdm --show-config` für den Rückweg notieren. Den SSH-Zugang während der Umstellung verfügbar halten.

```bash
labwc --help 2>&1 | grep -F -- --config-dir
sudo lightdm --show-config
```

Nach erfolgreich abgeschlossener Vorprüfung mit den tatsächlichen Pfaden aufrufen.

```bash
sudo bash "$HOME/kostbar-rc-pi/pi/install.sh" \
  "$HOME/kostbar-setup/terminal-a.json" "$HOME/kostbar-setup/caddy-root.crt" &&
sudo systemctl --no-pager status kaffeekasse-terminal-reader.service &&
sudo lightdm --show-config
```

Bei Synology mit öffentlich vertrauenswürdigem Zertifikat und `ca_file: null` das zweite Dateiargument weglassen. Bei einer vorhandenen eigenen NAS-CA beide Dateien verwenden. Chromium-Profil, Zuordnung und konfigurierte Skalierung werden weiterverwendet. Das bisherige WLAN-Profil bleibt bestehen. Der Installer setzt `autologin-user=kiosk` und `autologin-session=kostbar-kiosk`. Wenn beide Werte wirksam sind und der Leserdienst läuft, den Pi mit `sudo reboot` neu starten.

### 3.2 Nach dem Neustart abnehmen

1. Prüfen, dass derselbe Verkaufspunkt direkt startet, das Querformat stimmt und Touch an den vier Ecken und beim Scrollen funktioniert. Eine vorhandene Kopplung soll weiter funktionieren.
2. NFC und PIN testen. Lizenztext in KoSTbar öffnen. Wenn der Pi Internetzugang hat, den Projektlink und den Rückweg zur Kasse prüfen.
3. Prüfen, dass die Kiosksitzung ohne Desktop-Panel startet und dass der Zugang per SSH als Wartungsbenutzer weiter funktioniert. Bei Fehlern über SSH `sudo journalctl -b -u lightdm -u kaffeekasse-terminal-reader --no-pager -n 100` prüfen.
4. Erst danach weitere Pis umstellen. [Vollständige Abnahme am Display](TERMINALS.md#6-am-echten-display-abnehmen)

### Pi-Rückweg für die grafische Sitzung

Über das Wartungskonto per SSH auf den Pi gehen. Die Sicherung `lightdm.conf.pre-kostbar-kiosk-session` enthält den Stand vor der ersten Installation der neuen Kiosksitzung. Der folgende Block hält bei Fehlern an und zeigt anschließend die wirksame LightDM-Konfiguration.

```bash
sudo sh -eu <<'KOSTBAR_ROLLBACK'
lightdm_backup=/etc/lightdm/lightdm.conf.pre-kostbar-kiosk-session
policy=/etc/chromium/policies/managed/90-kostbar-kiosk.json
policy_backup=/etc/kaffeekasse-kiosk/chromium-policy.pre-kostbar-kiosk-session.json

test -s "$lightdm_backup"
cp -p "$lightdm_backup" /etc/lightdm/lightdm.conf
if [ -f "$policy_backup" ]; then
  install -D -m 0644 -o root -g root "$policy_backup" "$policy"
else
  rm -f "$policy"
fi
rm -f /etc/polkit-1/rules.d/10-kostbar-kiosk.rules
lightdm --show-config
KOSTBAR_ROLLBACK
```

Die nun wirksamen Autologin-Werte mit den in Schritt 3.1 notierten Werten vergleichen. Erst bei erfolgreichem Rückweg und passender Ausgabe `sudo reboot` ausführen. Danach den bisherigen Kiosk, die Kopplung und SSH erneut prüfen.

## 4. Nach bestandener Abnahme nach main mergen

1. Im GitHub-Pull-Request den getesteten Commit-Hash, die Image-ID und das Ergebnis für NAS, Verwaltungsoberfläche und Pi festhalten. Falls nach dem Build App- oder Pi-Code geändert wurde, aus dem neuen Branch-Stand erneut bauen und die betroffenen Abläufe wiederholen.
2. Den Entwurf auf **Ready for review** setzen und verfügbare GitHub-Prüfungen abwarten.
3. **Create a merge commit** bzw. **Merge pull request** wählen. Dadurch bleiben der v40.0.2-Basisimport und die einzelnen Refactoring-Commits mit ihren Commit-IDs in `main` nachvollziehbar. [GitHub · Merge-Methoden](https://docs.github.com/en/pull-requests/how-tos/merge-and-close-pull-requests/merging-a-pull-request)
4. Im lokalen Windows-Checkout `git switch main` und `git pull --ff-only` ausführen. Das bereits geprüfte Image läuft durch den Merge auf dem QNAP weiter. Eine Veröffentlichung unter einer stabilen Versionsnummer ist ein eigener Release-Schritt.
