# KoSTbar 40.1.0 · Release Notes

Vergleich mit dem öffentlichen main-Stand v38.0.1 (ba8bc6a). Die Änderungen umfassen den importierten Stand v40.0.2 und alle darauf folgenden Anpassungen. Zur Abnahme steht 40.1.0-rc.3 bereit.

## Neu in 40.1.0-rc.3

- Das Kassenbuch kann Einkäufe, Zahlungen und Saldenkorrekturen mit einer verknüpften Gegenbuchung stornieren. PayPal-Zahlungen behalten ihre Transaktionsreferenz.
- Die Produktanlage und -bearbeitung bieten 32 Bilder mit einer Vorschaukachel. Die Reihenfolge lässt sich je Terminal-Kategorie im Sortiment ändern. Das Terminal zeigt Kalt- und Heißgetränke zusammen an. Die Sammelkarte zählt weiterhin nur Heißgetränke. „Süßes“ und „Schokoladiges“ stehen als getrennte Kategorien bereit.
- Die Startseite zeigt das NFC Forum N-Mark und einen Pfeil zum Kartenleser. Das Betragsformular schaltet Formularvorschläge ab. Die Abmeldezeiten betragen 20 Sekunden bei Inaktivität, 10 Sekunden nach einem Kauf und 8 Sekunden nach einer Barzahlung.
- Der NAS-Host kann die Saldenliste täglich um 23 Uhr als XLSX sichern und alte Exportdateien nach 90 Tagen bereinigen. Der [Update-Leitfaden](docs/UPDATE-RC3.md) enthält Befehle für QNAP und Synology.
- Schema-Migration 8 übernimmt die bestehende Reihenfolge und ordnet bekannte Schokoladenprodukte und Produktsymbole zu. Das NFC-Zeichen stammt aus [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:NFC_logo.svg), SVG von Eg0rk0t323 unter CC0 1.0. Das N-Mark ist ein Kennzeichen des NFC Forum.

## Verwaltung und API

- Admins können Konten mit vierstelliger Start-PIN anlegen. Beim Erstlogin akzeptiert die Person die Nutzungsbedingungen, bestätigt die Kenntnisnahme der Datenschutzerklärung, ordnet eine freie NFC-Karte zu und bestätigt eine neue PIN. Bei einem Konto ohne Karte kann die Verwaltung eine neue Start-PIN vergeben.
- Die Benutzerliste sucht und sortiert serverseitig und lädt bis zu 50 Konten je Seite. Nachname, Vorname, Referat und Saldo sind sortierbar. Kontonummer, Anlagezeitpunkt, Kartenträger und erkannter Typ stehen unter **Kontodetails**. Der Gesamtexport umfasst alle Konten.
- Das Kassenbuch blendet Stornos standardmäßig aus. Der Storno-Filter greift vor der Paginierung. Die ursprünglichen Buchungen bleiben mit ihren Stornoverweisen sichtbar. Die Kontoauswahl lädt Suchergebnisse seitenweise. Konto, Verkaufspunkt und Storno-Filter stehen zusammen.
- Die Verwaltung lädt Konten, Sortiment, PayPal-Daten und weitere Inhalte je nach Ansicht. Kennzahlen und Ansichten nutzen getrennte API-Endpunkte. Der vollständige Verwaltungsüberblick bleibt für bestehende API-Aufrufer verfügbar.
- Die Terminal-Vorschau läuft in einem Bildschirmrahmen mit 1280 × 800 CSS-Pixeln. Auf kleineren Browserfenstern wird sie proportional verkleinert. Käufe, Sammelkarten und Zahlungen lassen sich mit Testdaten simulieren.
- **Technik** zeigt HTTP-Statuscodes als Legende. Beide Dokumenteditoren verwenden **Standdatum**. Der Abmeldebutton der Verwaltung verwendet dieselbe Farbgebung wie am Terminal.

## Terminal und Hinweise

- Die PIN-Anmeldung liefert nach erfolgreicher Prüfung das Sortiment mit. Suchtreffer haben mehr Abstand zum Eingabefeld. Dialoge haben einen eigenen Kopfbereich und scrollbaren Inhalt. Im PayPal-Dialog stehen Betragseingabe und QR-Code bei ausreichender Breite nebeneinander.
- Nutzungsbedingungen und Datenschutzerklärung öffnen sich breiter. **Projekt und Lizenz** ist in den Nutzungshinweisen und über die Fußzeile erreichbar. Beide Ansichten laden dieselbe MIT-Lizenz lokal und zeigen sie in Absätzen. Der Druckexport enthält den Projektverweis mit eingebettetem QR-Code.

## Raspberry Pi und Betrieb

- Der Installer startet eine eigene labwc-Kiosksitzung unter einem unprivilegierten Konto. Chromium beschränkt Navigation und Browserfunktionen. Wartung und NFC-Leserdienst verwenden getrennte Konten. Der Mauszeiger ist ausgeblendet, Touch-Eingaben erfolgen nativ. Kopplung, Browserprofil, Skalierung und Touch-Zuordnungen werden beim Update übernommen.
- Die Terminal-Anleitung beschreibt WPA2-Enterprise mit PEAP/MSCHAPv2, getrennten RADIUS-Gerätekonten und Prüfung des Serverzertifikats. Beim Update werden passende alte Standardhinweise einmalig aktualisiert.
- Das Backend trennt Admin-Schreibvorgänge, Eingabeprüfung und Dokumentverwaltung. Kontosperren, Kontoschließungen und PIN-Resets beenden Kiosksitzungen nach erfolgreichem Datenbank-Commit.
- Schema-Migration 7 ermöglicht Konten ohne Karte und kennzeichnet Start-PINs als vorläufig. Ein Rückweg zu einer App mit Schema 6 benötigt den Datenbankstand vor der Migration. [Update, Abnahme und Rückweg](docs/UPDATE-v40.1.md)
