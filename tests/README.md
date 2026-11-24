# Funktionale Tests

Die Suite verwendet ausschließlich synthetische Testdaten. Produktivdaten, `.env`, Geräteprofile und Caddy-Volumes werden nicht benötigt.

## Schnelle Python-Regressionstests

Im gemeinsamen Hauptordner (oberhalb von QNAP/ und Synology/) mit Python 3.12 oder 3.13 ausführen:

```sh
python -m unittest discover -s tests -v
```

Ohne `KOSTBAR_TEST_DSN` werden die PostgreSQL-Integrationstests ausdrücklich als übersprungen angezeigt. Die schnellen Tests benötigen nur die Python-Standardbibliothek. Der Installer-Pfadtest benötigt Linux und Bash. Er führt den lesenden Vorprüfungsabschnitt des Installers in einem temporären Verzeichnis aus. Weitere Tests prüfen die Übernahme von Skalierung, Touch-Zuordnung und Kalibrierung in die dedizierte Kiosksitzung sowie die erzeugten Chromium-Richtlinien für die unterstützten NAS-Adressen. Die Abnahme des Starts unter LightDM und labwc erfolgt auf dem Raspberry Pi.

## JavaScript-Verhalten

Mit Node.js 22 oder 24:

```sh
node --test tests/frontend.test.mjs
```

