# Betrieb, Abnahme und Sicherung

Alle folgenden NAS-Befehle im gewählten Unterordner **QNAP/** oder **Synology/** ausführen. Der Projektname ist wie bei der Einrichtung **kostbar** für Neuinstallationen. Bei einem Upgrade den bisherigen Compose-Projektnamen weiterverwenden. Bei eigenem Namen alle Befehle entsprechend anpassen.

## Historische Produktnamen

Monatsauswertungen verwenden die Bezeichnung beim Kauf, auch wenn ein Produkt später umbenannt, archiviert oder dauerhaft ausgeblendet wird. Bei mehreren Namen desselben Produkts innerhalb eines Monats erscheinen mehrere Zeilen. Stornos behalten den Kaufnamen und zählen weiterhin im Stornomonat. Die gespeicherten Monatswerte enthalten keine Personenzuordnung und überstehen die 90-Tage-Löschung der Einzelbuchungen. Kassenbuch, persönliche Buchungslisten und Einzelkontoexporte verwenden weiterhin die Artikel-Snapshots.

Neue Käufe speichern die Produktbezeichnung direkt. Umbenennungen ändern die in vergangenen Käufen gespeicherten Bezeichnungen nicht.

Nur der Super-Admin kann **Dauerhaft ausblenden** verwenden. Die Aktion entfernt das Produkt aus Sortiment, Terminals und regulärer Produktverwaltung. Datenbankzeile und Historie bleiben erhalten. Die Oberfläche bietet hierfür keine Wiederherstellung. Reguläre Admins können Produkte weiterhin anlegen, bearbeiten, archivieren und reaktivieren.

## Erstabnahme

1. NAS-Dienste und `/healthz` prüfen; `server.py schema-status` zeigt die Versionen 1 bis 6 und beginnt mit `v35_baseline`.
2. Super-Admin-Anmeldung testen und benötigte reguläre Admins anlegen. Sortiment und Standortzuordnung prüfen; Startprodukte werden den bei der Ersteinrichtung vorhandenen Verkaufspunkten zugeordnet.
3. An jedem eingerichteten Pi das produktive WPA-Enterprise-Profil, die erfolgreiche RADIUS-Anmeldung und den HTTPS-Healthcheck aus dem produktiven WLAN prüfen. Anschließend die Terminals koppeln und Kartenanmeldung, manuelle Anmeldung und Registrierung am Touchscreen testen.
4. Testkauf, Barzahlung und gegebenenfalls PayPal-Meldung mit Admin-Bestätigung prüfen. Saldo und Kassenbuch abgleichen.
5. Ein Testprodukt kaufen, umbenennen und erneut kaufen: In der Monatsauswertung bleiben beide Namen erhalten. Den alten Kauf stornieren und prüfen, dass das Storno unter dessen damaligem Namen erscheint.
6. Jeden eingerichteten Pi neu starten und die automatische RADIUS-Anmeldung per PEAP/MSCHAPv2, die Browseröffnung und den ausgeblendeten Mauszeiger schon vor der ersten Berührung prüfen. Rotation, Tastaturlayout, Start ohne Keyring-Dialog, Kopplung, 15 Sekunden Inaktivität und fünf Sekunden Kaufanzeige prüfen.
7. Nutzungshinweise und Datenschutz vervollständigen, Aushänge exportieren, Sicherung anlegen und Wiederherstellung in einer getrennten Testinstallation üben.

## Sammelkarte für Heißgetränke

- Nach der Anmeldung öffnet **Sammelkarte** neben **Saldo begleichen** den kontoweiten Stand. Jedes bezahlte Stück in der Kategorie **Heißgetränke** zählt. Nach zehn bezahlten Heißgetränken ist das nächste gratis, auch im selben Warenkorb. Alle Verkaufspunkte verwenden denselben Kartenstand.
- Die Einlösung ist automatisch. Benötigt der Warenkorb einen oder mehrere Rabatte, erhalten sie zuerst die günstigsten Heißgetränke. Bei gleichen Preisen entscheidet die Produktnummer. Die Kaufbestätigung nennt die Gratispositionen und den zu zahlenden Betrag. Im fünfsekündigen Kaufbeleg schwingt die Sammelkarte kurz ins Bild, und neue Stempel werden nacheinander aufgedrückt. Beim Einlösen zeigt die Karte den Einlösestempel und wechselt danach auf den aktuellen Stand. Die Terminal-Vorschau zeigt denselben Ablauf.
- Im persönlichen Verlauf, im Kassenbuch und im Excel-Kontoauszug stehen Gratispositionen mit **0,00 €**. Die Monatsauswertung erfasst ausgegebene Stückzahlen einschließlich Bonusgetränken und nur die tatsächlich berechneten Beträge als Umsatz.
- Ein vollständiges Storno erstattet den bezahlten Betrag und nimmt die zugehörige Sammelkartenänderung zurück. Wurde mit später stornierten Stempeln schon ein Bonus eingelöst, werden fehlende Stempel mit künftigen Käufen verrechnet. Eine spätere Nachbelastung erfolgt dabei nicht.
- Der Stand läuft nicht ab. Er bleibt als Zähler beim Konto gespeichert, unabhängig von der Löschung der Einzelbuchungen nach 90 Tagen. Beim Löschen des Kontos entfällt auch der Zähler. Beim Upgrade von v33 oder älter startet die Karte leer.

Unter **Benutzer → Sammelkarte** stehen der aktuelle Stempelstand und die Zahl der gültig eingelösten Gratisgetränke pro Konto. Das Storno eines Bonuskaufs reduziert den Zähler. Er bleibt bei der 90-Tage-Bereinigung erhalten und entfällt bei der Kontolöschung.

Für die Abnahme im isolierten Testsystem zehn Heißgetränke in einer Buchung kaufen, danach ein weiteres als Gratisgetränk beziehen und im Verlauf den Nullbetrag prüfen. Anschließend das Gratisgetränk stornieren und prüfen, dass der Bonus wieder verfügbar ist.

## Verwaltungszugänge

Der erste Super-Admin wird per NAS-Konsole angelegt. Der Super-Admin verwaltet weitere Admin-Konten im Backend. Nur er kann andere Administratoren anlegen, bearbeiten oder Kennwörter zurücksetzen. `set-admin NAME`, `set-super-admin NAME` und `remove-admin NAME` bleiben die Konsolenwege für Einrichtung und Wiederherstellung. Kennwörter werden verdeckt abgefragt. Kennwörter für Administratoren und Super-Admins benötigen mindestens zwölf Zeichen.

### Speicherung der Kartenkennungen

KoSTbar verarbeitet die ausgelesene Karten-UID mit **HMAC-SHA-256**. In `people.card` und in der Sperrliste `retired_cards.card` wird der daraus berechnete Prüfwert gespeichert. Bei erneutem Auflegen entsteht mit demselben Schlüssel derselbe Wert. Dadurch funktioniert die Anmeldung an allen Terminals mit dem gemeinsamen Konto.

Die Roh-UID wird während des Lesevorgangs im Arbeitsspeicher verarbeitet und vom Leserdienst über die zertifikatsgeprüfte HTTPS-Verbindung an das NAS übertragen. Auf Anwendungsebene wird sie weder in die Datenbank noch in das Änderungsprotokoll geschrieben. Auch die Kartenerfassung für einen Austausch hält serverseitig den HMAC-Wert. Die Browser-Antworten enthalten keine Roh-UID. Das Dienstprotokoll zeigt keine Roh-UID und die Leserprobe erzeugt eine nur für diesen Testlauf gültige maskierte Kennung.

Der gemeinsame HMAC-Schlüssel ist der zufällig erzeugte 32-Byte-Wert `card_key` in `config/server.json` auf dem NAS. Er muss für die Wiedererkennung verfügbar sein. Er gehört in ein administrativ geschütztes Verzeichnis und in das geschützte Konfigurationsbackup. Die Geräteprofile auf den Pis enthalten den Terminaltoken und den öffentlichen CA-Verweis. Der `card_key` wird in diese Profile nicht kopiert.

Die gespeicherten Kennungen sind mit den namentlichen Konten verknüpft. Die Anwendung verarbeitet daher weiterhin personenbezogene Daten. Die Hashbildung schützt die ursprüngliche Kartenkennung und ersetzt keine Festlegung von Zugriffsrechten, Zweck und Aufbewahrung. [DSGVO, insbesondere Erwägungsgrund 26 und Artikel 4](https://eur-lex.europa.eu/legal-content/DE/TXT/?uri=CELEX%3A32016R0679)

### Verschlüsselter Speicher auf dem NAS

Die Nutzungsbedingungen enthalten gemäß der vorgesehenen NAS-Konfiguration den Hinweis, dass die Datenhaltung auf verschlüsseltem Speicher erfolgt. Dafür muss der tatsächliche Speicherort der Datenbank auf dem NAS in die Verschlüsselung einbezogen sein.

Im mitgelieferten Compose-Projekt liegen die PostgreSQL-Daten im benannten Docker-Volume `pgdata`. Dessen Speicherort wird von Docker verwaltet. Ein verschlüsselter Projektordner allein belegt deshalb noch keine Verschlüsselung des Datenbankvolumes. Der tatsächlich verwendete Pfad lässt sich im Projektordner mit diesem lesenden Befehl anzeigen.

```bash
sudo docker inspect "$(sudo docker compose -p kostbar ps -q db)" --format '{{range .Mounts}}{{if eq .Destination "/var/lib/postgresql/data"}}{{.Source}}{{end}}{{end}}'
```

Wenn dieser Pfad und der Projektordner auf demselben vollständig verschlüsselten NAS-Volume liegen, sind Datenbank und Konfiguration im Ruhezustand abgedeckt. Sicherungen, Snapshots und Exporte an anderen Speicherorten separat prüfen. Nach dem Entsperren greifen berechtigte Dienste wie gewohnt auf die Daten zu. [Docker-Volumes](https://docs.docker.com/engine/storage/volumes/)

## Nutzungsbedingungen und Abnahme

- Die mitgelieferten Nutzungshinweise beschreiben die Ausweiskennung als HMAC-SHA-256-Prüfwert. Die Angabe zur NAS-Verschlüsselung mit der tatsächlichen Installation abgleichen.
- Der Abschnitt **Netzzugang der Terminals** beschreibt die PSK-Ersteinrichtung und den WLAN-Produktivbetrieb mit technischen RADIUS-Gerätekonten. Beim Upgrade ersetzt das Backend den früheren EAP-TLS-Standardtext in den Nutzungshinweisen durch den neuen Standardtext und ergänzt bei Bedarf den Hinweis zur RADIUS-Anmeldung in der Datenschutzerklärung. Wird dabei eine neue Fassung veröffentlicht, bestätigen registrierte Personen sie beim nächsten Zugriff.
- Der Footer verlinkt **Nutzungsbedingungen** und zeigt **© 2026 | beilo1**. Die Nutzungsbedingungen erläutern freiwillige Teilnahme, Barzahlung, lokale Datenhaltung, die Verarbeitung der Kartenkennung, verwendete Technik und die konfigurierten Kontaktdaten. Unter **Projekt und Lizenz** stehen der GitHub-Link, ein lokal ausgelieferter QR-Code und der lokal lesbare MIT-Lizenztext.
- Beim Registrieren sind Vorname, Nachname und Referat Pflichtfelder. Der Fokus liegt in **Vorname**. Die Bildschirmtastatur beginnt in jedem leeren Feld mit Großbuchstaben und wechselt nach dem ersten Buchstaben in Kleinbuchstaben. Über die gemeinsame Pflicht-Checkbox werden die Nutzungsbedingungen akzeptiert und die Kenntnisnahme der Datenschutzerklärung bestätigt. Das Backend prüft beide Fassungen. Unter **Benutzer → Zustimmung** steht **Bestätigt**, wenn beide aktuellen Fassungen bestätigt sind, sonst **Offen**. Die Datenbank speichert beide Versionskennungen, Zeitpunkt und Verkaufspunkt. Die Kopfzeile zeigt das Standdatum der veröffentlichten Nutzungshinweise.
- Nutzungshinweise und Datenschutzerklärung zeigen im Kopf jeweils **Stand TT.MM.JJJJ**. Bei den Nutzungshinweisen ist das der Veröffentlichungstag. Unter **Nutzungshinweise** lässt sich der gesamte Text einschließlich Kontaktdaten mit Überschriften, Fettdruck, Unterstreichung und Aufzählungen bearbeiten. Die Vorschau entspricht der Darstellung am Terminal. **Neue Fassung veröffentlichen** aktiviert den Text sofort. Die Anwendung speichert jede veröffentlichte Fassung sowie die zugehörigen Zustimmungen. Beim nächsten Zugriff bestätigen registrierte Personen die neue Fassung.
- Im **Kassenbuch** nach Verkaufspunkt filtern. Einkäufe und deren Stornos führen den Standort. Selbst eingetragene Barzahlungen und bestätigte PayPal-Zahlungen werden dem jeweiligen Verkaufspunkt zugeordnet. Administrative Zahlungen und Korrekturen gelten für das gemeinsame Konto und tragen keinen Kioskstandort.
- In **Benutzer** stehen Nachname (**Name**), Vorname und Referat in eigenen Spalten. Die Spaltenköpfe **Name**, **Vorname**, **Referat** und **Saldo** ändern die Sortierreihenfolge. Ein erneuter Klick kehrt die Richtung um. In Referaten mit Ziffern steht beispielsweise R 2 vor R 10.
- Für einen **Kartentausch** unter **Benutzer → Karte ersetzen** den Verkaufspunkt ausdrücklich wählen. Nur der dortige Leser erfasst die nächste Karte für diesen Vorgang. Bei der nächsten Kartenanmeldung kann KoSTbar einen bisher unbekannten Typ ergänzen. Der Leser liefert dafür die von PC/SC erkennbare Kartenfamilie oder den Standard. Beispiele sind MIFARE Classic-kompatibel, Type 2 / Ultralight-kompatibel und Topaz / Jewel. NTAG213, 215 und 216 werden ohne eindeutige Typmeldung gemeinsam als Type 2 geführt. Rohe UID und ATR werden dafür nicht gespeichert. Unter **Benutzer → Bearbeiten → Kartenträger** kann das Kassen-Team Dienstausweis, NFC-Schlüsselanhänger oder Sonstiges auswählen. Die Liste zeigt den hinterlegten Kartenträger und, falls erkannt, den technischen Typ. „Kartentyp nicht bestimmt“ erscheint, wenn beide Angaben fehlen. Bei einem Kartentausch wird diese manuelle Angabe für die neue Karte zurückgesetzt.

### Anmeldung und Zahlungen

- Bei der Registrierung mit Karte vergibt und bestätigt jede Person ihre vierstellige PIN. Das Terminal verdeckt beide Eingaben. KoSTbar speichert einen mit einem geheimen Serverschlüssel und einem zufälligen Zusatzwert geschützten scrypt-Prüfwert.
- Über **Ohne Ausweis anmelden** sucht die Person nach Name oder Referat, wählt ihr Konto und gibt die PIN ein. Die Suche zeigt aktive Konten mit eingerichteter PIN. Nach fünf Fehlversuchen ist die PIN-Anmeldung für dieses Konto 15 Minuten gesperrt. Die Kartenanmeldung bleibt möglich.
- Unter **Benutzer → PIN zurücksetzen** löscht das Kassen-Team den Prüfwert und beendet laufende Sitzungen des Kontos. Bei der nächsten Anmeldung mit Karte vergibt und bestätigt die Person eine neue PIN.
- Jede Kiosk-Sitzung endet nach 15 Sekunden ohne Eingabe. In den letzten fünf Sekunden erscheint eine Warnung. **Weiter nutzen** startet die Inaktivitätsfrist neu. **Kaufen** öffnet die Bestätigung des Warenkorbs. Nach einem erfolgreich gebuchten Kauf oder einer gebuchten Barzahlung sind Saldo und Countdown fünf Sekunden sichtbar.
- Die Kachel **Dein Saldo** öffnet die eigenen Buchungen, einschließlich Käufen und Zahlungen, mit Datum und Uhrzeit. Zwischen Monaten lässt sich blättern. Der neueste Eintrag steht jeweils oben.
- **Saldo begleichen → Barzahlung** bucht den eingeworfenen Betrag sofort als Gutschrift. Pro Selbsteintrag sind maximal **100 €** möglich. Zahlungen über die offene Forderung hinaus führen zu Guthaben.
- **Saldo begleichen → PayPal** zeigt den Link und seinen lokal erzeugten QR-Code. Nach Eingabe des Betrags erstellt die Kasse eine offene Meldung mit einer fortlaufenden Referenz wie `KK-1`, `KK-2` und `KK-3`. Beim Senden über das eigene Mobilgerät wird diese Referenz als PayPal-Nachricht eingetragen. Die Person kann bereits offene Meldungen am Terminal wieder aufrufen. Im Admin-Reiter **PayPal** vergleicht das Kassen-Team die Referenz mit dem Zahlungseingang und bucht den tatsächlich eingegangenen Betrag mit der PayPal-Transaktions-ID. Die Kasse akzeptiert jede Transaktions-ID einmal. Abgelehnte oder offene Meldungen ändern den Saldo nicht. Die Überweisung läuft außerhalb der Kasse über PayPal.
- Als Super-Admin unter **Finanzen → PayPal → Empfänger bearbeiten** den Link im Format `https://paypal.me/DeinName` speichern. Ein leeres Feld deaktiviert PayPal. Der Wert wird in PostgreSQL gespeichert, gilt sofort für neue Meldungen und hat Vorrang vor dem optionalen Startwert aus `configure.py --paypal-url`. Bereits offene Meldungen behalten ihren ursprünglichen Empfänger. Bei deaktiviertem PayPal bleiben ihre Referenzen für die Bearbeitung vorhanden. Vor dem ersten Einsatz den Empfänger per Scan prüfen.

- Bei einem Verbindungsabbruch prüft KoSTbar nach Wiederverbindung oder bei der nächsten Anmeldung, ob der zuletzt bestätigte Vorgang schon gespeichert wurde. Ist das der Fall, zeigt das Terminal die Buchung oder PayPal-Referenz an. Der nächste Vorgang wird erst nach dieser Bestätigung freigegeben. Ohne Verbindung zum NAS sind keine Buchungen möglich.

### Verwaltung, Auswertung und Ausdruck

- Der **Administrationsbereich** bündelt die Seiten unter **Finanzen**, **Benutzer**, **Verkauf** und **Verwaltung**. Die Unterseiten klappen beim Überfahren mit der Maus auf. Auf Touchscreens und per Tastatur lassen sich die Gruppen durch Antippen bzw. mit Enter öffnen.
- Unter **Verkauf → Terminal-Vorschau** öffnet der Super-Admin die Kiosk-Oberfläche mit dem aktuellen Sortiment des gewählten Verkaufspunkts. **Testausweis anhalten** meldet das Testkonto an. Für die Anmeldung ohne Ausweis nach **Test Gast** suchen und **1234** eingeben. Über **Sammelkarte (Testkonto)** lässt sich der Stand vorgeben, etwa neun Stempel für einen Testkauf mit einem Heißgetränk, der das Gratisgetränk freischaltet. Erneut anmelden und ein weiteres Heißgetränk kaufen, um die Einlösung zu testen. Registrierung, Belege, Verlauf, Barzahlung und PayPal-Meldung verwenden Testdaten im Browser-Tab. Der Test-QR-Code enthält einen Text. **Testdaten zurücksetzen** beginnt eine neue Simulation.
- **Verkauf → Verkaufspunkte** zeigt pro Kiosk den Verbindungsstatus. Nach zehn Sekunden ohne erfolgreiche Browserabfrage gilt das Terminal als inaktiv. Die Verwaltung aktualisiert die Anzeige alle fünf Sekunden und weist den Leserstatus separat aus.
- Unter **Administratoren** sieht der Super-Admin die Aktionen zum Anlegen, Bearbeiten, Löschen und Zurücksetzen von Passwörtern. Ein Passwort-Reset benötigt das alte Passwort des Zielkontos nicht und beendet dessen aktive Sitzungen. Das eigene Passwort lässt sich in beiden Rollen über **Passwort ändern** mit Eingabe des bisherigen Passworts ändern.
- Das **Änderungsprotokoll** lädt beim Öffnen die erste Seite. Über **Ältere Änderungen** und **Neuere Änderungen** lassen sich alle Einträge in Seiten mit bis zu 100 Datensätzen ansehen. Der ausführende Admin sowie der vorherige und neue Stand werden angezeigt. Rot kennzeichnet entfernte, gelb geänderte und grün hinzugefügte Werte. Ältere Einträge behalten ihre vorhandenen Angaben.
- Unter **Sortiment** nach Kategorie filtern. Archivierte Produkte lassen sich reaktivieren. Dauerhaft ausgeblendete Produkte verschwinden aus dem Sortiment und von allen Terminals. Für bestehende Buchungen, Stornos und Auswertungen bleibt die historische Produktzuordnung erhalten.
- Unter **Verkauf → Verkaufspunkte** verwaltet der Super-Admin Standorte, Kopplungen und private Pi-Profile. Reguläre Admins sehen den Verbindungsstatus und verwalten das Sortiment. Neue Verkaufspunkte starten mit leerem Sortiment. Beim Löschen entfernt KoSTbar den Standort aus dem laufenden Betrieb und widerruft die Kopplung. Die Kennung bleibt für die Historie reserviert. Kassenbuch und Auswertung lassen sich weiterhin nach dem gelöschten Standort filtern.
- **Auswertung** zeigt je Kalendermonat und optional je Verkaufspunkt Verkäufe, Stornos und Umsatz nach Stornos sowie Stückzahlen je Produkt. Verkäufe und Stornos zählen zu ihrem jeweiligen Buchungsmonat. Zahlungseingänge zählen zum Saldenausgleich. KoSTbar schreibt die Monatssummen beim Kauf oder Storno in derselben Datenbanktransaktion. Sie enthalten keine Kontozuordnung und bleiben nach Ablauf der Buchungsdetails verfügbar. Eine spätere Löschung des Kaufs ändert die gespeicherte Produktzuordnung im Monatsbericht nicht.
- **Benutzer → Gesamtexport** exportiert alle Konten einschließlich gesperrter Konten mit Referat, Saldo und offener Forderung. **Export** neben einer Person erstellt den Einzelkontoauszug mit Referat, Buchungen, Kaufpositionen und laufendem Saldo. Beide Dateien sind als DIN A4 mit Druckbereich, wiederholten Tabellenköpfen, Stichtag im Druckkopf und **Seite X von Y** im Footer eingerichtet. Die Saldenliste ist im Hochformat, der Einzelkontoauszug im Querformat. Als Stichtag gilt der Zeitpunkt des Abrufs in deutscher Ortszeit.

Vor der Freigabe die eingerichteten Terminals am tatsächlichen Standort prüfen. Die standortübergreifenden Schritte gelten ab zwei Terminals.

1. Jeder Verkaufspunkt wird korrekt angezeigt. Sind mehrere eingerichtet, aktiviert die Karte nur den Pi, an dessen Leser sie angehalten wird.
2. Bei mehreren Terminals je ein Testprodukt exklusiv einem Standort zuweisen und die Sortimente vergleichen. Auch mit einem Terminal lässt sich prüfen, ob die Kasse eine Aktualisierung verlangt, wenn du einen Artikel während eines offenen Warenkorbs für diesen Standort entfernst und anschließend den Checkout versuchst.
3. Nutzungsbedingungen öffnen und Ansprechpartner sowie Erreichbarkeit prüfen. Ein Konto mit expliziter Zustimmung anlegen. In der Adminansicht den Status **Bestätigt** prüfen. Mit einem zweiten Terminal prüfen, ob dieselbe Karte auch dort zum gleichen Konto führt.
4. Bei mehreren Terminals für dasselbe Konto an zwei Standorten buchen. Beide Käufe müssen ihrem Standort und dem gemeinsamen Saldo zugeordnet sein. Fällt vor der Belegbestätigung die Antwort eines Terminals aus, muss der nächste Kiosk-Buchungsversuch für dieses Konto zuerst den letzten Vorgang klären. Nach jedem erfolgreichen Kauf oder einer gebuchten Barzahlung kehrt das Terminal nach fünf Sekunden zum Start zurück.
5. Einen Kauf tätigen, danach Barzahlung und PayPal-Meldung prüfen. Die PayPal-Meldung darf den Saldo erst nach einer Admin-Bestätigung verändern. Für diesen Test nur simulierte Zahlungen verwenden.
6. Eine Testperson mit Karte registrieren. PIN und Bestätigung zunächst unterschiedlich eingeben und die Fehlermeldung prüfen. Mit übereinstimmender PIN und führender Null registrieren, danach ohne Karte anmelden. Im Adminbereich unter **Benutzer → PIN zurücksetzen** den Zugang zurücksetzen. Erneut mit Karte anmelden, eine neue PIN vergeben und die Anmeldung ohne Karte mit der neuen PIN prüfen. Danach in der laufenden Sitzung 15 Sekunden keine Eingabe machen. Die Warnung erscheint in den letzten fünf Sekunden. Prüfen, dass **Weiter nutzen** die Frist neu startet und dass ohne weitere Eingabe die Abmeldung erfolgt. Beide Excel-Exporte in der Druckvorschau öffnen.
7. Die Pis neu starten. Querformat, Touch-Zuordnung, Chromium-Start ohne Keyring-Dialog und Leserdienste prüfen. Bei einem Testkauf und bei einer Test-Barzahlung die Verbindung während der Antwort kurz unterbrechen. Nach der Wiederverbindung bzw. Anmeldung muss ein schon gespeicherter Vorgang einmalig in der Buchungshistorie stehen. Falls die Buchung nie angekommen ist, kann der Vorgang erneut gestartet werden.

### Datenschutzerklärung

Auf allen Terminals steht der Link zur Datenschutzerklärung im Fußbereich und bei der Registrierung. Im Admin-Bereich unter **Datenschutz** lassen sich Text und Standdatum pflegen. Der Editor bietet Überschriften, Fett, Unterstreichung, Aufzählungen und eine Vorschau. Änderungen erscheinen an allen Terminals. Historische Bestätigungen behalten die damals gültigen Fassungen. Nach Veröffentlichung einer neuen Fassung ist die aktuelle Dokumentkombination erneut zu bestätigen.

Vor der Freigabe die als `[EINTRAGEN: …]` markierten Betreiberangaben, Empfänger, Drittlandübermittlungen, Fristen und die zuständige Aufsicht vervollständigen. Die Vorlage in `privacy.md` geht von einem freiwillig vereinbarten Kassenkonto aus. Art. 6 Abs. 1 Buchst. b DSGVO setzt für jeden Verarbeitungsschritt voraus, dass er für die vereinbarte Leistung objektiv erforderlich ist. Das gilt auch für das Pflichtfeld Referat, die Anzeige in der Namenssuche und die Erfassung von Kartenmerkmalen. Für die auf Art. 6 Abs. 1 Buchst. f DSGVO gestützten Sicherheits- und Nachweiszwecke die Interessenabwägung dokumentieren. [DSGVO · Art. 5, 6 und 13](https://eur-lex.europa.eu/eli/reg/2016/679/oj?locale=de) · [EDSA · Leitlinien zu Art. 6 Abs. 1 Buchst. b](https://www.edpb.europa.eu/documents/guideline/guidelines-22019-on-the-processing-of-personal-data-under-article-61b-gdpr-in_de)

Falls eine Behörde KoSTbar in Erfüllung ihrer Aufgaben betreibt, die konkrete Aufgaben- und Rechtsgrundlage prüfen. Art. 6 Abs. 1 Buchst. f DSGVO steht Behörden bei der Aufgabenerfüllung nicht zur Verfügung. In diesem Fall kommt Art. 6 Abs. 1 Buchst. e in Verbindung mit Art. 6 Abs. 3 DSGVO nur mit tragfähiger gesetzlicher Grundlage in Betracht. Gesetzliche Aufbewahrungspflichten nur angeben, soweit sie den tatsächlichen Betreiber treffen. Die Datenschutzerklärung wird zur Kenntnis genommen. [DSGVO · Art. 6](https://eur-lex.europa.eu/eli/reg/2016/679/oj?locale=de)

### Aushänge exportieren und drucken

In der Verwaltung unter **Nutzungshinweise** oder **Datenschutz** den Text und das Standdatum prüfen. **HTML für Druck exportieren** übernimmt den aktuellen Editorinhalt samt Formatierung. Das funktioniert auch mit ungespeicherten Änderungen. Bei den Nutzungshinweisen gilt das gewählte Standdatum nur für den Export. **Veröffentlichte Fassung exportieren** ruft den aktuell veröffentlichten Text ab samt seinem Standdatum. Diese Druckfassung eignet sich für den Aushang. Ein Export veröffentlicht keine neue Fassung und berührt bestehende Zustimmungen nicht.

Die heruntergeladene HTML-Datei im Browser öffnen. Logo und Schriften sind eingebettet. Text und Datum lassen sich anklicken und bei Bedarf direkt ändern. **HTML speichern** lädt eine Kopie mit den Änderungen herunter. **Drucken** öffnet die Druckvorschau für A4 im Hochformat. Im Browser lassen sich bei Bedarf Kopf- und Fußzeilen abschalten. Bei längeren Texten die Seitenaufteilung in der Vorschau prüfen. Änderungen an der HTML-Datei wirken nur auf diese Datei.

## Backup und Wiederherstellung

Pro Terminal ein technisches RADIUS-Konto verwenden. Nach einem Passwortwechsel oder einer Erneuerung der RADIUS-CA das WLAN-Profil nach der [Terminal-Anleitung](TERMINALS.md) aktualisieren und die automatische Anmeldung per Neustart prüfen. Bei Geräteverlust das zugehörige Konto sperren.

### Aufbewahrung der Buchungen

Der Hintergrunddienst startet zusammen mit dem Backend und prüft die fällige Bereinigung fortlaufend. Unter **Verwaltung → Technik** stehen der Zustand und der letzte erfolgreiche Lauf seit dem Backend-Start. Bei einem Fehler erscheint im App-Protokoll eine Meldung. Der Dienst versucht es nach fünf Sekunden erneut. Wenn Datenbank und Kasse erreichbar sind, kann während eines fehlgeschlagenen Laufs weiter gebucht werden.

90 Tage nach der jeweiligen Buchung entfernt der Löschlauf persönliche Einzelbuchungen, Artikelpositionen und buchungsbezogene Protokolle. Der Nettobetrag fließt in derselben Datenbanktransaktion in den Saldoübertrag. Stornos haben ihr eigenes Buchungsdatum. Einzelkontoauszug, Kassenbuch und persönlicher Verlauf filtern abgelaufene Details auch bei einem Rückstand aus. Der Einzelkontoauszug rechnet die noch nicht übertragenen Altbeträge in den Saldoübertrag ein. Die Monatssummen je Produkt und Verkaufspunkt enthalten keine Konto- oder Buchungskennungen und bleiben verfügbar.

Offene PayPal-Meldungen verfallen 90 Tage ab Erstellung. Bestätigte Meldungen bleiben 90 Tage ab Gutschrift, abgelehnte 90 Tage ab Entscheidung erhalten. Danach verhindert ein HMAC-Prüfwert ohne Kontozuordnung die erneute Gutschrift bereits verbuchter Transaktions-IDs. Solange im Backend auch alte Zahlungseingänge nachgebucht werden können, bleibt der Prüfwert gespeichert. Wird ein Zahlungseingang erst nach Ablauf einer offenen Meldung bemerkt, gleicht das Kassen-Team ihn anhand der PayPal-Unterlagen ab.

Unter **Benutzer → Konto schließen** den Zugang ausscheidender Personen sofort sperren. Der PIN-Prüfwert wird entfernt und aktive Sitzungen enden. Die Verwaltung kann offene Beträge und Guthaben weiter ausgleichen sowie offene PayPal-Meldungen bearbeiten. Sobald der Saldo null ist und die letzte Einzelbuchung oder PayPal-Meldung abgelaufen ist, entfernt der Löschlauf das Konto, die Kartenkennung, seine Zustimmungsnachweise und die direkt zugeordneten Verwaltungsprotokolle. Eine vorübergehende Sperre über **Bearbeiten** lässt sich weiterhin rückgängig machen und führt zu keiner Kontolöschung. Der Sperrprüfwert einer ersetzten Karte verfällt nach 90 Tagen. Danach kann die Karte wie eine unbekannte Karte neu registriert werden. Allgemeine Verwaltungsprotokolle werden nach 180 Tagen gelöscht.

Für KoSTbar-Sicherungen und NAS-Snapshots eine rollierende Frist von **30 Tagen** in der jeweiligen Sicherungssoftware einstellen. Für Exporte und Ausdrucke gilt die Aufbewahrung bis zum Ende ihres Abrechnungszwecks. Diese Dateien liegen außerhalb der Datenbank und werden vom Kassen-Team oder dem NAS-Backupdienst entfernt. Bei einer Rücksicherung nach der folgenden Anleitung vor Freigabe des Zugriffs auch seit dem Sicherungsstand erfolgte Kontoschließungen erneut anwenden.

Das private Chromium-Profil des Kiosk-Kontos liegt unter `~kiosk/.local/share/kostbar-chromium` und speichert die Browser-Gerätekennung für den Neustart. Der Browser-Cache liegt in `/dev/shm`. KoSTbar-Antworten werden mit `Cache-Control: no-store` ausgeliefert. Das Kiosk-Profil gehört zur Geräteidentität und darf beim Klonen eines Pi-Images nicht mitkopiert werden. Auf dem NAS liegen nur die Prüfwerte der Kopplung.

### Sicherung und Wiederherstellung

Sichere regelmäßig die Datenbank, `config/server.json`, `.env` und die privaten Geräteprofile. Sichere auch den passenden App-Stand oder dessen Image-Referenz mit Digest. Der ursprüngliche `card_key` wird für Kartenanmeldung, Browserkopplung und die Wiederherstellung regulär erzeugter Tokens dynamischer Verkaufspunkte benötigt. Bei **QNAP** zusätzlich das Caddy-Datenvolume mit dem privaten Schlüssel der internen CA sichern. Bei **Synology** HTTPS-Zertifikat, Zertifikatserneuerung und Reverse-Proxy-Regel samt beider Anfrage-Header separat in der DSM-Sicherung berücksichtigen. Alle Backups verschlüsselt oder in einem gleichwertig geschützten Sicherungsziel aufbewahren.

```bash
umask 077
backup_stamp=$(date +%F_%H%M%S)
sudo docker compose -p kostbar exec -T db pg_dump -U postgres -d kaffeekasse -Fc > "kasse-${backup_stamp}.dump"
# Nur für QNAP, solange der Proxy läuft
sudo docker compose -p kostbar exec -T proxy tar -C /data -czf - . > "caddy-${backup_stamp}.tar.gz"
```

Zusätzlich die Konfigurationsdateien in den Sicherungssatz kopieren. Einen Sicherungssatz regelmäßig auf einer getrennten Testinstanz wiederherstellen. Für die Wiederherstellung in einer bestehenden Installation zuerst den aktuellen Stand sichern und den Zugriff auf die Kasse beenden. Das Beispiel ersetzt die im Dump enthaltenen Objekte in der aktuellen Datenbank.

```bash
sudo docker compose -p kostbar stop proxy app
sudo docker compose -p kostbar exec -T db pg_restore -U postgres -d kaffeekasse \
  --clean --if-exists --exit-on-error --single-transaction < kasse-ZEITSTEMPEL.dump
```

Die zum Datenstand passende `server.json` mit dem ursprünglichen `card_key` bereitstellen. Die Anmeldedaten in `.env` müssen zur laufenden Datenbank passen. In einer vorbereiteten Ersatzinstallation müssen Datenbank und Rolle vor dem Import durch den Datenbankdienst initialisiert sein.

Bei QNAP auf einem **neuen, leeren** Caddy-Datenvolume vor dem ersten Proxy-Start das zugehörige CA-Backup einspielen. Ist das ursprüngliche Caddy-Volume intakt, kann es weiterverwendet werden. Bei Synology für ein Ersatzsystem die DSM-Proxy-Regel und das passende Zertifikat bereitstellen.

```bash
sudo docker compose -p kostbar run --rm --no-deps -T --entrypoint /bin/sh proxy \
  -c 'tar -xzf - -C /data' < caddy-ZEITSTEMPEL.tar.gz
```

Die App erst nach erfolgreichem Import starten. Den Proxy erst nach erfolgreichem Healthcheck öffnen. Den Zugang der Terminals nach einer Rücksicherung bis zum Abgleich der seit dem Sicherungsstand erfolgten Kontoschließungen zurückhalten.

```bash
sudo docker compose -p kostbar up -d --no-deps --force-recreate app
sudo docker compose -p kostbar ps app
# Nach erfolgreichem Healthcheck und den erforderlichen Prüfungen
sudo docker compose -p kostbar up -d proxy
```

## Technische Dokumentation pflegen

Die Seite **Verwaltung → Technik** zeigt Architektur, Datenfluss, API und Versionen. Das Architekturdiagramm zeigt den WLAN-Zugang über PEAP/MSCHAPv2 und RADIUS sowie die HTTPS-Verbindung zum NAS. Die Ansicht meldet die Laufzeitversionen von Python, PostgreSQL und Caddy, die konfigurierte App-Image-Referenz und die Image-Vorgaben der gemeinsamen Compose-Datei. Installierte Pi-Paketversionen meldet der Leserdienst bei Verbindung. Bei älteren Pis ohne diese Meldung den aktuellen Terminal-Installer mit vorhandenem Geräteprofil und gegebenenfalls der NAS-CA erneut ausführen.

Bei Änderungen an HTTP-Endpunkten Methode, Berechtigung, Beschreibung und Eingaben in `api_reference.py` zusammen mit `web.py` und `server.py` pflegen. `python check_api_reference.py` gleicht die Pfade mit der Referenz ab und läuft beim Image-Build. Erlaubte HTTP-Methode, Rolle und Pflichtfelder der betroffenen Operation zusätzlich mit einem Aufruf prüfen. Bei Änderungen an Rollen, Datenfluss oder Architektur auch `static/technical-docs.js` und diese Anleitung aktualisieren. Paketvorgaben stehen in `requirements.txt`. Die Liste der vom Pi gemeldeten Pakete steht in `pi/versions.py`.

Schreiboperationen in `admin_operations.py` verwenden die von `server.py` eröffnete Datenbanktransaktion. Eine Kontosperre, Kontoschließung oder ein PIN-Reset beendet die betroffenen Kiosksitzungen erst nach dem Commit. `policy_documents.py` lädt und aktualisiert die veröffentlichten Fassungen beim Start. Die Aktualisierungsmarker in PostgreSQL stellen sicher, dass Ergänzungen einmalig angewendet werden.

QNAP und Synology verwenden dasselbe versionierte App-Image. Das gemeinsame `compose.common.yml` liegt als Referenz für die Technikansicht auch im Image. Der gewählte NAS-Unterordner setzt `KOSTBAR_DEPLOYMENT` und bindet seine Caddy-Konfiguration sowie `server.json` zur Laufzeit ein. Das jeweilige `nas/deployment.json` liefert Standardwerte für `configure.py` auf dem NAS. Die Wahl der NAS-Variante erfolgt beim Deployment.

### Patchstand bei Neuinstallation und späteren Builds

PostgreSQL und Caddy verwenden Tags für Release-Reihen. Für einen frischen Patchstand im NAS-Unterordner `sudo docker compose -p kostbar pull db proxy` ausführen und die Images mit `sudo docker compose -p kostbar up -d --pull never` anwenden. Das KoSTbar-App-Image für einen freigegebenen Stand zentral erzeugen oder aus der eigenen Registry beziehen. Details stehen unter [App-Image bereitstellen](../README.md#app-image-bereitstellen). Die gemeldeten Laufzeitversionen unter **Technik** und die bezogenen Image-Digests vor der Abnahme erfassen. Für reproduzierbare Freigaben die geprüften Digests im eigenen Deployment festlegen und bei Updates bewusst erneuern. [Docker Compose up](https://docs.docker.com/reference/cli/docker/compose/up/)
