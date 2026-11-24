## Verantwortlich und Kontakt
Verantwortlich für KoSTbar: [EINTRAGEN: Name, Anschrift und Kontakt der verantwortlichen Stelle, ggf. Vertretung].
Datenschutzbeauftragte Stelle: [EINTRAGEN: Kontakt, falls bestellt; sonst Zeile streichen].

## Zweck, Daten und Rechtsgrundlage
Wir verarbeiten Daten für dein Kassenkonto, die Anmeldung, Einkäufe, die Abrechnung und die Sicherheit der Anwendung. Dazu gehören Name, Referat, ein HMAC-Prüfwert der Ausweiskennung, soweit verfügbar der Kartentyp und die Angabe zum Kartenträger, der Hash der PIN, Zeitpunkt und Fassungen der bestätigten Nutzungsbedingungen und Datenschutzerklärung, Buchungen und der Saldo. Die Namenssuche am Terminal zeigt Name und Referat. Bei Verwaltungszugängen kommen Anmeldename, Passwort-Hash und Änderungsprotokoll hinzu. Zur Begrenzung von Fehlversuchen wird die Quell-IP vorübergehend im Arbeitsspeicher berücksichtigt.

### Betrieb des Kassenkontos und Abrechnung
Art. 6 Abs. 1 Buchst. b DSGVO ist die Grundlage für die Daten, die für die freiwillig vereinbarte Nutzung von KoSTbar erforderlich sind. Dazu zählen die Einrichtung und Zuordnung deines Kassenkontos, die Anmeldung mit Karte oder PIN, die Zuordnung deiner Einkäufe und Zahlungen sowie die Führung und Abrechnung deines Saldos. Wenn du die Zahlung über PayPal auswählst, gilt diese Grundlage für die Zuordnung der Zahlung zu deinem Kassenkonto durch das Kassen-Team.

### Sicherheit und Nachvollziehbarkeit
Art. 6 Abs. 1 Buchst. f DSGVO ist die Grundlage für die dazu erforderliche Verarbeitung bei der Absicherung der Zugänge, zum Beispiel bei der Begrenzung von Anmeldeversuchen, der Sperre ersetzter Karten und der Protokollierung von Verwaltungsänderungen. Das berechtigte Interesse besteht darin, unbefugte Zugriffe und Doppelbuchungen zu verhindern, Änderungen am Kassenbestand nachvollziehen zu können und den Stand der vereinbarten Nutzungsbedingungen und bereitgestellten Datenschutzhinweise zu dokumentieren.

## Anmeldung mit PIN
KoSTbar speichert nur einen mit einem geheimen Serverschlüssel und einem zufälligen Zusatzwert geschützten Einweg-Prüfwert der vierstelligen PIN. Das Kassen-Team kann den Prüfwert zurücksetzen. Bei der nächsten Anmeldung mit Karte vergibst du selbst eine neue PIN. Fehlversuche werden je Konto vorübergehend in der Datenbank gezählt.

## Empfänger und PayPal
Zugriff haben das berechtigte Kassen-Team und, soweit erforderlich, der IT-Betrieb. [EINTRAGEN: ggf. weitere Empfänger und Drittlandübermittlungen samt Garantien; sonst die zutreffende Aussage ergänzen].
Bei freiwilliger PayPal-Zahlung nutzt du PayPal auf deinem eigenen Gerät. Für diese Verarbeitung gelten die Hinweise von PayPal. Das Kassen-Team übernimmt zur Zuordnung Betrag, Referenz und Transaktions-ID aus dem Zahlungseingang. KoSTbar bindet PayPal nicht technisch ein.