Die Tests prüfen die PIN-Felder und ihre Zifferntastatur. Sie führen Timer-, Aktivitäts- und Dialogfunktionen in einer kontrollierten Umgebung aus. Sie prüfen auch den Lizenzdialog in der gemeinsamen Fußzeile und die Rücklinks der öffentlichen Dokumentseiten. Die Darstellung, den lokalen Lizenzabruf und Eingaben am echten Touchscreen im Rahmen der [Terminal-Abnahme](../docs/TERMINALS.md#6-am-echten-display-abnehmen) prüfen.

## PostgreSQL und vollständige Python-Suite

Der folgende Compose-Stack erzeugt eine eigene PostgreSQL-17-Testinstanz ohne veröffentlichte Ports. Ihre Daten liegen ausschließlich im temporären Dateisystem des Testcontainers. Es werden keine Produktiv-Volumes eingebunden. Immer den eigenen Projektnamen und die separate Compose-Datei wie angegeben verwenden.

```sh
docker compose -p kostbar-tests -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from tests
docker compose -p kostbar-tests -f docker-compose.test.yml down
```

Erwartet werden erfolgreiche Tests ohne übersprungene PostgreSQL- oder Installer-Tests. Für den ersten Build werden die in den Dockerfiles angegebenen Images und Python-Pakete benötigt.

Die Integrationstests akzeptieren nur eine eigens vorgesehene Datenbank mit dem Namen `kostbar_test*`. Jeder Test erzeugt ein zufälliges eigenes Schema und entfernt anschließend ausschließlich dieses Schema. Die Tests prüfen insbesondere:

- frische Installation und unveränderten wiederholten Start;
- unversioniertes v35-Schema mit Salden, PIN-Prüfwert und Terminalkopplung;
- Ablehnung inkompatibler Spalten, neuerer Schemata und veränderter Migrationsprüfsummen;
- erfolgreiche spätere `ALTER TABLE`-Migration und vollständigen Rollback einer fehlerhaften Migration;
- Wiederholungen von Käufen, Barzahlungen und Admin-Buchungen;
- Registrierung mit PIN, Anmeldung ohne Ausweis, Admin-Reset, Neuvergabe nach Kartenanmeldung und Sperre nach fünf Fehlversuchen;
- Saldoerhalt bei der 90-Tage-Bereinigung und Löschung ausgeglichener geschlossener Konten.

Der Teststack wird separat von KoSTbar betrieben. Die normale Produktivinstallation startet keine Tests.

## Konfiguration und Monatsberichte

Die Konfigurationstests führen den echten Generator in privaten temporären Verzeichnissen aus: QNAP-IP/Port, Synology-Host-Header, getrennte Profile, eigene Tokens, Wahl der Umgebung und Schutz vor Überschreiben. Berichtstests prüfen historische Namen und die Kennzeichnung unbekannter Altdaten.

Die PostgreSQL-Suite prüft zusätzlich Umbenennungen innerhalb eines Monats und zwischen Monaten, einen Storno über die Berliner Monatsgrenze nach Umbenennung und Ausblenden, Namens-Erhalt nach der Buchungsbereinigung sowie die Datenaufbereitung für historische Statistiken mit rekonstruierbaren und bereits gelöschten Details. Diese Tests werden ohne Testdatenbank sichtbar übersprungen.

Die produktiven Compose-Dateien lassen sich ohne laufenden Docker-Daemon im jeweiligen NAS-Unterordner mit `docker compose -p kostbar config --quiet` prüfen, nachdem die jeweilige Konfiguration erzeugt wurde. Die Test-Compose-Datei wird immer aus dem Hauptordner gestartet und verwendet keine produktiven Zugangsdaten.

## Fehlerkorrekturen in v30

Der HTTP-Test prüft den während der Beleganzeige wiederholten Checkout. Dieselben Positionen in anderer Reihenfolge ergeben den ursprünglichen Beleg. Abweichende Artikel, Mengen und Preise werden abgewiesen. Der JavaScript-Test prüft die Felder der Statusanfrage für Archivieren und Reaktivieren.

Die PostgreSQL-Suite prüft zusätzlich, ob nach einer Produktänderung die Belegwiederholung genau einen Journaleintrag und die Monatssumme eines einzelnen Kaufs ergibt. Sie prüft auch, ob der Statuswechsel durch einen zweiten Admin die aktuellen Produktdaten, die Standortzuordnung und die historischen Artikelpositionen erhält.

## Kassenbuch und persönlicher Verlauf in v31

Die lokalen SQL-Tests prüfen den Sammelabruf mit 51 Einträgen für eine Person. Sie kontrollieren die Abfragezahl, Seitenwechsel bei identischen Zeitstempeln, Personen- und Standortfilter, Zahlungsarten und die Zuordnung eines Stornos zu einem Kauf auf einer anderen Seite. Der Frontend-Test prüft die gemeinsame Anzeige von Artikel, Grund und Kaufverweis.

Die PostgreSQL-Suite erweitert den Stornotest um den tatsächlichen Ablauf der ursprünglichen Kaufdetails nach 90 Tagen. Solange der jüngere Storno vorliegt, sind Betrag und Grund sichtbar. Die Tests prüfen außerdem den Saldo und den historischen Artikelnamen in der Monatsstatistik.

Die Tests prüfen auch den Storno-Filter vor der Kassenbuch-Paginierung. Die PostgreSQL-Suite kontrolliert die globale Suche und Sortierung der Benutzerliste über mehrere Seiten, die Kontoauswahl und Kennzahlen über alle Konten. Der Frontend-Test prüft, welche Abrufe die jeweilige Ansicht auslöst und wie verspätete Suchantworten behandelt werden.

## Datenbereinigung und Parallelbetrieb in v32

Der lokale HTTP-Test hält den Hintergrundlauf an und prüft die Antwort von `/healthz`. Ein zweiter Test prüft die Wiederholung nach einem Fehler sowie den Status nach der Erholung. Der Frontend-Test deckt die Anzeige unter **Technik** ab.

Die PostgreSQL-Suite hält den ersten Bereinigungslauf vor dem Commit an. Beide Terminals melden sich mit derselben Testkarte an und buchen nacheinander, während die Bereinigungstransaktion offen ist. Der Lauf wird danach gezielt zurückgerollt. Die Tests prüfen beim Wiederholen den Saldo, die einzelnen Buchungen und die Monatssummen. Weitere Fälle prüfen den Einzelkontoexport während eines Rückstands und den erhaltenen PayPal-Dublettenprüfwert.

## Verkaufspunkte und Parallelbetrieb in v33

Der Konfigurationstest deckt einen Erststandort und den optionalen zweiten Standort ab. Ein PostgreSQL-Test legt einen weiteren Standort an und prüft Profil, Kopplung und Verhalten nach dem Neustart. Der Parallelitätstest hält gleichzeitig einen Admin-Export und Terminal A an. Terminal B muss währenddessen antworten. Ein weiterer PostgreSQL-Test startet Käufe für dasselbe Konto an zwei Terminals parallel und prüft, dass zuerst der offene Beleg bestätigt werden muss und am Ende beide Käufe genau einmal im Saldo stehen. Die JavaScript-Suite prüft unter anderem, dass Antworten abgelaufener Besuche den Kiosk-Zustand nicht wiederherstellen.


## Sammelkarte in v34

Die PostgreSQL-Tests decken mehrere Heißgetränke pro Warenkorb, Nullbuchungen, kostenlose Artikel in Buchungsverlauf und Kontoauszug, Stornos und den Erhalt des Kartenstands nach der 90-Tage-Bereinigung ab. Für die Admin-Anzeige prüfen die Tests beide Zähler und das Herausrechnen von Stornos. Die Prüfung am physischen Touchscreen erfolgt bei der Erstabnahme.

## Verwaltung und Vorschau in v36

Die PostgreSQL-Tests prüfen die Rollenrechte für Verkaufspunkte und den PayPal-Empfänger. Sie decken das Löschen eines gekoppelten Standorts mit weiter nutzbarer Historie, den PayPal-Wechsel bei offenen Meldungen und die Fortsetzung einer v35-Datenbank mit den neuen Migrationen ab. Die Preisabfrage der Terminal-Vorschau ermittelt einen Gratisartikel für einen simulierten Kartenstand und hinterlässt weder Buchung noch Karte noch produktive Terminalsitzung.
