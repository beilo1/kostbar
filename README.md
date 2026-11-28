# KoSTbar

KoSTbar ist eine selbst gehostete Selbstbedienungskasse für den Pausenshop. Am Touchterminal melden sich Nutzer mit NFC-Karte oder PIN an, wählen Produkte und buchen den Einkauf auf ihr Kassenkonto. Das Kassen-Team verwaltet Sortiment, Zahlungen und Auswertungen im Browser.

![KoSTbar-Terminal Pausenküche mit Begrüßung „Hallo, Max“, Sammelkarte, Bezahlen, Saldo und Warenkorb](docs/images/frontend.png)

## Funktionen

- Anmeldung per NFC und optional per PIN, mit persönlichem Saldo und Buchungsverlauf
- Barzahlung auf Vertrauensbasis und optionale PayPal-Zahlung mit manueller Bestätigung
- Digitale Sammelkarte für Heißgetränke mit einem Gratisgetränk nach zehn Stempeln
- Mehrere Verkaufspunkte mit eigenem Sortiment und einer Terminal-Vorschau zum Simulieren von Einkäufen
- Verwaltung mit getrennten Admin-Rollen, manueller Benutzeranlage, Journal, Monatsauswertungen und Exporten

### Terminal vor der Anmeldung

![Startseite des KoSTbar-Terminals Pausenküche mit Kartenanmeldung und PIN-Option](docs/images/terminal-start.png)

### Sammelkarte am Terminal

![Geöffnete digitale Sammelkarte von Max mit sieben von zehn Stempeln](docs/images/sammelkarte.png)

### Verwaltung

#### Kassenbuch

![Kassenbuch der Pausenküche mit Käufen und Barzahlungen von Max Berger, Nora Winter und Theo Sommer](docs/images/backend.png)

#### Benutzerverwaltung

![Benutzerverwaltung für Max Berger, Nora Winter und Theo Sommer mit Salden, Sammelkarten und Kontoaktionen](docs/images/benutzerverwaltung.png)

