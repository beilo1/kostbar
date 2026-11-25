import {dateTime, esc} from './shared.js';
import {table as renderTable} from './ui-table.js';

const purpose = {
  chromium: 'Kiosk-Browser', python3: 'Laufzeit des Leserdiensts', 'python3-pyscard': 'PC/SC-Anbindung in Python',
  pcscd: 'PC/SC-Systemdienst', libccid: 'Treiber für USB-Kartenleser', 'pcsc-tools': 'Leserdiagnose',
  lightdm: 'Automatische Anmeldung in der KoSTbar-Sitzung', labwc: 'Eigene Wayland-Kiosksitzung', curl: 'HTTPS-Verbindungsprüfung',
  'wlr-randr': 'Displaydrehung beim Kioskstart',
  usbguard: 'USB-Gerätefreigabe am Terminal',
  'network-manager': 'WLAN-Systemprofil und PEAP/MSCHAPv2-Anmeldung',
  unzip: 'Entpacken des Installationspakets', 'libnss3-tools': 'Zertifikatsimport in Chromium', 'util-linux': 'Prozesssperre beim Kioskstart',
};

const areas = {
  'System und Leserdienst': ['Betrieb', 'Öffentlich', 'Leserdienst'],
  'Kiosk und Kopplung': ['Kiosk', 'Kopplung'],
  'Verwaltung': ['Admin-Login', 'Admin', 'Super-Admin'],
};

function table(headers, rows) {
  return renderTable(headers, rows.map(row => `<tr>${row.map(cell => `<td>${cell}</td>`).join('')}</tr>`).join(''));
}

const box = (title, detail) => `<div><strong>${title}</strong><small>${detail}</small></div>`;
const arrow = label => `<span class="tech-arrow"><small>${label}</small><span aria-hidden="true">→</span></span>`;

function architecture(synology) {
  const edge = synology ? 'DSM Reverse Proxy → Caddy' : 'Caddy mit interner CA';
  return `<section id="tech-arch"><h3>Architektur</h3>
    <h4>WLAN-Zugang der Terminals</h4>
    <p>Für die Ersteinrichtung und Paketupdates nutzen die Pis ein vorläufiges PSK-WLAN. Im Produktivbetrieb verbindet NetworkManager jedes Terminal beim Start über ein systemweites WPA2-Enterprise-Profil mit dem separaten Terminal-VLAN.</p>
    <div class="tech-flow tech-flow-wifi" role="group" aria-label="Die Pis melden sich per PEAP und MSCHAPv2 am WLAN-Access-Point an, der die Authentifizierung an RADIUS weiterleitet">
      ${box('Raspberry Pis', 'Je ein Gerätekonto mit Passwort')}${arrow('PEAP / MSCHAPv2')}
      ${box('WLAN-Access-Point', 'WPA2-Enterprise')}${arrow('RADIUS')}
      ${box('RADIUS-Dienst', 'Prüft die Geräteanmeldung')}
    </div>
    <p>Der Pi prüft die CA und den erwarteten Namen im RADIUS-Serverzertifikat. Das aktive WLAN-Profil und den Anmeldeerfolg prüfst du auf dem Pi und am RADIUS-Dienst.</p>
    <h4>HTTPS zur Anwendung</h4>
    <div class="tech-flow" role="group" aria-label="Chromium und Leserdienst greifen über den NAS-Proxy auf Waitress und PostgreSQL zu">
      ${box('Verkaufspunkte', 'Chromium und PC/SC-Leserdienst')}${arrow('HTTPS')}
      ${box('NAS-Einstieg', edge)}${arrow('HTTP im Docker-Netz')}
      ${box('KoSTbar-Backend', 'Waitress · Python')}${arrow('SQL / Psycopg')}
      ${box('PostgreSQL', 'Konten, Sortiment, Buchungen')}
    </div>
    <p>Chromium öffnet <code>/</code> mit dem unprivilegierten Kioskkonto. Der PC/SC-Leserdienst hat ein eigenes Dienstkonto. Die Verwaltung unter <code>/admin</code> nutzt vom Wartungsrechner denselben HTTPS-Einstieg. ${synology ?
      'DSM terminiert TLS. Caddy nimmt intern Anfragen vom DSM Reverse Proxy an und reicht sie an das Backend weiter.' :
      'Caddy stellt das HTTPS-Zertifikat über seine interne CA aus und leitet intern an das Backend weiter.'}
      App und Datenbank haben keine eigenen veröffentlichten Host-Ports.</p>
    <p>Das Backend läuft als einzelner Waitress-Prozess mit acht Threads. Admin-Sitzungen, Kiosksitzungen und ausstehende Kopplungen liegen im Prozessspeicher. Kiosk-Anfragen sind pro Terminal synchronisiert. Buchungen verwenden Kontosperren in PostgreSQL. Abgeschlossene Kopplungen und Geschäftsdaten bleiben in PostgreSQL erhalten.</p>
    <p>Die HTTP-Schicht prüft Anfragen. Eigene Backend-Module übernehmen Schreiboperationen der Verwaltung und das Laden und Aktualisieren der veröffentlichten Dokumentfassungen. Nach einer Kontosperre, Kontoschließung oder einem PIN-Reset beendet die Anwendung die betroffene Kiosksitzung erst nach erfolgreichem Datenbank-Commit.</p>
  </section>`;
}

