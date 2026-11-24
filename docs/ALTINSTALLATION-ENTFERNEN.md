# KoSTbar-Altinstallation vom NAS entfernen

Diese Anleitung gilt für **Synology mit Container Manager** und **QNAP mit Container Station**. Sie entfernt eine Altinstanz für eine [v40-Neuinstallation mit leerer Datenbank](../README.md#neuinstallation). Bei mehreren Altinstanzen führst du die Schritte für jeden bestätigten Compose-Projektnamen einzeln aus.

**Das Entfernen des PostgreSQL-Volumes löscht die alte Datenbank endgültig.** Dazu gehören Benutzerkonten, Salden, Buchungen, Einstellungen und Terminalkopplungen. Falls du den Datenstand noch brauchst, [sichere ihn vorab](BETRIEB.md#sicherung-und-wiederherstellung). Für einen leeren Neustart importierst du die Sicherung nicht.

## 1. Projektnamen und Arbeitsordner ablesen

Führe die Befehle per SSH auf dem NAS aus. Bei einer Root-Sitzung kannst du `sudo` weglassen. Kopiere jeweils den Inhalt des Codeblocks ohne die Eingabeaufforderung der Shell.

```sh
sudo docker ps -a --format 'table {{.Names}}\t{{.Label "com.docker.compose.project"}}\t{{.Image}}'
sudo docker volume ls --format 'table {{.Name}}\t{{.Label "com.docker.compose.project"}}'
sudo docker network ls --format 'table {{.Name}}\t{{.Label "com.docker.compose.project"}}'
```

Verwende den exakten Wert aus der Spalte `project` der zugehörigen Container. Beispielsweise gehören `kostbar-app-1`, `kostbar-db-1` und `kostbar-proxy-1` mit dem Label `kostbar` zum Projekt `kostbar`. Der Hostname `kostbar.example.org` und ein Verzeichnisname wie `kostbar-v35` ändern dieses Label nicht.

Im folgenden Beispiel lautet das Projektlabel `kostbar`. Passe den Wert vor der Ausführung an, falls deine Ausgabe einen anderen Projektnamen zeigt.

```sh
old_project='kostbar'
sudo docker ps -a --filter "label=com.docker.compose.project=$old_project" --format '{{.Names}}'
```

Zeigt der Befehl keine Container, gleiche das Label erneut mit der unfiltrierten Liste ab. Eine leere Liste für `coffee` sagt beispielsweise nichts über die laufende Instanz `kostbar` aus. Wenn die Container tatsächlich schon entfernt wurden, prüfe die Volumes und Netzwerke für das belegte Projektlabel und verwende den manuellen Weg in Schritt 2.

Erfasse vor dem Abbau den bisherigen Arbeitsordner, die Compose-Dateien, die Images und die Mounts. Die Abfrage gibt keine Umgebungsvariablen der Container aus.

```sh
for container in $(sudo docker ps -aq --filter "label=com.docker.compose.project=$old_project"); do
  sudo docker inspect --format '{{.Name}} | Image={{.Config.Image}} | Projektordner={{index .Config.Labels "com.docker.compose.project.working_dir"}} | Compose-Dateien={{index .Config.Labels "com.docker.compose.project.config_files"}}{{range .Mounts}}{{printf "\n  Typ=%s" .Type}}{{if .Name}}{{printf " Name=%q" .Name}}{{end}}{{printf " Quelle=%q Ziel=%q" .Source .Destination}}{{end}}' "$container"
done
```

- Bei `Typ=volume` ist `Name` der Docker-Volume-Name. Bei v35 mit Projekt `kostbar` sind das `kostbar_pgdata`, `kostbar_caddy_data` und `kostbar_caddy_config`. Ein langer Name ohne Projektlabel belegt die Zugehörigkeit zu KoSTbar nicht. Halte für anonyme Volumes die Verbindung zum konkreten Container über dessen Mounts fest.
- Bei `Typ=bind` ist `Quelle` der Dateipfad auf dem NAS. Halte auch ausschließlich von KoSTbar verwendete Pfade außerhalb des Projektordners fest. Docker entfernt beim Abbau keine Bind-Mount-Dateien.
- Prüfe, ob weitere alte Projektlabels, Datenpfade oder Projekte in der NAS-Oberfläche auftauchen. Ein PostgreSQL- oder Caddy-Image allein reicht für die Zuordnung zu KoSTbar nicht.

## 2. Container, Volumes und Netzwerke abbauen

Prüfe, ob ein alter DSM-Aufgabenplaner-Job oder eine vergleichbare Automatisierung die Altinstanz erneut starten würde. Deaktiviere den zugehörigen Job vor dem Abbau.

### Mit den ursprünglichen Compose-Dateien

Ab v35 liegt `docker-compose.yml` im Verzeichnis `Synology/` bzw. `QNAP/`. Ein Fehler wie `stat …/kostbar-v35/docker-compose.yml: no such file or directory` zeigt, dass am angegebenen Pfad keine Compose-Datei liegt. Verwende `Projektordner` und `Compose-Dateien` aus Schritt 1. Übernimm bei mehreren Dateien alle ursprünglichen `-f`-Argumente in derselben Reihenfolge und gegebenenfalls die bisher verwendete Option `--env-file`.

Beispiel für v35 auf Synology mit dem Projektlabel `kostbar` und dem Arbeitsordner `/volume1/docker/kostbar-v35/Synology`. Passe den Pfad an deine Ausgabe an.

```sh
old_dir='/volume1/docker/kostbar-v35/Synology'
(
  cd "$old_dir" &&
  sudo docker compose -p "$old_project" -f docker-compose.yml config --quiet &&
  sudo docker compose -p "$old_project" -f docker-compose.yml ps -a
)
```

Für dieses Beispiel muss `ps -a` die drei Altcontainer `kostbar-app-1`, `kostbar-db-1` und `kostbar-proxy-1` anzeigen. `config --quiet` prüft die Datei und ihre Konfiguration. Eine leere Containerliste nach erfolgreicher Konfigurationsprüfung ist kein Nachweis dafür, dass die Altinstanz entfernt wurde. Wenn die direkte Docker-Liste und die Compose-Liste nicht übereinstimmen, prüfe Projektname, Arbeitsordner und Compose-Dateien. Fehlt die ursprüngliche Konfiguration oder wurde sie verändert, kannst du bestätigte Ressourcen manuell entfernen.

Wenn die Ausgabe zur Altinstanz passt und du die zugehörigen Daten endgültig löschen willst, führe aus:

```sh
(
  cd "$old_dir" &&
  sudo docker compose -p "$old_project" -f docker-compose.yml down --volumes
)
```

Falls nur `docker-compose` verfügbar ist, verwende es in beiden Blöcken. `down --volumes` entfernt die Compose-Container, die zugehörigen projektinternen Netzwerke, die im Compose-Projekt definierten nicht externen Volumes sowie die an den entfernten Containern hängenden anonymen Volumes. Wähle den manuellen Weg, wenn die alte Konfiguration Ressourcen enthält, die auch andere Projekte benötigen. Externe Ressourcen und alte Container aus anderen Compose-Konfigurationen prüfst du separat. [Docker-Referenz zu compose down](https://docs.docker.com/reference/cli/docker/compose/down/)

### Ohne nutzbare Compose-Dateien oder bei Resten

Entferne gezielt die in Schritt 1 bestätigten Container. `docker rm -v` entfernt dabei auch ihre anonymen Volumes, soweit Docker sie freigeben kann. Prüfe deren Mount-Zuordnung vorab. Im Synology-Beispiel wäre der manuelle Ersatz für `down`:

```sh
sudo docker stop kostbar-proxy-1 kostbar-app-1 kostbar-db-1 &&
sudo docker rm -v kostbar-proxy-1 kostbar-app-1 kostbar-db-1
```

Wiederhole die drei Abfragen aus Schritt 5. Für verbleibende Volumes und Netzwerke die Verbraucher sowie die Verwendung durch andere Deployments prüfen. Ersetze die Beispielnamen durch die tatsächlich vorhandenen und KoSTbar zugeordneten Ressourcen.

```sh
sudo docker ps -a --filter 'volume=kostbar_pgdata'
sudo docker network inspect kostbar_database --format '{{json .Containers}}'
```

Wenn ihre Zuordnung eindeutig ist und sie ausschließlich zur entfernten KoSTbar-Instanz gehörten, lösche sie einzeln per exaktem Namen. Beispiel für zwei mögliche Reste:

```sh
sudo docker volume rm kostbar_pgdata
sudo docker network rm kostbar_database
```

Bei `volume is in use` oder `has active endpoints` den gemeldeten Verbraucher nachsehen und zuerst dessen Zugehörigkeit klären. Ohne Beleg bleiben alte Volumes ohne Projektlabel bestehen. Ein globales `docker system prune`, `docker volume prune` oder `docker network prune` greift auch auf Ressourcen anderer Projekte zu. [Docker-Referenz zu container rm](https://docs.docker.com/reference/cli/docker/container/rm/)

## 3. Alte Images finden und gezielt entfernen

Nach dem Abbau der Container alle lokalen Tags prüfen. Frühere Installationen können beispielsweise Compose-generierte App- und Test-Image-Namen gehabt haben. Die Suche liefert Kandidaten. Bestätige sie anhand der alten Compose-Dateien, Build-Befehle oder der vorab erfassten Image-Referenzen.

```sh
sudo docker image ls --format '{{.Repository}}:{{.Tag}} {{.ID}}'
```

Entferne jedes bestätigte, nicht mehr benötigte Image einzeln per exakter Referenz. Beispiel für v35:

```sh
sudo docker image inspect --format '{{.Id}} {{json .RepoTags}}' kostbar-app:35.0.0
sudo docker ps -a --filter 'ancestor=kostbar-app:35.0.0' --format '{{.Names}}'
```

Wenn die Containerliste leer ist und der Tag auch für kein geplantes Deployment oder Rollback benötigt wird:

```sh
sudo docker image rm kostbar-app:35.0.0
```

Wenn eine Image-ID mehrere Tags hat, prüfe jeden Tag separat. Ein ungetaggtes Image (`<none>`) erst entfernen, wenn seine Herkunft und fehlende Nutzung belegt sind. Für `postgres:17-bookworm` und `caddy:2-alpine` gilt dieselbe Verbraucherprüfung, falls du die Tags ebenfalls entfernen willst. Für eine Neuinstallation werden beide Basis-Images benötigt. Das aktuelle App-Image steht in der [Anleitung zum Image-Build](../README.md#app-image-bereitstellen). [Docker-Referenz zu image rm](https://docs.docker.com/reference/cli/docker/image/rm/)

## 4. Alte Dateien und NAS-Einstellungen bereinigen

1. Prüfe in **Container Manager → Projekt** (Synology) bzw. in **Container Station → Anwendungen** (QNAP), ob der Altstand noch einen eigenen Projekteintrag hat. Entferne den eindeutig bestätigten Alt-Eintrag vor dem Anlegen der neuen Instanz. [Synology Container Manager](https://kb.synology.com/en-global/DSM/help/ContainerManager/docker_project) · [QNAP Container Station](https://www.qnap.com/de-de/how-to/tutorial/article/wie-wird-container-station-3-verwendet)
2. Lösche in **File Station** den eindeutig zugeordneten alten Installationsordner. Im Synology-Beispiel ist das `/volume1/docker/kostbar-v35` mit dem Unterverzeichnis `Synology/`. Prüfe weitere alte KoSTbar-Verzeichnisse und separate KoSTbar-Bind-Mounts aus Schritt 1, etwa `.env`, `config/`, Geräteprofile und exportierte Zertifikate. Lösche in gemeinsamen Ordnern gezielt die ermittelten KoSTbar-Dateien. Bei aktivem Papierkorb kannst du die KoSTbar-Einträge dort separat entfernen. [Synology File Station](https://kb.synology.com/index.php/en-us/DSM/help/FileStation/delete?version=7)
3. Alte KoSTbar-ZIP-Dateien, Datenbankexporte, Sicherungen und Snapshots liegen gegebenenfalls außerhalb des Projektordners. Prüfe diese Kopien separat. Gemeinsame Sicherungen und Snapshots können auch andere Anwendungen enthalten.
4. Wenn die neue Synology-Instanz unter derselben Adresse erreichbar sein soll, kannst du DNS, DSM-Zertifikatszuordnung und Reverse-Proxy-Regel weiterverwenden. Mit der Beispielkonfiguration ist das DSM-Ziel `HTTP → 127.0.0.1:18765`. Ersetze vor dem Start den Wert des Anfrage-Headers `X-KoSTbar-Proxy-Key` durch den neuen `KASSE_DSM_PROXY_KEY` aus `Synology/.env`. Bei geändertem Hostnamen prüfe, welche alte KoSTbar-Regel entfallen kann. Für die weiteren Schritte siehe [Synology](../Synology/README.md#0-altinstallation-entfernen) bzw. [QNAP](../QNAP/README.md#0-altinstallation-entfernen).

## 5. Abschluss prüfen und v40 neu installieren

Verwende denselben bestätigten Projektnamen aus Schritt 1. Setze `old_project` erneut, wenn du zwischenzeitlich eine neue SSH-Sitzung geöffnet hast.

```sh
sudo docker ps -a --filter "label=com.docker.compose.project=$old_project" --format '{{.Names}}'
sudo docker volume ls --filter "label=com.docker.compose.project=$old_project" --format '{{.Name}}'
sudo docker network ls --filter "label=com.docker.compose.project=$old_project" --format '{{.Name}}'
```

Alle drei Abfragen sollten erfolgreich und ohne Treffer enden. Prüfe zusätzlich die zuvor identifizierten Ressourcen ohne Projektlabel, die alten App-Image-Tags und die Installationsordner. Im Synology-Beispiel sind das insbesondere `kostbar_pgdata`, `kostbar_caddy_data`, `kostbar_caddy_config` sowie `kostbar_backend`, `kostbar_database` und `kostbar_lan`.

Lege den aktuellen Quellstand in einem neuen, leeren Ordner ab, etwa `/volume1/docker/kostbar-neu`. Verwende diesen Pfad in der [Synology-Neuinstallation](../Synology/README.md#1-konfiguration-erzeugen) bzw. [QNAP-Neuinstallation](../QNAP/README.md). Du kannst das Compose-Projekt wieder `kostbar` nennen, sobald seine früheren Ressourcen entfernt sind. Erzeuge die Konfiguration frisch, stelle das aktuelle App-Image bereit und starte die neue Installation. PostgreSQL initialisiert ein neues Datenvolume. Prüfe `schema-status` und `/healthz` und richte den Super-Admin und die Terminalkopplungen mit den neu erzeugten Geräteprofilen ein.