Die Screenshots zeigen fiktive Beispieldaten. Die [Bedienungsanleitung](docs/BETRIEB.md#nutzungsbedingungen-und-abnahme) beschreibt die Benutzerliste, den Storno-Filter und den Dialog **Projekt und Lizenz**.

## Hardware

| Einsatz | Komponente | Referenzkonfiguration |
| --- | --- | --- |
| Zentraler Betrieb | Docker-fähiges NAS | QNAP TVS-872XT mit QTS 5.2.11.3683 Build 20261114 und Container Station oder Synology DS720+ mit DSM 7.4.1-90080 Update 2 und Container Manager |
| Je Terminal | Raspberry Pi 5 | Raspberry Pi OS 64-Bit mit Desktop, microSD-Karte (32 GB empfohlen), USB-C-Netzteil (27 W empfohlen) |
| Je Terminal | Touchdisplay | Raspberry Pi Touch Display 2, 10″, per DSI, im Querformat mit 1920 × 1200 Pixeln |
| Je Terminal | USB-NFC-Leser und Karten | ACS ACR1552U-M1 im PC/SC-Modus, mit kompatiblen NFC-Karten oder Anhängern |
| Optional je Terminal | Gehäuse und Halteschiene | 3D-gedruckter Standfuß und Displaygehäuse. Druckprofil und Montage stehen in der [Hardware-Anleitung](docs/HARDWARE.md). |

NAS, Terminals und der Admin-Rechner benötigen Netzwerkzugang, DNS und eine vertrauenswürdige HTTPS-Verbindung zum NAS. Die [Terminal-Anleitung](docs/TERMINALS.md) beschreibt auch WPA2-Enterprise mit PEAP/MSCHAPv2, RADIUS-Gerätekonten und Prüfung des RADIUS-Serverzertifikats.

![Fotorealistische Visualisierung des KoSTbar-Terminals Pausenküche mit limettengrünem 3D-Druck-Gehäuse und USB-NFC-Leser](docs/images/terminal-render.jpg)

*Visualisierung des 3D-gedruckten Terminalgehäuses mit der KoSTbar-Produktansicht.*

## Installation

Für eine bestehende Installation führt [Update auf v40.1.0-rc.3](docs/UPDATE-RC3.md) vom Patch über Sicherung und App-Wechsel bis zur Abnahme und Einrichtung des Saldenexports. Für eine Neuinstallation gelten die folgenden Schritte.

| | QNAP | Synology |
| --- | --- | --- |
| Anleitung | [QNAP einrichten](QNAP/README.md) | [Synology einrichten](Synology/README.md) |
| HTTPS | Caddy auf der NAS-LAN-IP mit eigener CA | DSM Reverse Proxy vor internem Caddy |
| Adresse | Vorgabe `https://kostbar.internal.lan:18443` | Eigene HTTPS-Adresse bei `--origin` |

### Neuinstallation

Verwende den Quellstand, zu dem diese Anleitung gehört. Für einen noch nicht gemergten Kandidaten den [Patch auf dem RC-Branch übernehmen](docs/UPDATE-RC3.md#1-änderungen-auf-dem-rc-branch-übernehmen) oder den veröffentlichten Refactoring-Branch auschecken. Wenn der Kandidat bereits in `main` gemergt ist, kannst du den entsprechenden Commit aus dem öffentlichen Repo verwenden. Vor dem Build den erwarteten Wert `40.1.0-rc.3` im Versionslabel des Dockerfiles und den ausgecheckten Commit prüfen.

1. Das [gemeinsame App-Image bauen](#app-image-bereitstellen).
2. Nach der passenden NAS-Anleitung eine neue Konfiguration erzeugen. Der Beispiel-Projektname für Docker Compose ist `kostbar`. Bei einer zusätzlichen Instanz einen eigenen Projektnamen sowie passende Bind-Adressen, Ports und Proxy-Ziele verwenden.
3. Den Verkaufspunkt koppeln und die [Erstabnahme](docs/BETRIEB.md#erstabnahme) durchführen. `schema-status` zeigt die Versionen **1 bis 7**, beginnend mit `v35_baseline`.
4. Vor der Freigabe die Datenschutzerklärung an die tatsächliche Umgebung anpassen und veröffentlichen. [`privacy.md`](privacy.md) ist die Ausgangsvorlage. Die [Betriebsanleitung](docs/BETRIEB.md) erläutert die Bearbeitung in der Verwaltung.

Weitere Terminals legst du als Super-Admin unter **Verkauf → Verkaufspunkte** an. Lade das jeweilige private Geräteprofil herunter, richte den Pi ein und bestätige dessen Kopplungscode. Produkte weist du unter **Sortiment** zu.

### App-Image bereitstellen

Beide Deployment-Varianten verwenden standardmäßig das gemeinsame Image `kostbar-app:40.1.0-rc.3`. Führe den Build im Hauptordner für die Architektur des Ziel-NAS aus. Für ein x86-64-NAS kann bei einem Build auf ARM beispielsweise `--platform linux/amd64` verwendet werden, sofern der Builder diese Zielplattform unterstützt.

```bash
docker build --pull -t kostbar-app:40.1.0-rc.3 .
docker image save -o kostbar-app-40.1.0-rc.3.tar kostbar-app:40.1.0-rc.3
```

Die Tar-Datei je Zielsystem einmal importieren. Für die Erstinstallation müssen auch `postgres:17-bookworm` und `caddy:2-alpine` lokal geladen oder erreichbar sein.

```bash
sudo docker image load -i kostbar-app-40.1.0-rc.3.tar
sudo docker image inspect kostbar-app:40.1.0-rc.3 --format '{{.Id}} {{.Os}}/{{.Architecture}}'
```

Alternativ die Image-Referenz einer Registry als `KOSTBAR_APP_IMAGE` in der jeweiligen `.env` setzen und im NAS-Unterordner `sudo docker compose -p kostbar pull app` ausführen. Eine Referenz mit Digest legt den Build eindeutig fest.

### Upgrade einer bestehenden Installation

Für den Wechsel von RC2 zu RC3 stehen Vorgehen, Abnahme und Rückweg in der [Update-Anleitung](docs/UPDATE-RC3.md). Für ältere Installationen dokumentiert die [RC2-Anleitung](docs/UPDATE-v40.1.md) den vorherigen NAS- und Pi-Wechsel.

Der Kandidat ergänzt Migration 7 (`manual_account_setup`) für manuell angelegte Konten. Für die Rückkehr zu einer App-Version mit Schema 6 wird der Datenbankstand vor dieser Migration benötigt. [NAS-Rückweg](docs/UPDATE-v40.1.md#nas-rückweg)

## Entwicklung und Lizenz

- [Release Notes für 40.1.0](RELEASE-NOTES.md)
- [Isolierte Python-, PostgreSQL- und JavaScript-Tests](tests/README.md)
- [Betrieb, Datensicherung und Abnahme](docs/BETRIEB.md)
- [MIT-Lizenz](LICENSE). Die mitgelieferten Schriften Fraunces und Plus Jakarta Sans stehen unter der [SIL Open Font License 1.1](licenses/fonts/).

Die Browser-Oberflächen liegen in `static/`, der Raspberry-Pi-Installer in `pi/`. `web.py` verarbeitet HTTP-Anfragen, `server.py` steuert die Abläufe. `admin_operations.py` bündelt Schreiboperationen der Verwaltung, `policy_documents.py` pflegt die veröffentlichten Dokumentfassungen, und `validation.py` enthält die gemeinsame Eingabeprüfung. `store.py` und `finance.py` kapseln PostgreSQL-Abfragen, Buchungslogik und Exporte.