const flow = `<section id="tech-flow"><h3>Datenfluss</h3>
  <ol class="tech-steps">
    <li><strong>Terminal koppeln</strong><p>Der PC/SC-Dienst meldet seine Gerätekennung und den Leserstatus per HTTPS. Der Browser fordert einen Einmalcode an. Die Verwaltung bestätigt ihn für denselben Verkaufspunkt. Das Backend speichert die Prüfwerte der Gerätezuordnung und stellt das widerrufbare Browser-Cookie aus.</p></li>
    <li><strong>Anmelden und Sortiment laden</strong><p>Der Leserdienst überträgt eine Kartenkennung samt erkanntem Kartentyp. Das Backend bildet einen HMAC-Prüfwert und verwendet ihn zur Kontozuordnung. Der Kiosk lädt das aktive Sortiment für seinen gekoppelten Standort. Registrierungen speichern die Zustimmung zu beiden Dokumentfassungen.</p></li>
    <li><strong>Kaufen und bezahlen</strong><p>Das Backend prüft Artikel, Preis und Standort. Ein Kauf schreibt Buchung und Artikelpositionen gemeinsam in PostgreSQL. Beträge sind ganzzahlige Eurocent. Barzahlungen werden direkt gutgeschrieben. PayPal erzeugt zunächst eine offene Meldung, die ein Admin nach externem Zahlungseingang bestätigt. Jeder dieser Vorgänge wird zusammen mit seinem Anzeigestatus gespeichert. Ging die Antwort verloren, muss das angemeldete Konto den letzten Vorgang prüfen, bevor es erneut buchen kann.</p></li>
    <li><strong>Verwalten und aufbewahren</strong><p>Admin-Aktionen werden im Änderungsprotokoll erfasst. Auswertungen und Excel-Exporte kommen vom Backend. Die Bereinigung überträgt abgelaufene Beträge nach 90 Tagen in den Saldoübertrag. Monatsberichte beziehen ihre Summen aus Tabellen ohne Kontozuordnung. Geschlossene Konten werden nach Ausgleich und Ablauf der Detailfristen entfernt. Allgemeine Verwaltungsprotokolle haben eine Frist von 180 Tagen.</p></li>
  </ol>
  <h4>Persistente Daten</h4>
  ${table(['Bereich', 'PostgreSQL-Tabellen', 'Beziehung'], [
    ['Verkaufspunkte', '<code>terminals</code>, <code>kiosk_devices</code>, <code>product_terminals</code>', 'Je Standort eine Browserkopplung. Produkte lassen sich mehreren Standorten zuordnen.'],
    ['Konten und Zustimmung', '<code>people</code>, <code>terms_versions</code>, <code>privacy_versions</code>, <code>policy_acceptances</code>', 'Die Zustimmung verbindet ein Konto mit beiden Dokumentfassungen und dem Standort.'],
    ['Einkäufe und Salden', '<code>journal</code>, <code>items</code>, <code>carried_balances</code>', 'Buchungen gehören zu einem Konto. Artikelpositionen gehören zur Kaufbuchung. Der Saldo enthält auch den Übertrag.'],
    ['Monatsauswertung', '<code>monthly_sales</code>, <code>monthly_products</code>', 'Käufe und Stornos aktualisieren die Summen gemeinsam mit der Buchung. Produktnamen werden als Bezeichnung beim Kauf gespeichert, bei Umbenennung getrennt ausgewiesen und bei Storno beibehalten. Die Summen enthalten weder Konto- noch Buchungskennungen.'],
    ['Zahlung und Verwaltung', '<code>paypal_requests</code>, <code>admins</code>, <code>audit</code>', 'Bestätigte PayPal-Meldungen verweisen auf eine Buchung. Admin-Aktionen werden separat protokolliert.'],
  ])}
  </section>`;

