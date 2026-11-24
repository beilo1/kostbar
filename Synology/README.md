# Synology mit DSM Reverse Proxy – Neuinstallation

Container Manager und Docker Compose bereitstellen. **Den gesamten Projektordner** beispielsweise nach `/volume1/docker/kostbar` kopieren. Nicht nur diesen Unterordner übertragen: Anwendung, `compose.common.yml` und gemeinsame Startskripte werden aus dem Hauptordner verwendet.

## 0. Altinstallation entfernen

Für eine bestehende v35-, v36- oder v37-Instanz gilt die [Upgrade-Anleitung](../README.md#upgrade-einer-bestehenden-installation). Falls du eine Altinstanz für eine Neuinstallation entfernen möchtest, folge der [Löschanleitung](../docs/ALTINSTALLATION-ENTFERNEN.md).

Bei gleicher Adresse kannst du die vorhandene DSM-Reverse-Proxy-Regel, die Zertifikatszuordnung und den DNS-Eintrag für die Neuinstallation verwenden. Ersetze in Schritt 2 den alten Proxy-Schlüssel durch den neuen Wert aus `Synology/.env` und prüfe das Ziel `127.0.0.1:18765`. Bei einem anderen Hostnamen entferne eine überflüssige alte KoSTbar-Regel samt ihrer Zuordnung und lege die neue Regel wie unten beschrieben an. Ein von anderen DSM-Diensten genutztes Zertifikat bleibt in der Zertifikatsverwaltung.

## 1. Konfiguration erzeugen

```bash
cd /volume1/docker/kostbar
sudo docker compose version
sudo docker run --rm \
  --user "$(id -u):$(id -g)" \
  --volume "$(pwd -P):/project" \
  --workdir /project \
  python:3.13-slim-bookworm \
  python configure.py --deployment synology \
    --origin 'https://kostbar.example.org' \
    --contact-name 'Kassen-Team' \
    --contact-reach 'Interne E-Mail oder Durchwahl'
```

Ersetze `kostbar.example.org` in allen Beispielen durch deinen eigenen Hostnamen. Trage ihn bei `--origin`, im DNS, in der DSM-Regel und im Zertifikat passend ein. Passe auch die Kontaktdaten an. Das Skript setzt auch den an die App weitergereichten Host-Header passend. Anders als bei QNAP wird kein `--nas-ip` angegeben.

Erzeugt werden **Synology/.env**, **Synology/config/server.json** und das private Geräteprofil für A. Mit `--label-b` wird auch B eingerichtet. Bestehende Dateien werden nicht überschrieben. Mit `--reader-ca` enthalten die Pi-Profile den Pfad zur eigenen HTTPS-CA. Der zufällige DSM-Proxy-Schlüssel steht in `Synology/.env` unter `KASSE_DSM_PROXY_KEY`.

## 2. DSM Reverse Proxy einrichten

Im internen DNS den verwendeten Hostnamen auf die LAN-IP des NAS setzen. In DSM unter **Systemsteuerung → Anmeldeportal → Erweitert → Reverse Proxy** die KoSTbar-Regel anlegen oder die vorhandene bearbeiten:

| Feld | Beispielwert |
| --- | --- |
| Quelle | HTTPS, `kostbar.example.org`, Port `443` |
| Ziel | HTTP, `127.0.0.1`, Port `18765` |
| Benutzerdefinierter Anfrage-Header `X-KoSTbar-Proxy-Key` | Wert von `KASSE_DSM_PROXY_KEY` aus `.env` |
| Benutzerdefinierter Anfrage-Header `X-KoSTbar-Client-IP` | `$remote_addr` |

Der Proxy-Schlüssel ist ein Geheimnis; ausschließlich in dieser DSM-Regel und der geschützten Konfiguration hinterlegen. Bei belegtem Port `18765` vor dem Start **KASSE_DSM_PORT in .env und das DSM-Ziel** auf denselben freien lokalen Port ändern. Der Port bleibt auf `127.0.0.1` gebunden. Den Zugriff aus dem LAN auf diesen internen Port zusätzlich prüfen, insbesondere bei älteren Docker-Versionen.

Unter **Systemsteuerung → Sicherheit → Zertifikat → Einstellungen** ein für den Hostnamen gültiges Zertifikat der Regel zuweisen. DSM muss die vollständige Zertifikatskette ausliefern. Die Kasse ist für das interne Netz vorgesehen: Wenn DSM auf Port 443 öffentlich erreichbar ist, die Regel mit einem Zugriffskontrollprofil auf eure internen Netze begrenzen und den externen Zugriff separat prüfen. Andere Subdomains können ihre bisherigen Regeln behalten.

## 3. Dienste starten

Zuerst das [gemeinsame App-Image bereitstellen](../README.md#app-image-bereitstellen). Danach in den Unterordner `Synology/` des in Schritt 1 verwendeten Projektordners wechseln. In den Beispielen heißt das Compose-Projekt `kostbar`. Bei einem anderen Projektnamen auch die Netzwerknamen in der Diagnose entsprechend anpassen.

```bash
cd /volume1/docker/kostbar/Synology &&
sudo chmod 600 .env config/server.json &&
sudo chown 10001:10001 config/server.json &&
sudo chmod 755 ../nas/init-db.sh &&
sudo docker compose -p kostbar config --quiet &&
sudo docker compose -p kostbar up -d &&
sudo docker compose -p kostbar ps -a
```

Falls nur `docker-compose` verfügbar ist, dieses Kommando durchgängig verwenden. Beim ersten Start legt Compose die fehlenden Projekt-Volumes an. Bei einer vorhandenen Datenbank müssen die Zugangsdaten zur bestehenden Instanz passen.

Wenn `db` und `app` gesund sind (`healthy`) und `proxy` läuft, prüfe Schema und HTTPS. Verwende bei einem abweichenden Hostnamen die in Schritt 1 konfigurierte Adresse.

```bash
sudo docker compose -p kostbar exec -T app python server.py schema-status &&
curl -fsS --max-time 10 https://kostbar.example.org/healthz
```

Erwartet werden Schema-Versionen **1 bis 6** mit `v35_baseline` als erster Version sowie `{"ok": true}`. Nach dem Healthcheck auch die Admin-Anmeldung separat prüfen. Die App läuft als UID/GID `10001:10001` und PostgreSQL nutzt ein eigenes persistentes Volume.

### DSM-Firewall für die Docker-Netze prüfen

Wenn `db` als gesund angezeigt wird, `app` beim Start aber `psycopg.errors.ConnectionTimeout` meldet, prüfe den Verbindungsweg zwischen den Containern. Der DB-Healthcheck prüft nur `127.0.0.1:5432` innerhalb des DB-Containers. Solange die App nicht gesund ist, startet Compose den Caddy-Proxy nicht. Der DSM-Reverse-Proxy kann dann mit `502 Bad Gateway` antworten.

Docker kann nach dem Löschen und Neuerstellen der Projekt-Netze andere Subnetze zuweisen. Prüfe die tatsächlichen Subnetze und die IP-Adresse des DB-Containers nach dem ersten Startversuch.

```bash
sudo docker network inspect kostbar_database kostbar_backend \
  --format '{{.Name}} {{range .IPAM.Config}}{{.Subnet}} {{end}}| {{range .Containers}}{{.Name}}={{.IPv4Address}} {{end}}'
```

Solange die Datenbank läuft, kannst du den Zugriff mit einem kurzlebigen Container aus dem App-Image testen, auch wenn `app` fortlaufend neu startet. Der Test verwendet dieselben Docker-Netze und DB-Zugangsdaten wie der App-Dienst und gibt kein Passwort aus.

```bash
sudo docker compose -p kostbar run --rm --no-deps -T --entrypoint python app - <<'PY'
import os
import socket

import psycopg

host = os.environ["PGHOST"]
print("Docker-DNS:", host, "->", socket.gethostbyname(host), flush=True)

with socket.create_connection((host, 5432), timeout=5) as connection:
    print("TCP OK:", connection.getsockname()[0], "->", connection.getpeername(), flush=True)

with psycopg.connect(connect_timeout=5) as connection:
    print("PostgreSQL OK:", connection.execute(
        "SELECT current_user, current_database()"
    ).fetchone())
PY
```

Löst `db` auf die IP des DB-Containers auf und tritt vor `TCP OK` ein Timeout auf, prüfe zuerst in DSM unter **Systemsteuerung → Sicherheit → Firewall → Regeln bearbeiten** das aktive Profil. Falls die Firewall den Verkehr blockiert, setze unter **Alle Schnittstellen** zwei gezielte Erlaubnisregeln oberhalb der passenden Verweigerungsregel. Verwende für die Quellen die aktuell ermittelten Docker-Subnetze. [Synology-Dokumentation zur Firewall](https://kb.synology.com/en-global/DSM/help/DSM/AdminCenter/connection_security_firewall)

| Verbindung | Zielport (TCP) | Quelle |
| --- | --- | --- |
| App → PostgreSQL | `5432` | Subnetz aus `kostbar_database` |
| Caddy → App | `8765` | Subnetz aus `kostbar_backend` |

Beispiel für einen Neuaufbau, bei dem Docker `192.168.112.0/20` für `kostbar_database` und `192.168.128.0/20` für `kostbar_backend` zuweist. In DSM entspricht `/20` der Subnetzmaske `255.255.240.0`. PostgreSQL bleibt im internen Docker-Netz. Die Regeln betreffen den Verkehr zwischen den Containern und erfordern keine Portfreigabe am NAS.

Wiederhole nach dem Anwenden der Regeln den Test. Sobald er `PostgreSQL OK` meldet, starte den vorhandenen App-Container direkt über Docker neu und setze den Compose-Start fort. Verwende bei abweichendem Projektnamen den tatsächlichen App-Containernamen aus `docker compose ps -a`. Wenn Compose den App-Container noch nicht angelegt hat, beginne mit `docker compose -p kostbar up -d`.

```bash
sudo docker restart kostbar-app-1 &&
sudo docker compose -p kostbar up -d &&
sudo docker compose -p kostbar ps -a
```

Prüfe anschließend das Schema und `/healthz` wie oben beschrieben. Wenn `TCP OK` erscheint, PostgreSQL aber die Anmeldung ablehnt, prüfe die Zugangsdaten der bestehenden Instanz. Bleibt der TCP-Timeout bestehen, verwende die Ausgabe von `docker network inspect` und des Testcontainers zur weiteren Fehlersuche.

### Weitere Startprobleme

```bash
sudo docker compose -p kostbar logs --tail=80 db app proxy
```

Ein **403** bei passender DSM-Regel deutet auf den Proxy-Schlüssel hin. Ein **503** nur beim Admin-Login deutet auf den fehlenden Client-IP-Header hin.

## 4. Super-Admin und Terminals

```bash
sudo docker compose -p kostbar exec app python server.py set-super-admin kassenadmin
```

Das Kennwort wird verdeckt abgefragt. Danach `https://kostbar.example.org/admin` öffnen. Die Paketinstallation im PSK-WLAN und die Umstellung auf WPA2-Enterprise mit PEAP/MSCHAPv2 nach der [Terminal-Anleitung](../docs/TERMINALS.md) durchführen. Den gemeinsamen Ordner `pi/` aus dem Hauptverzeichnis und das passende Geräteprofil übertragen. Das bei der Installation erzeugte Profil für A liegt in `Synology/config/terminal-a.json`. In **Verkauf → Verkaufspunkte** kannst du weitere Standorte anlegen und das jeweilige Profil herunterladen. Aus dem produktiven WLAN müssen der DNS-Name und der DSM-Reverse-Proxy auf TCP **443** erreichbar sein.

Bei einem öffentlich vertrauenswürdigen DSM-Zertifikat nutzen die Pi-Profile den System-Vertrauensspeicher (`ca_file: null`). HTTPS endet am DSM Reverse Proxy. Bei eigener CA schon bei der Erstkonfiguration `--reader-ca` setzen und die verifizierte öffentliche CA-Datei als zweites Installer-Argument übergeben. In einer bestehenden Konfiguration kannst du `reader_ca_file` in `config/server.json` auf `/etc/kaffeekasse-terminal/nas-root.crt` setzen. Danach im Synology-Unterordner `sudo docker compose -p kostbar up -d --no-deps --force-recreate app` mit dem tatsächlich verwendeten Projektnamen ausführen und das Profil neu aus der Verwaltung laden. Auf dem Admin-PC muss die CA ebenfalls vertrauenswürdig sein.

Auf dem eingerichteten Pi ohne eigene CA:

```bash
sudo -u kaffeekasse -- curl -fsS --max-time 10 https://kostbar.example.org/healthz
```

Mit eigener CA stattdessen:

```bash
sudo -u kaffeekasse -- curl -fsS --max-time 10 \
  --cacert /etc/kaffeekasse-terminal/nas-root.crt \
  https://kostbar.example.org/healthz
```

Den Test mit dem Dienstkonto ausführen; das Terminal-Verzeichnis bleibt geschützt. Abschließend [Betrieb und Abnahme](../docs/BETRIEB.md) durchführen.