## Speicherort und Aufbewahrung
Die Datenbank wird hier betrieben: [EINTRAGEN: tatsächlicher Speicherort und Schutz des Datenbankspeichers]. Die Terminals greifen per HTTPS auf das NAS zu. Sie speichern keine Konten oder Buchungen dauerhaft. KoSTbar nutzt Sitzungscookies für die Anmeldung. Eine separate Gerätekennung ordnet das Terminal dauerhaft seinem Verkaufspunkt zu und lässt sich durch das Kassen-Team widerrufen. KoSTbar verwendet keine Tracking-Cookies. Einzelbuchungen und zugehörige Details werden nach **90 Tagen** gelöscht. Offene Forderungen und Guthaben bleiben als Saldoübertrag erhalten. Für Auswertungen bleiben monatliche Summen je Produkt und Verkaufspunkt ohne Kontozuordnung gespeichert. Offene PayPal-Meldungen verfallen nach 90 Tagen. Für bestätigte oder abgelehnte Meldungen beginnt die Frist mit der Buchung oder der Entscheidung. Zur Vermeidung von Doppelbuchungen bleibt ein Prüfwert bestätigter PayPal-Transaktionen ohne Kontozuordnung erhalten, solange nachträgliche Buchungen möglich sind.
Wenn das Kassen-Team dein Konto schließt, werden der Zugang gesperrt und der Prüfwert der PIN entfernt. Das Konto samt Kartenkennung und persönlichen Zustimmungsnachweisen wird gelöscht, sobald der Saldo ausgeglichen ist und die verbleibenden Buchungs- und PayPal-Fristen abgelaufen sind. Allgemeine Verwaltungsprotokolle werden nach 180 Tagen gelöscht. Direkt kontobezogene Einträge können mit der Kontolöschung früher entfallen. Der Sperrprüfwert einer ausgetauschten Karte bleibt 90 Tage gespeichert.
Sicherungen und Snapshots: [EINTRAGEN: tatsächliche rollierende Frist, vorgesehen sind 30 Tage]. Exporte und Ausdrucke werden gelöscht oder vernichtet, sobald sie für die Abrechnung nicht mehr erforderlich sind.

## Sammelkarte
Für die Sammelkarte wird der aktuelle Punktestand deinem Konto zugeordnet und ohne Ablaufdatum gespeichert. Dieser Stand enthält keine Liste von Einkäufen, Produkten, Zeitpunkten oder Verkaufspunkten. Buchungsbezogene Angaben zu Stempeln und Gratisgetränken werden zusammen mit den Einzelbuchungen nach 90 Tagen gelöscht. Bei der Löschung des Kontos wird auch der Sammelkartenstand gelöscht.
KoSTbar speichert zusätzlich die Gesamtzahl der eingelösten Gratisgetränke ohne Ablaufdatum. Stornierte Gratisgetränke werden abgezogen. Das Kassen-Team kann beide Zähler pro Konto einsehen. Bei der Kontolöschung entfällt auch dieser Zähler.

## Netzzugang der Terminals
Für den Zugang zum internen WLAN verwendet jedes Terminal ein technisches Gerätekonto beim RADIUS-Dienst. Die WLAN-Zugangsdaten werden außerhalb von KoSTbar verwaltet und sind keinem Kassenkonto zugeordnet.

## Freiwilligkeit und deine Rechte
Die digitale Teilnahme ist freiwillig. Für ein KoSTbar-Konto sind Name, Referat, die Zuordnung einer Karte und die Vergabe einer vierstelligen PIN erforderlich. Ohne diese Angaben bleibt die Barzahlung ohne KoSTbar-Konto möglich. Es gibt keine ausschließlich automatisierten Entscheidungen mit rechtlicher oder ähnlich erheblicher Wirkung.
Die Bestätigung der Datenschutzerklärung dokumentiert, dass du die Hinweise zur Kenntnis genommen hast. Du kannst nach Maßgabe der DSGVO Auskunft, Berichtigung, Löschung, Einschränkung und Datenübertragbarkeit verlangen.

**Widerspruchsrecht nach Art. 21 Abs. 1 DSGVO.** Du kannst einer Verarbeitung nach Art. 6 Abs. 1 Buchst. f DSGVO jederzeit aus Gründen widersprechen, die sich aus deiner besonderen Situation ergeben.
Du hast ein Beschwerderecht bei einer Datenschutzaufsichtsbehörde. Zuständige Stelle: [EINTRAGEN: Name und Kontakt der Aufsicht].