function packageVersions(doc) {
  const retention = doc.retention || {};
  const retentionStatus = retention.failed_since ? 'Gestört seit ' + dateTime(retention.failed_since)
    : retention.running_since ? 'Lauf seit ' + dateTime(retention.running_since)
      : retention.last_success ? 'Bereit' : 'Erster Lauf steht aus';
  const lastRun = retention.last_success ? dateTime(retention.last_success) : 'Noch kein erfolgreicher Lauf';
  const runtime = [
    ['Python', esc(doc.python), 'Laufzeit im App-Container'],
    ['PostgreSQL', esc(doc.postgresql), 'Version der verbundenen Datenbank'],
    ['Caddy', esc(doc.caddy || 'Nicht gemeldet'), 'Version des Proxys dieser Anfrage'],
    ['Datenbereinigung', esc(retentionStatus), 'Letzter Erfolg · ' + esc(lastRun)],
    ...(doc.deployment === 'Synology' ? [['DSM Reverse Proxy', 'In DSM ablesen', 'TLS-Endpunkt auf dem NAS']] : []),
    ...doc.images.map(x => [esc(x.name), `<code>${esc(x.tag)}</code>`, 'Konfigurierter Container-Tag']),
  ];
  const dependencies = doc.dependencies.map(x => [esc(x.name), esc(x.installed), esc(x.pinned)]);
  const terminalVersions = doc.pi_packages.map(name => [`<code>${esc(name)}</code>`, purpose[name] || '',
    ...Object.values(doc.terminals).map(t => esc(t?.[name] || '—'))]);
  return `<section id="tech-versions"><h3>Komponenten und Versionen</h3>
    <h4>NAS und Container</h4>${table(['Komponente', 'Version / Tag', 'Quelle'], runtime)}
    <h4>Python-Pakete</h4>${table(['Paket', 'Installiert', 'Buildvorgabe'], dependencies)}
    <h4>Raspberry Pis</h4>
    <p>Der Leserdienst meldet die installierten Paketversionen ungefähr einmal pro Minute. Die Tabelle zeigt den zuletzt empfangenen Stand. Der aktuelle Verbindungsstatus steht unter <strong>Verkaufspunkte</strong>.</p>
    <ul>${Object.entries(doc.terminal_reported_at || {}).map(([id, at]) =>
      `<li>Terminal ${esc(id.toUpperCase())} · ${at ? esc(dateTime(at)) : 'Noch kein Paketstand empfangen'}</li>`).join('')}</ul>
    ${table(['Paket', 'Aufgabe', ...Object.keys(doc.terminals).map(id => 'Terminal ' + esc(id.toUpperCase()))], terminalVersions)}
    <h4>Browser-Oberfläche</h4><p>Die Oberfläche verwendet HTML, CSS und JavaScript-Module. Fraunces und Plus Jakarta Sans liegen als WOFF2-Dateien im Paket. Die Schriften und die Dokumentation werden lokal ausgeliefert.</p>
  </section>`;
}

