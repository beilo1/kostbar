# Funktionale Tests

Führe die Befehle im Hauptordner des Quellstands aus, den du prüfen möchtest. Dort liegen `docker-compose.test.yml`, `Dockerfile.tests` und `tests/`. Bei mehreren KoSTbar-Ordnern wähle den Quellordner des Release-Kandidaten, den du testen möchtest. Docker baut das Testimage aus genau diesem Ordner.

## Python und PostgreSQL auf Synology oder QNAP

Starte die vollständige Python-Suite mit Docker Compose. Der Testcontainer bringt Python 3.13 und die benötigten Pakete mit. Auf DSM kann `python` in der NAS-Shell auf Python 3.8 zeigen. Dort fehlen `zoneinfo` und die Unterstützung für die geklammerte `with`-Syntax der Tests.

```sh
docker compose -p kostbar-tests -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from tests
```

Füge bei Bedarf `sudo` vor `docker` ein. Der Teststack verwendet synthetische Daten in einer eigenen PostgreSQL-17-Instanz mit temporärem Speicher und internem Docker-Netz. Er benötigt weder produktive Zugangsdaten noch die Volumes der laufenden Installation. Beim ersten Build müssen die Basisimages und Python-Pakete verfügbar sein.

Ein erfolgreicher Lauf endet mit `OK` und Exit-Code 0. Im Testcontainer sollen auch die PostgreSQL-Integrationstests und der Installer-Pfadtest laufen. Räume das Testprojekt nach dem Lauf auch bei einem Fehler auf.

```sh
docker compose -p kostbar-tests -f docker-compose.test.yml down
```

## Schnelle Python-Tests ohne PostgreSQL

Wenn auf deinem Rechner Python 3.12 oder 3.13 installiert ist, kannst du die schnelle Suite direkt starten.

```sh
python --version
python -m unittest discover -s tests -v
```

Ohne `KOSTBAR_TEST_DSN` werden die PostgreSQL-Integrationstests als übersprungen angezeigt. Der lesende Vorprüfungstest für den Terminal-Installer benötigt Linux und Bash und wird unter Windows übersprungen. Falls dem System IANA-Zeitzonendaten fehlen, installiere `tzdata` in der verwendeten Python-Umgebung.

## Frontend-Tests

Verwende Node.js 22 oder 24.

```sh
node --test tests/frontend.test.mjs
```

Die Tests prüfen unter anderem PIN-Eingabe, Inaktivität und Dialoge am Kiosk, Beleganzeige und Sammelkarte sowie die Darstellung des Kassenbuchs. Die Darstellung und Bedienung am echten Touchscreen prüfst du bei der [Terminal-Abnahme](../docs/TERMINALS.md#6-am-echten-display-abnehmen).

## Testabdeckung

- **Datenbankmigrationen** prüfen Neuinstallationen, wiederholte Starts, die Übernahme von Bestandsdaten ohne Migrationshistorie, Prüfsummen und den Rollback bei Fehlern.
- **Konfiguration und Anmeldung** decken NAS-spezifische Einstellungen, Terminalprofile und Kopplung, Registrierung, manuell angelegte Konten, PIN-Anmeldung und PIN-Reset ab.
- **Buchungen und Verwaltung** prüfen wiederholte und parallele Käufe, Stornos, Barzahlungen, Sammelkarte, Rollenrechte, PayPal-Einstellungen und die Terminal-Vorschau.
- **Kiosk-Installer** prüft, wie die Kiosksitzung Skalierung und Touch-Kalibrierung übernimmt und welche Chromium-Richtlinien sie erhält.
- **Kassenbuch und Berichte** prüfen Filter, Seitenwechsel, historische Artikelnamen und den Saldoerhalt bei der Datenbereinigung.

Die PostgreSQL-Tests erwarten eine eigens vorgesehene Datenbank mit einem Namen, der mit `kostbar_test` beginnt. Jeder Test verwendet ein eigenes Schema, das er anschließend entfernt.