function apiReference(operations) {
  return `<section id="tech-api"><h3>API-Endpunkte <small class="pill">${operations.length}</small></h3>
    <p>Browseraufrufe mit POST erfordern dieselbe HTTPS-Origin und einen JSON-Body. Die Kiosk-API prüft das Geräte-Cookie und bei zustandsabhängigen Aktionen zusätzlich die Kiosksitzung und den Besuchsschlüssel. Der Leserdienst authentifiziert sich separat. Die Verwaltungs-API verlangt eine Admin-Sitzung. Admin-Konten, Verkaufspunkte samt Kopplungen und Pi-Profilen, der PayPal-Empfängerlink und die Terminal-Vorschau sind dem Super-Admin vorbehalten. Die Vorschau liest das Standortsortiment und berechnet Testwarenkörbe mit derselben Preislogik wie der Kiosk. Testkonten und Testbuchungen bleiben im Browser-Tab.</p>
    <p>API-Antworten sind in der Regel JSON, Downloads liefern XLSX, SVG oder private Pi-Profile als JSON. In der Spalte Eingaben markiert <code>?</code> optionale Felder. Pfade ohne Body können bei POST mit <code>{}</code> aufgerufen werden.</p>
    ${Object.entries(areas).map(([title, scopes]) => `<details class="tech-api-group" ${title === 'Verwaltung' ? 'open' : ''}>
      <summary>${title}</summary>
      ${table(['Methode und Pfad', 'Zugriff', 'Zweck', 'Eingaben'], operations.filter(row => scopes.includes(row[2])).map(([method, path, scope, use, fields]) =>
        [`<span class="pill ${method === 'POST' ? 'good' : ''}">${esc(method)}</span> <code>${esc(path)}</code>`, esc(scope), esc(use), `<code>${esc(fields)}</code>`]))}
    </details>`).join('')}
    <h4>Statuscodes</h4>
    <dl class="tech-status-codes">
      <div><dt><code>400</code></dt><dd>Ungültige Eingabe</dd></div>
      <div><dt><code>401</code></dt><dd>Fehlende oder abgelaufene Sitzung</dd></div>
      <div><dt><code>403</code></dt><dd>Fehlende Berechtigung oder unzulässige Origin</dd></div>
      <div><dt><code>404</code></dt><dd>Unbekannte Ressource</dd></div>
      <div><dt><code>405</code></dt><dd>Falsche Methode</dd></div>
      <div><dt><code>409</code></dt><dd>Konflikt</dd></div>
      <div><dt><code>429</code></dt><dd>Anmeldeversuche begrenzt</dd></div>
      <div><dt><code>503</code></dt><dd>Dienst vorübergehend nicht verfügbar</dd></div>
    </dl>
  </section>`;
}

export function technicalPanel(doc) {
  return `<article class="technical-docs">
    <header class="tech-header"><p class="eyebrow">KoSTbar · ${esc(doc.deployment)}</p><h2>Technische Dokumentation</h2>
      <p>Architektur, Datenfluss, Abhängigkeiten und API der laufenden Installation.</p></header>
    <nav class="tech-nav" aria-label="Abschnitte der Dokumentation">
      <a href="#tech-arch">Architektur</a><a href="#tech-flow">Datenfluss</a>
      <a href="#tech-versions">Versionen</a><a href="#tech-api">API-Endpunkte</a>
    </nav>
    ${architecture(doc.deployment === 'Synology')}${flow}${packageVersions(doc)}${apiReference(doc.operations)}
  </article>`;
}
