import { formattedTerms, standLabel, termsText } from './terms.js';
import { downloadPrintDocument, termsPrintDate } from './print-export.js';
import { technicalPanel } from './technical-docs.js';
import { categoryIcons, icon } from './art.js';
import { api, dateTime, esc, euro, eurosToCents, idempotencyKey, notify, personLabel } from './shared.js';

const admin = document.getElementById('admin');
const top = document.getElementById('top-actions');
const editor = document.getElementById('editor');
const tabs = {journal: 'Kassenbuch', payments: 'PayPal', people: 'Benutzer', products: 'Sortiment',
  sites: 'Verkaufspunkte', report: 'Auswertung', terms: 'Nutzungshinweise', privacy: 'Datenschutz',
  admins: 'Administratoren', audit: 'Änderungsprotokoll', technical: 'Technik', preview: 'Terminal-Vorschau'};
const navigation = [
  ['Finanzen', ['journal', 'payments', 'report']],
  ['people'],
  ['Verkauf', ['products', 'sites', 'preview']],
  ['Verwaltung', ['admins', 'terms', 'privacy', 'audit', 'technical']],
];
const kinds = {purchase: 'Kauf', payment: 'Zahlung', correction: 'Korrektur', reversal: 'Storno'};
const iconDefaults = {cold: 'water', hot: 'coffee', snack: 'salami', sweet: 'bar'};
const peopleSortKeys = {Name: 'last', Vorname: 'first', Referat: 'department', Saldo: 'balance'};
const peopleCollator = new Intl.Collator('de-DE', {numeric: true, sensitivity: 'base'});
let session = null;
let overview;
let tab = 'journal';
let journal = {entries: [], next: null};
let audit = {entries: [], next: null};
let auditPage = 0;
let auditCursors = [null];
let productCategory = 'all';
let payments = {payments: [], next: null};
let paymentStatus = 'pending';
let paypalSettings;
let report;
let reportMonth = '';
let reportTerminal = '';
let terms;
let privacy;
let technical;
let admins = [];
let selectedPerson = '';
let selectedTerminal = '';
let search = '';
let peopleSort = {key: 'last', direction: 'ascending'};
let captureTimer;
let capturing = null;
let modalAction;
let busy = false;
let adminTimer;

function signIn() {
  session = null;
  tab = 'journal';
  audit = {entries: [], next: null};
  auditPage = 0;
  auditCursors = [null];
  clearTimeout(adminTimer);
  if (editor.open) editor.close();
  top.replaceChildren();
  admin.innerHTML = `<section class="center-card admin-login"><div class="round-icon">${icon('lock', 26)}</div>
    <p class="eyebrow">ZUGANG FÜR DAS KASSEN-TEAM</p><h1>Verwaltung</h1>
    <p class="muted">Melde dich mit deinem Administratorkonto an.</p>
    <form id="login-form">
      <label>Anmeldename<input name="name" maxlength="32" autocomplete="username" required></label>
      <label>Passwort<input type="password" name="password" maxlength="256" autocomplete="current-password" required></label>
      <button class="button primary" type="submit">Anmelden ${icon('arrow', 19)}</button>
      <p id="login-error" class="form-error" role="alert"></p>
    </form></section>`;
}

function handleError(error) {
  if (error.status === 401) signIn();
  notify(error.message);
}

async function loadJournal(append = false) {
  const params = new URLSearchParams();
  if (selectedPerson) params.set('person', selectedPerson);
  if (selectedTerminal) params.set('terminal', selectedTerminal);
  if (append && journal.next) params.set('before', journal.next);
  const result = await api('/api/admin/journal?' + params);
  journal = {entries: append ? [...journal.entries, ...result.entries] : result.entries, next: result.next};
}

async function loadPayments(append = false) {
  const params = new URLSearchParams({status: paymentStatus});
  if (append && payments.next) params.set('before', payments.next);
  const result = await api('/api/admin/payments?' + params);
  payments = {payments: append ? [...payments.payments, ...result.payments] : result.payments, next: result.next};
}

async function loadAudit(page, cursor) {
  audit = await api('/api/admin/audit' + (cursor ? '?before=' + encodeURIComponent(cursor) : ''));
  auditPage = page;
  auditCursors[page] = cursor;
}

async function loadTab() {
  if (tab === 'journal') await loadJournal();
  if (tab === 'audit') {
    await loadAudit(0, null);
    auditCursors.length = 1;
  }
  if (tab === 'payments') {
    await loadPayments();
    if (session.super_admin) paypalSettings = await api('/api/admin/paypal-settings');
  }
  if (tab === 'terms') terms = await api('/api/admin/terms');
  if (tab === 'privacy') privacy = await api('/api/admin/privacy');
  if (tab === 'admins') admins = (await api('/api/admin/admins')).admins;
  if (tab === 'technical') technical = await api('/api/admin/technical-docs');
  if (tab === 'report') {
    const params = new URLSearchParams({month: reportMonth, terminal: reportTerminal});
    report = await api('/api/admin/report?' + params);
    reportMonth = report.month;
  }
}

function sessionTimer() {
  if (!session) return;
  clearTimeout(adminTimer);
  // Clear displayed data even if the connection drops. The server also expires the cookie.
  adminTimer = setTimeout(() => {
    if (!session) return;
    api('/api/admin/logout', {}).catch(() => {});
    signIn();
    notify('Die Verwaltung wurde wegen Inaktivität geschlossen.');
  }, 590000);
}

async function refresh(message) {
  overview = await api('/api/admin/overview');
  await loadTab();
  render();
  sessionTimer();
  if (message) notify(message);
}

function personName(person) {
  return esc(personLabel(person));
}

function rowAction(action, value, label, glyph, tone = 'neutral', description = '') {
  const tooltip = description ? ` title="${esc(description)}" aria-label="${esc(label + ' · ' + description)}"` : '';
  return `<button type="button" class="button compact row-action action-${tone}" data-${action}="${esc(value)}"${tooltip}>${icon(glyph, 15)}${label}</button>`;
}

function exportLink(path, label, description) {
  return `<a class="button compact row-action action-good export-action" href="/api/admin/${path}" download
    title="${description}" aria-label="${label} als Excel-Datei">${icon('table', 15)}${label}</a>`;
}

function amount(cents) {
  return `<span class="amount ${cents < 0 ? 'negative' : ''}">${euro(cents)}</span>`;
}

function columnHeading(label) {
  return `<th scope="col">${label}</th>`;
}

function table(labels, rows, empty, heading = columnHeading) {
  if (!rows) return `<p class="admin-empty">${empty}</p>`;
  return '<div class="table-wrap"><table><thead><tr>' + labels.map(heading).join('') +
    '</tr></thead><tbody>' + rows + '</tbody></table></div>';
}

function journalPanel() {
  const opts = overview.people.map(p =>
    `<option value="${p.id}" ${String(p.id) === selectedPerson ? 'selected' : ''}>${personName(p)}</option>`).join('');
  const rows = journal.entries.map(j => {
    const items = j.items.flatMap(item => {
      const bonus = item.bonus_quantity ?? 0;
      const paid = item.quantity - bonus;
      return [
        paid ? esc(paid + ' × ' + item.name) + ' <span class="muted">à ' + euro(item.price) + '</span>' : '',
        bonus ? esc(bonus + ' × ' + item.name) + ' <span class="history-bonus">Sammelkartenbonus · ' + euro(0) + '</span>' : '',
      ].filter(Boolean);
    }).join('<br>');
    const note = !items || j.kind === 'reversal' ? esc(j.note || '') : '';
    const details = [items, note].filter(Boolean).join('<br>');
    const reference = j.reverses ? `<small>Zu Kauf #${j.reverses}</small>` : j.reversed_by ? `<small>Storno #${j.reversed_by}</small>` : '';
    const tone = j.kind === 'purchase' ? ' good' : j.kind === 'reversal' ? ' danger' : '';
    return `<tr><td><strong>#${j.id}</strong><small>${dateTime(j.at)}</small></td><td>${personName(j)}</td><td>${j.terminal ? esc(historicalSites()[j.terminal]) : '—'}</td>
      <td><span class="pill${tone}">${kinds[j.kind]}</span>${reference}</td><td>${details}${j.actor ? '<small>Von ' + esc(j.actor) + '</small>' : ''}</td>
      <td class="num">${amount(j.cents)}</td><td>${j.kind === 'purchase' && !j.reversed_by ? rowAction('reverse', j.id, 'Stornieren', 'undo', 'danger') : ''}</td></tr>`;
  }).join('');
  return `<div class="panel-heading"><div><h2>Kassenbuch</h2><p>Einzelbuchungen der letzten 90 Tage.</p></div>
    <div class="journal-filters filter-pair"><label class="filter">Konto<select id="journal-person"><option value="">Alle Konten</option>${opts}</select></label>
    <label class="filter">Verkaufspunkt<select id="journal-terminal"><option value="">Alle</option>${options(historicalSites(), selectedTerminal)}</select></label></div></div>
    ${table(['Buchung', 'Konto', 'Verkaufspunkt', 'Art', 'Positionen / Grund', 'Betrag', 'Aktion'], rows, 'Für diese Auswahl gibt es noch keine Buchungen.')}
    ${journal.next ? '<button class="button outline compact more" data-more>Ältere Buchungen</button>' : ''}`;
}

function consentCell(person) {
  return person.terms_current ? '<span class="pill good">Bestätigt</span>' : '<span class="pill off">Offen</span>';
}

function peopleHeading(label) {
  const key = peopleSortKeys[label];
  if (!key) return columnHeading(label);
  const direction = peopleSort.key === key ? peopleSort.direction : null;
  const arrow = direction === 'ascending' ? '↑' : direction === 'descending' ? '↓' : '↕';
  return `<th scope="col"${direction ? ` aria-sort="${direction}"` : ''}>
    <button type="button" class="column-sort" data-people-sort="${key}">${label} <span aria-hidden="true">${arrow}</span></button>
  </th>`;
}

function comparePeople(a, b) {
  const {key, direction} = peopleSort;
  const {compare} = peopleCollator;
  const order = key === 'balance' ? a.balance - b.balance : compare(a[key], b[key]);
  return (direction === 'ascending' ? order : -order) ||
    compare(a.last, b.last) || compare(a.first, b.first) || a.id - b.id;
}

function peopleRows() {
  const words = search.trim().toLocaleLowerCase('de-DE').split(/\s+/);
  return overview.people.filter(p => {
    const label = personLabel(p).toLocaleLowerCase('de-DE');
    return words.every(word => label.includes(word));
  }).sort(comparePeople).map(p => {
    const medium = overview.card_media[p.card_medium];
    const type = overview.card_types[p.card_type];
    return `<tr><td><strong>${esc(p.last)}</strong><small>Konto #${p.id} · seit ${dateTime(p.created)}</small>
    <small>${esc(medium || type || 'Kartentyp nicht bestimmt')}${medium && type ? ' · ' + esc(type) : ''}</small></td>
    <td>${esc(p.first)}</td><td>${esc(p.department || '—')}</td>
    <td><span class="pill ${p.active ? 'good' : 'off'}">${p.closed_at ? 'Geschlossen' : p.active ? 'Aktiv' : 'Gesperrt'}</span></td>
    <td class="num">${amount(p.balance)}</td>
    <td><strong>${p.loyalty.stamps}/${p.loyalty.target}</strong>
      <small>${p.loyalty.redeemed} ${p.loyalty.redeemed === 1 ? 'Gratisgetränk' : 'Gratisgetränke'} eingelöst</small></td>
    <td class="consent-status">${consentCell(p)}</td><td class="row-actions"><div class="action-list">
      ${rowAction('book', p.id, 'Buchung', 'plus', 'good')}
      ${rowAction('person', p.id, 'Bearbeiten', 'edit')}
      ${p.closed_at ? '' : rowAction('capture', p.id, 'Karte ersetzen', 'card', 'info')}
      ${p.closed_at ? '' : rowAction('close-account', p.id, 'Konto schließen', 'close', 'danger')}
      ${rowAction('show', p.id, 'Verlauf', 'history')}
      ${exportLink('export-account?person=' + p.id, 'Export', 'Kontoauszug als Excel-Datei')}
      ${p.manual_enabled ? rowAction('reset-pin', p.id, 'PIN zurücksetzen', 'key', 'warn', 'PIN zurücksetzen') : ''}</div></td></tr>`;
  }).join('');
}

function peopleTable() {
  return table(['Name', 'Vorname', 'Referat', 'Status', 'Saldo', 'Sammelkarte', 'Zustimmung', 'Aktionen'],
    peopleRows(), 'Keine passenden Konten.', peopleHeading);
}

function peoplePanel() {
  const current = overview.terms_date ? ' · Nutzungshinweise: ' + standLabel(overview.terms_date) : '';
  return `<div class="panel-heading"><div><h2>Benutzer</h2><p>Konten, Salden, Sammelkarten und Zustimmungen${esc(current)}</p></div>
    <div class="journal-filters"><label class="filter">Name oder Referat suchen<input id="person-search" value="${esc(search)}" type="search" placeholder="Name, Referat"></label>
    ${exportLink('export-balances', 'Gesamtexport', 'Saldenliste als Excel-Datei')}</div></div>
    <div id="people-table">${peopleTable()}</div>`;
}

function productsPanel() {
  const products = overview.products.filter(p => productCategory === 'all' || p.category === productCategory);
  const filters = Object.entries({all: 'Alle', ...overview.categories}).map(([key, label]) =>
    `<button type="button" data-product-category="${key}" aria-pressed="${key === productCategory}">${key === 'all' ? '' : icon(categoryIcons[key], 16) + ' '}${esc(label)}</button>`
  ).join('');
  const rows = products.map(p => `<tr><td><strong>${esc(p.name)}</strong></td>
    <td><span class="category-cell">${icon(categoryIcons[p.category], 18)} ${esc(overview.categories[p.category])}</span></td>
    <td class="num">${amount(p.cents)}</td><td>${p.terminals.map(site => esc(overview.terminals[site])).join(', ') || 'Keiner'}</td>
    <td><span class="pill ${p.active && p.terminals.length ? 'good' : 'off'}">${p.active ? (p.terminals.length ? 'Im Sortiment' : 'Ohne Zuordnung') : 'Archiviert'}</span></td>
    <td class="row-actions">${rowAction('product', p.id, 'Bearbeiten', 'edit')}
    ${rowAction('archive', p.id, p.active ? 'Archivieren' : 'Reaktivieren', p.active ? 'close' : 'undo', p.active ? 'warn' : 'good')}
    ${session.super_admin ? rowAction('delete-product', p.id, 'Dauerhaft ausblenden', 'trash', 'danger') : ''}</td></tr>`).join('');
  return `<div class="panel-heading"><div><h2>Sortiment</h2><p>Produkte, Kategorien und Preise pflegen.</p></div>
    <button class="button primary compact" data-new>${icon('plus', 18)} Neues Produkt</button></div>
    <nav class="admin-tabs product-filters" aria-label="Sortiment nach Kategorie filtern">${filters}</nav>
    ${table(['Produkt', 'Kategorie', 'Preis', 'Verkaufspunkte', 'Status', 'Aktionen'], rows, 'Keine Produkte in dieser Auswahl.')}`;
}

function paymentsPanel() {
  const labels = {pending: 'Offen', confirmed: 'Bestätigt', rejected: 'Abgelehnt'};
  const rows = payments.payments.map(p => `<tr><td><strong>${esc(p.reference)}</strong><small>${dateTime(p.created)}</small></td>
    <td>${personName(p)}</td><td>${esc(historicalSites()[p.terminal])}</td><td class="num">${amount(p.cents)}</td>
    <td class="row-actions">${p.status === 'pending' ?
      rowAction('paypal-confirm', p.id, 'Eingang bestätigen', 'check', 'good') +
      rowAction('paypal-reject', p.id, 'Ablehnen', 'close', 'danger') :
      `<span class="pill ${p.status === 'confirmed' ? 'good' : 'off'}">${labels[p.status]}</span>
       ${p.credited != null ? amount(p.credited) : ''}<small>${dateTime(p.resolved)} · ${esc(p.actor)}
       ${p.transaction_ref ? '<br>Transaktion ' + esc(p.transaction_ref) : ''}${p.note ? '<br>' + esc(p.note) : ''}</small>`}</td></tr>`).join('');
  return `<div class="panel-heading"><div><h2>PayPal-Zahlungen</h2><p>Vergleiche die Referenz mit dem tatsächlichen Zahlungseingang in PayPal.</p></div>
    <label class="filter">Status<select id="payment-status">${options(labels, paymentStatus)}</select></label></div>
    ${session.super_admin ? `<section class="paypal-settings">
      <div><h3>PayPal.Me-Empfänger</h3><p>${esc(paypalSettings.link || 'PayPal ist deaktiviert.')}</p></div>
      <button type="button" class="button outline compact" data-paypal-settings>${icon('edit', 18)} Empfänger bearbeiten</button>
    </section>` : ''}
    ${table(['Referenz', 'Konto', 'Verkaufspunkt', 'Gemeldet', 'Status / Aktion'], rows, 'Keine Zahlungen mit diesem Status.')}
    ${payments.next ? '<button class="button outline compact more" data-paypal-more>Weitere Zahlungen</button>' : ''}`;
}

function resolvePaypal(id, confirm) {
  const payment = payments.payments.find(p => p.id === id);
  const info = `<p><strong>${personName(payment)}</strong> · ${esc(payment.reference)} · gemeldet ${euro(payment.cents)}</p>
    ${payment.recipient_link ? `<p>Empfänger ${esc(payment.recipient_link)}</p>` : ''}`;
  if (confirm) {
    modal('PayPal-Eingang bestätigen', info + `<p>Prüfe den Zahlungseingang in PayPal. Der folgende Betrag wird gutgeschrieben.</p>
      <label>Tatsächlich eingegangener Betrag in Euro<input name="value" required inputmode="decimal"
        value="${(payment.cents / 100).toFixed(2).replace('.', ',')}"></label>
      <label>PayPal-Transaktions-ID<input name="transaction" maxlength="100" required></label>`,
      'Gutschrift buchen', fields => api('/api/admin/paypal-confirm', {id, cents: eurosToCents(fields.get('value')),
        transaction: fields.get('transaction')}));
  } else {
    modal('PayPal-Meldung ablehnen', info + '<label>Begründung<input name="note" maxlength="240" required></label>',
      'Meldung ablehnen', fields => api('/api/admin/paypal-reject', {id, note: fields.get('note')}));
  }
}

function reportPanel() {
  const rows = report.products.map(p => `<tr><td><strong>${esc(p.name)}</strong></td><td class="num">${p.sold}</td>
    <td class="num">${p.returned}</td><td class="num">${p.sold - p.returned}</td><td class="num">${amount(p.net)}</td></tr>`);
  if (report.unallocated) rows.push(`<tr><td><strong>Stornos ohne Produktzuordnung</strong></td>
    <td class="num">—</td><td class="num">—</td><td class="num">—</td><td class="num">${amount(-report.unallocated)}</td></tr>`);
  const coverage = {
    partial: 'Die Monatssummen enthalten auch Umsätze, deren Einzelbuchungen bereits gelöscht wurden.',
    expired: 'Für diesen Monat stehen nur noch die Monatssummen zur Verfügung.',
    complete: 'Verkäufe und Stornos im gewählten Kalendermonat.',
  };
  return `<div class="panel-heading"><div><h2>Monatsauswertung</h2><p>${coverage[report.coverage]}</p></div>
    <div class="journal-filters filter-pair"><label class="filter">Monat<input type="month" id="report-month" value="${esc(reportMonth)}"></label>
    <label class="filter">Verkaufspunkt<select id="report-terminal"><option value="">Alle</option>${options(historicalSites(), reportTerminal)}</select></label></div></div>
    <div class="metrics report-metrics"><div><small>VERKÄUFE</small><strong>${euro(report.gross)}</strong></div>
    <div><small>STORNOS</small><strong>${euro(report.reversed)}</strong></div>
    <div><small>UMSATZ NACH STORNOS</small><strong>${euro(report.gross - report.reversed)}</strong></div></div>
    <p class="hint">${report.orders} Kaufbuchungen im gewählten Zeitraum. Mengen enthalten auch Gratisgetränke. Im Umsatz zählen die tatsächlich berechneten Preise. Produktnamen entsprechen der Bezeichnung beim Kauf; Umbenennungen erscheinen in getrennten Zeilen.</p>
    ${table(['Produkt', 'Ausgegeben', 'Storniert', 'Ausgegeben abzüglich Stornos', 'Umsatz nach Stornos'], rows.join(''), 'Keine Verkäufe oder Stornos in diesem Zeitraum.')}`;
}

function termsPanel() {
  const isPrivacy = tab === 'privacy';
  const draft = isPrivacy ? privacy.body : termsText(terms);
  const title = isPrivacy ? 'Datenschutzerklärung' : 'Nutzungshinweise';
  const status = esc(standLabel(isPrivacy ? privacy.date : terms.date)) + (isPrivacy && privacy.template ? ' · Vorlage' : '');
  return `<div class="panel-heading"><div><h2>${title} bearbeiten</h2><p>${status}</p></div></div>
    <form id="terms-form" class="terms-editor" data-document="${isPrivacy ? 'privacy' : 'terms'}">
      <label>${isPrivacy ? 'Standdatum' : 'Standdatum für den Ausdruck'}<input name="date" type="date" value="${esc(isPrivacy ? privacy.date : (terms.date || termsPrintDate(terms.version)))}"${isPrivacy ? ' required' : ''}></label>
      <div class="editor-toolbar" role="group" aria-label="Formatierung">
        <button class="button outline compact" type="button" data-format="heading">Überschrift</button>
        <button class="button outline compact" type="button" data-format="subheading">Zwischenüberschrift</button>
        <button class="button outline compact" type="button" data-format="bold"><strong>Fett</strong></button>
        <button class="button outline compact" type="button" data-format="underline"><u>Unterstrichen</u></button>
        <button class="button outline compact" type="button" data-format="list">Aufzählung</button>
      </div>
      <label>Text<textarea id="terms-draft" name="body" rows="14" maxlength="16000" required>${esc(draft)}</textarea></label>
      <div class="terms-preview"><h3>Vorschau</h3><div id="terms-preview">${formattedTerms(draft)}</div></div>
      <p class="hint">${isPrivacy ? 'Ergänze die Betreiberangaben in den markierten Feldern. Änderungen erscheinen direkt an allen Terminals.' :
        'Bei einer neuen Fassung bestätigen registrierte Personen die Hinweise beim nächsten Zugriff erneut.'}</p>
      <p class="form-error" role="alert"></p>
      <div class="editor-toolbar">
        <button type="submit" class="button primary">${isPrivacy ? 'Datenschutzerklärung speichern' : 'Neue Fassung veröffentlichen'}</button>
        <button type="button" class="button outline" data-document-export>HTML für Druck exportieren</button>
        <button type="button" class="button outline" data-document-export="published">Veröffentlichte Fassung exportieren</button>
      </div>
      <p class="hint">Der Export verwendet den aktuellen Editorinhalt. Öffne die HTML-Datei im Browser zum Weiterbearbeiten oder Drucken.</p>
    </form>`;
}

function formatDraft(kind) {
  const field = document.getElementById('terms-draft');
  const start = field.selectionStart, end = field.selectionEnd;
  const selected = field.value.slice(start, end);
  if (kind === 'bold' || kind === 'underline') {
    const mark = kind === 'bold' ? '**' : '__';
    const text = selected || 'Text';
    field.setRangeText(mark + text + mark, start, end);
    field.setSelectionRange(start + mark.length, start + mark.length + text.length);
  } else {
    const prefix = {heading: '## ', subheading: '### ', list: '- '}[kind];
    const lineStart = start ? field.value.lastIndexOf('\n', start - 1) + 1 : 0;
    const newline = field.value.indexOf('\n', end);
    const lineEnd = newline === -1 ? field.value.length : newline;
    const lines = field.value.slice(lineStart, lineEnd) || (kind === 'list' ? 'Listenpunkt' : 'Überschrift');
    const text = lines.split('\n').map(line => prefix + line.replace(/^(?:#{2,3}|-) /, '')).join('\n');
    field.setRangeText(text, lineStart, lineEnd);
    field.setSelectionRange(lineStart + prefix.length, lineStart + text.length);
  }
  field.focus();
  field.dispatchEvent(new Event('input', {bubbles: true}));
}

function adminsPanel() {
  const canManage = session.super_admin;
  const rows = admins.map(account => `<tr><td><strong>${esc(account.name)}</strong></td>
    <td><span class="pill ${account.super_admin ? 'good' : ''}">${account.super_admin ? 'Super-Admin' : 'Administrator'}</span></td>
    <td>${esc(account.first) || '—'}</td><td>${esc(account.last) || '—'}</td><td>${esc(account.description) || '—'}</td>
    ${canManage ? `<td class="row-actions">${rowAction('edit-admin', account.name, 'Bearbeiten', 'edit')}
      ${rowAction('reset-admin-password', account.name, 'Passwort zurücksetzen', 'key', 'warn')}
      ${account.super_admin ? '' : rowAction('remove-admin', account.name, 'Löschen', 'trash', 'danger')}</td>` : ''}</tr>`).join('');
  const labels = ['Anmeldename', 'Rolle', 'Vorname', 'Nachname', 'Beschreibung'];
  if (canManage) labels.push('Aktionen');
  return `<div class="panel-heading"><div><h2>Administratoren</h2><p>${canManage ? 'Persönliche Zugänge für das Kassen-Team.' :
    'Der Super-Admin verwaltet die Zugänge. Dein eigenes Passwort kannst du oben ändern.'}</p></div>
    ${canManage ? '<button class="button primary compact" data-add-admin>' + icon('plus', 18) + ' Admin anlegen</button>' : ''}</div>
    ${table(labels, rows, 'Keine Administratoren gefunden.')}`;
}

function passwordFields() {
  const minimum = 12;
  return `<label>Neues Passwort (mindestens ${minimum} Zeichen)<input type="password" name="password" required minlength="${minimum}" maxlength="256" autocomplete="new-password"></label>
    <label>Neues Passwort wiederholen<input type="password" name="repeat" required minlength="${minimum}" maxlength="256" autocomplete="new-password"></label>`;
}

function editAdmin(previous) {
  const account = admins.find(row => row.name === previous);
  modal(account ? 'Administrator bearbeiten' : 'Administrator anlegen',
    `<label>Anmeldename<input name="name" required autocomplete="off" minlength="3" maxlength="32" value="${esc(account?.name)}"></label>
    <div class="field-pair"><label>Vorname<input name="first" maxlength="60" value="${esc(account?.first)}" required></label>
    <label>Nachname<input name="last" maxlength="60" value="${esc(account?.last)}" required></label></div>
    <label>Beschreibung (optional)<input name="description" maxlength="240" value="${esc(account?.description)}"></label>
    ${account ? '' : passwordFields() + '<p class="hint">Das neue Konto erhält Zugriff auf die gesamte Verwaltung.</p>'}`,
    account ? 'Speichern' : 'Admin anlegen', fields => api('/api/admin/' + (account ? 'edit-admin' : 'add-admin'),
      {...Object.fromEntries(fields), previous}));
}

function removeAdmin(name) {
  modal('Administrator löschen', `<p>Zugang für <strong>${esc(name)}</strong> löschen? Frühere Änderungen bleiben bis zum Ablauf ihrer Frist im Protokoll sichtbar.</p>`,
    'Konto löschen', () => api('/api/admin/remove-admin', {name}));
}

function resetAdminPassword(name) {
  modal('Admin-Passwort zurücksetzen',
    `<p>Lege ein neues Passwort für <strong>${esc(name)}</strong> fest. Aktive Sitzungen dieses Kontos werden beendet.</p>` +
    passwordFields(),
    'Passwort zurücksetzen', fields => api('/api/admin/reset-admin-password', {...Object.fromEntries(fields), name}));
}

function changePassword() {
  modal('Eigenes Passwort ändern',
    '<label>Bisheriges Passwort<input type="password" name="current" required maxlength="256" autocomplete="current-password"></label>' +
    passwordFields() + '<p class="hint">Nach dem Speichern meldest du dich mit dem neuen Passwort erneut an.</p>',
    'Passwort ändern', fields => api('/api/admin/change-password', Object.fromEntries(fields)));
}

function resetPin(id) {
  const person = overview.people.find(p => p.id === id);
  modal('PIN zurücksetzen', `<p><strong>${personName(person)}</strong> vergibt bei der nächsten Anmeldung mit Ausweis selbst eine neue PIN. Aktive Sitzungen des Kontos werden beendet.</p>`,
    'PIN zurücksetzen', () => api('/api/admin/reset-pin', {id}));
}

function auditValue(value) {
  if (Array.isArray(value)) return value.join(', ');
  return String(value ?? '') || '—';
}

function auditCell(snapshot, other, current, fields) {
  if (!fields.length) return '—';
  return '<dl class="audit-values">' + fields.map(field => {
    const exists = Object.hasOwn(snapshot || {}, field);
    const also = Object.hasOwn(other || {}, field);
    const value = exists ? auditValue(snapshot[field]) : '—';
    const changed = exists && also && JSON.stringify(snapshot[field]) !== JSON.stringify(other[field]);
    const status = changed ? 'changed' : exists && !also ? (current ? 'added' : 'removed') : '';
    return `<div class="${status ? 'audit-' + status : ''}"><dt>${esc(field)}</dt><dd>${esc(value)}</dd></div>`;
  }).join('') + '</dl>';
}

function auditPanel() {
  const rows = audit.entries.map(row => {
    const fields = [...new Set([...Object.keys(row.old_state || {}), ...Object.keys(row.new_state || {})])];
    const author = row.actor_label ? `<strong>${esc(row.actor_label)}</strong><small>${esc(row.actor)}</small>` : esc(row.actor);
    return `<tr><td>${dateTime(row.at)}</td><td>${author}</td><td>${esc(row.detail)}</td>
      <td>${auditCell(row.old_state, row.new_state, false, fields)}</td>
      <td>${auditCell(row.new_state, row.old_state, true, fields)}</td></tr>`;
  }).join('');
  return `<div class="panel-heading"><div><h2>Änderungsprotokoll</h2><p>Verwaltungsänderungen der letzten 180 Tage · bis zu 100 Einträge pro Seite.</p></div></div>
    <p class="audit-legend"><span class="audit-removed">Gelöscht</span><span class="audit-changed">Geändert</span><span class="audit-added">Hinzugefügt</span>
      <span class="muted">Ältere Einträge können ohne Vergleichswerte vorliegen.</span></p>
    ${table(['Zeitpunkt', 'Durchgeführt von', 'Änderung', 'Vorheriger Stand', 'Neuer Stand'], rows, 'Es sind noch keine Änderungen vorhanden.')}
    ${auditPage || audit.next ? `<nav class="audit-pagination" aria-label="Seiten des Änderungsprotokolls">
      <button class="button outline compact" type="button" data-audit-prev ${auditPage ? '' : 'disabled'}>Neuere Änderungen</button>
      <span aria-live="polite">Seite ${auditPage + 1}</span>
      <button class="button outline compact" type="button" data-audit-next ${audit.next ? '' : 'disabled'}>Ältere Änderungen</button></nav>` : ''}`;
}

function sitesPanel() {
  const canManage = session.super_admin;
  const rows = Object.entries(overview.terminals).map(([id, label]) =>
    `<tr><td>${esc(id.toUpperCase())}</td><td><strong>${esc(label)}</strong></td>
    <td data-terminal-status="${esc(id)}"><span class="pill">Wird geprüft …</span></td>
    ${canManage ? `<td><div class="action-list">${rowAction('edit-site', id, 'Umbenennen', 'edit')}
    <a class="button compact row-action" href="/api/admin/terminal-profile?terminal=${encodeURIComponent(id)}" download>Pi-Profil herunterladen</a>
    ${rowAction('pair-site', id, 'Koppeln', 'key')}
    ${rowAction('unpair-site', id, 'Kopplung lösen', 'key', 'warn')}
    ${rowAction('delete-site', id, 'Löschen', 'trash', 'danger')}</div></td>` : ''}</tr>`).join('');
  return `<div class="panel-heading"><div><h2>Verkaufspunkte</h2>
    <p>Der Status zeigt die Verbindung des Kiosk-Browsers. Der Kartenleser wird separat angezeigt.</p></div>
    ${canManage ? `<button type="button" class="button primary compact" data-create-site>${icon('plus', 18)} Verkaufspunkt anlegen</button>` : ''}</div>
    ${table(['Kennung', 'Anzeigename', 'Verbindung', ...(canManage ? ['Aktion'] : [])], rows, 'Keine Verkaufspunkte vorhanden.')}`;
}

async function refreshTerminalStatus() {
  if (!session || tab !== 'sites' || document.hidden) return;
  const currentSession = session;
  const cells = admin.querySelectorAll('[data-terminal-status]');
  if (!cells.length) return;
  try {
    const statuses = await api('/api/admin/terminal-status');
    if (session !== currentSession || tab !== 'sites') return;
    for (const cell of cells) {
      const status = statuses[cell.dataset.terminalStatus];
      if (!status) continue;
      cell.innerHTML = `<span class="pill ${status.online ? 'terminal-online' : 'terminal-offline'}">${status.online ? 'Aktiv' : 'Inaktiv'}</span>
        <small>${status.reader ? 'Kartenleser verbunden' : 'Kartenleser getrennt'}</small>
        <small>${status.paired ? 'Browser gekoppelt' : 'Browser noch nicht gekoppelt'}</small>`;
      const row = cell.closest('tr');
      row.querySelector('[data-pair-site]').hidden = status.paired;
      row.querySelector('[data-unpair-site]').hidden = !status.paired;
    }
  } catch (error) {
    if (session !== currentSession || tab !== 'sites') return;
    if (error.status === 401) handleError(error);
    else for (const cell of cells) cell.innerHTML = '<span class="pill">Status nicht abrufbar</span>';
  }
}

function createSite() {
  modal('Verkaufspunkt anlegen',
    `<label>Kennung<input name="id" maxlength="32" pattern="[a-z][a-z0-9]*(?:-[a-z0-9]+)*" spellcheck="false" required>
      <small>Zum Beispiel „etage-2“. Die Kennung wird für das Gerät und seine Buchungen verwendet.</small></label>
    <label>Anzeigename<input name="label" maxlength="60" required></label>`,
    'Verkaufspunkt anlegen', fields => api('/api/admin/terminal-create', {id: fields.get('id'), label: fields.get('label')}));
}

function renameSite(id) {
  modal('Verkaufspunkt umbenennen',
    `<label>Anzeigename<input name="label" maxlength="60" value="${esc(overview.terminals[id])}" required></label>`,
    'Speichern', fields => api('/api/admin/terminal', {id, label: fields.get('label')}));
}

function deleteSite(id) {
  modal('Verkaufspunkt löschen',
    `<p><strong>${esc(overview.terminals[id])}</strong> wird vom Kiosk getrennt und aus dem aktiven Sortiment entfernt.
      Buchungen und Auswertungen bleiben erhalten. Die Kennung bleibt für die Historie reserviert.</p>`,
    'Verkaufspunkt löschen', () => api('/api/admin/terminal-delete', {id}));
}

function editPaypalSettings() {
  modal('PayPal.Me-Empfänger bearbeiten',
    `<label>PayPal.Me-Link<input name="link" type="url" maxlength="118" value="${esc(paypalSettings.link)}"
      placeholder="https://paypal.me/DeinName" autocomplete="off" spellcheck="false">
      <small>Leere das Feld, um PayPal am Terminal zu deaktivieren.</small></label>`,
    'Empfänger speichern', fields => api('/api/admin/paypal-settings', {link: fields.get('link')}));
}

function pairSite(id) {
  modal('Kiosk koppeln',
    `<p>${esc(overview.terminals[id])} · Terminal ${id.toUpperCase()}</p>
     <label>Achtstelliger Code<input name="code" inputmode="numeric" pattern="[0-9]{8}" maxlength="8" autocomplete="off" required></label>`,
    'Kopplung bestätigen', fields => api('/api/admin/kiosk-pair', {id, code: fields.get('code')}));
}

function unpairSite(id) {
  modal('Kopplung lösen',
    `<p>Der Browser von ${esc(overview.terminals[id])} wird abgemeldet. Danach kannst du den Kiosk erneut koppeln.</p>`,
    'Kopplung lösen', () => api('/api/admin/kiosk-unpair', {id}));
}

function renderNavigation() {
  const button = key => `<button type="button" data-tab="${key}"${tab === key ? ' aria-current="page"' : ''}>${tabs[key]}</button>`;
  return navigation.map(([label, children]) => children
    ? `<details class="admin-nav-group" name="admin-navigation"><summary${children.includes(tab) ? ' class="current"' : ''}>${label}</summary>
        <div>${children.filter(key => key !== 'preview' || session.super_admin).map(button).join('')}</div></details>`
    : button(label)).join('');
}

function previewPanel() {
  return `<div class="panel-heading"><div><h2>Terminal-Vorschau</h2>
    <p>Teste Anmeldung, Einkauf, Sammelkarte und Zahlungen mit dem aktuellen Sortiment je Verkaufspunkt.</p></div></div>
    <div class="action-list">${Object.entries(overview.terminals).map(([id, label]) =>
      `<a class="button primary compact" href="/api/admin/terminal-preview/page?terminal=${encodeURIComponent(id)}"
        target="_blank" rel="noopener">Terminal ${esc(id.toUpperCase())} · ${esc(label)}</a>`).join('')}</div>`;
}

function render() {
  top.innerHTML = `<span class="operator">${icon('lock', 17)} ${esc(session.name)}${session.super_admin ? ' · Super-Admin' : ''}</span>
    <button class="button outline compact" data-change-password>${icon('key', 17)} Passwort ändern</button>
    <button class="button outline compact" data-admin-logout>${icon('exit', 17)} Abmelden</button>`;
  const outstanding = overview.people.reduce((sum, p) => sum + Math.max(0, -p.balance), 0);
  const credit = overview.people.reduce((sum, p) => sum + Math.max(0, p.balance), 0);
  const panels = {journal: journalPanel, people: peoplePanel, products: productsPanel, audit: auditPanel,
    payments: paymentsPanel, report: reportPanel, terms: termsPanel, privacy: termsPanel, admins: adminsPanel,
    sites: sitesPanel, technical: () => technicalPanel(technical), preview: previewPanel};
  admin.innerHTML = `<section class="admin-title"><div><h1>Administrationsbereich</h1></div></section>
    <div class="metrics"><div><small>OFFENE BETRÄGE</small><strong>${euro(outstanding)}</strong></div>
    <div><small>GUTHABEN</small><strong>${euro(credit)}</strong></div>
    <div><small>AKTIVE KONTEN</small><strong>${overview.people.filter(p => p.active).length}</strong></div></div>
    <nav class="admin-navigation" aria-label="Verwaltungsbereiche">${renderNavigation()}</nav>
    <section class="admin-panel">${panels[tab]()}</section>`;
  for (const group of admin.querySelectorAll('.admin-nav-group')) {
    group.addEventListener('pointerenter', event => {
      if (event.pointerType === 'mouse') group.open = true;
    });
    group.querySelector('summary').addEventListener('click', event => {
      if (event.pointerType === 'mouse' && group.open) event.preventDefault();
    });
    group.addEventListener('pointerleave', event => {
      if (event.pointerType === 'mouse' && !group.querySelector('div').contains(document.activeElement)) {
        group.open = false;
      }
    });
  }
  if (tab === 'sites') refreshTerminalStatus();
}

function modal(title, fields, submitLabel, action) {
  modalAction = action;
  editor.innerHTML = `<form id="edit-form"><h2 id="editor-title">${title}</h2>${fields}
    <p id="edit-error" class="form-error" role="alert"></p>
    <div class="form-actions"><button type="button" class="button outline" data-close>Abbrechen</button>
    <button type="submit" class="button primary">${submitLabel}</button></div></form>`;
  if (!editor.open) editor.showModal();
}

function options(list, selected) {
  return Object.entries(list).map(([key, label]) => `<option value="${key}" ${key === selected ? 'selected' : ''}>${esc(label)}</option>`).join('');
}

function historicalSites() {
  return {...overview.terminals, ...overview.retired_terminals};
}

function editProduct(id) {
  const p = overview.products.find(product => product.id === id);
  modal(p ? 'Produkt bearbeiten' : 'Produkt hinzufügen',
    `<label>Produktname<input name="name" maxlength="80" value="${esc(p?.name)}" required></label>
     <div class="field-pair"><label>Kategorie<select name="category">${options(overview.categories, p?.category)}</select></label>
     <label>Symbol<select name="icon">${options(overview.icons, p?.icon)}</select></label></div>
     <label>Preis in Euro<input name="price" inputmode="decimal" value="${p ? (p.cents / 100).toFixed(2).replace('.', ',') : ''}" placeholder="0,50" required></label>
     <fieldset class="location-options"><legend>Verfügbar an</legend>${Object.entries(overview.terminals).map(([id, label]) =>
        `<label class="check-field"><input type="checkbox" name="terminal" value="${id}" ${p?.terminals.includes(id) ? 'checked' : ''}> ${esc(label)}</label>`).join('')}</fieldset>
     <label class="check-field"><input type="checkbox" name="active" ${p?.active === 0 ? '' : 'checked'}> Im Sortiment anzeigen</label>`,
    'Speichern', fields => api('/api/admin/product', {
      id: p?.id, name: fields.get('name'), category: fields.get('category'), icon: fields.get('icon'),
      cents: eurosToCents(fields.get('price')), active: fields.has('active'), terminals: fields.getAll('terminal'),
    }));
}

function deleteProduct(id) {
  const p = overview.products.find(product => product.id === id);
  modal('Produkt dauerhaft ausblenden',
    `<p><strong>${esc(p.name)}</strong> dauerhaft aus Sortiment und Produktverwaltung ausblenden? Frühere Buchungen und Auswertungen bleiben erhalten. In der Oberfläche lässt sich dieser Schritt nicht rückgängig machen. Zum späteren Reaktivieren bitte stattdessen „Archivieren“ verwenden.</p>`,
    'Dauerhaft ausblenden', () => api('/api/admin/delete-product', {id}));
}

function archiveProduct(id) {
  const p = overview.products.find(product => product.id === id);
  modal(p.active ? 'Produkt archivieren' : 'Produkt reaktivieren',
    '<p><strong>' + esc(p.name) + '</strong> ' + (p.active ? 'aus dem Sortiment nehmen?' : 'im Sortiment anzeigen?') + '</p>',
    p.active ? 'Archivieren' : 'Reaktivieren',
    () => api('/api/admin/product-status', {id, active: !p.active}));
}

function editPerson(id) {
  const p = overview.people.find(person => person.id === id);
  modal('Konto bearbeiten',
    `<div class="field-pair"><label>Vorname<input name="first" maxlength="60" value="${esc(p.first)}" required></label>
     <label>Nachname<input name="last" maxlength="60" value="${esc(p.last)}" required></label></div>
     <label>Referat<input name="department" maxlength="80" value="${esc(p.department)}"></label>
     <label>Kartenträger<select name="card_medium">${options({'': 'Nicht angegeben', ...overview.card_media}, p.card_medium || '')}</select></label>
     <label class="check-field"><input type="checkbox" name="active" ${p.active ? 'checked' : ''} ${p.closed_at ? 'disabled' : ''}> Konto aktiv</label>`,
    'Speichern', fields => api('/api/admin/person', {id, first: fields.get('first'), last: fields.get('last'),
      department: fields.get('department'), card_medium: fields.get('card_medium'), active: fields.has('active')}));
}

function closeAccount(id) {
  const p = overview.people.find(person => person.id === id);
  modal('Konto schließen',
    `<p>Der Zugang für <strong>${personName(p)}</strong> wird sofort gesperrt. Aktueller Saldo ${amount(p.balance)}.</p>
     <p>Die Löschung erfolgt automatisch, sobald der Saldo ausgeglichen ist und die verbleibenden Buchungen und PayPal-Meldungen abgelaufen sind.</p>`,
    'Konto endgültig schließen', () => api('/api/admin/close-account', {id}));
}

function bookPerson(id) {
  const p = overview.people.find(person => person.id === id);
  const request = idempotencyKey();
  modal('Zahlung oder Korrektur buchen',
    `<p><strong>${personName(p)}</strong> · aktueller Saldo ${amount(p.balance)}</p>
     <label>Buchungsart<select name="kind"><option value="payment">Erhaltene Zahlung</option><option value="correction">Saldo korrigieren</option></select></label>
     <label>Betrag in Euro<input name="value" inputmode="decimal" placeholder="5,00" required></label>
     <p class="hint">Ein positiver Betrag erhöht den Saldo. Eine Korrektur kann auch negativ sein, zum Beispiel −2,50.</p>
     <label>Grund / Zahlungsart<input name="note" maxlength="240" placeholder="z. B. Barzahlung" required></label>`,
    'Buchen', fields => api('/api/admin/adjust', {id, request, kind: fields.get('kind'), note: fields.get('note'),
      cents: eurosToCents(fields.get('value').replace('−', '-'))}));
}

function reverseEntry(id) {
  const entry = journal.entries.find(row => row.id === id);
  modal('Kauf stornieren',
    `<p>Für Buchung #${id} werden ${euro(-entry.cents)} gutgeschrieben. Der Kauf bleibt im Kassenbuch sichtbar.</p>
     <label>Begründung<input name="note" maxlength="240" required></label>`,
    'Storno buchen', fields => api('/api/admin/reverse', {id, note: fields.get('note')}));
}

function captureCard(id) {
  const person = overview.people.find(p => p.id === id);
  modal('Karte ersetzen', `<p>Konto <strong>${personName(person)}</strong></p>
    <label>Leser am Verkaufspunkt<select name="terminal">${options(overview.terminals)}</select></label>`,
    'Leser aktivieren', async fields => {
      const terminal = fields.get('terminal');
      await api('/api/admin/capture-start', {id, terminal});
      waitForCard(terminal);
      return false;
    });
}

function waitForCard(terminal) {
  capturing = terminal;
  modal('Neue Karte anhalten',
    `<p>Leser an <strong>${esc(overview.terminals[terminal])}</strong></p>
    <p>Halte ausschließlich den neuen Ausweis an diesen Leser. Das Konto und seine Buchungen bleiben bestehen.</p>
    <p id="capture-status" class="hint" role="status">Warte auf die neue Karte …</p>`,
    'Karte zuordnen', () => api('/api/admin/capture-confirm', {terminal}));
  const submit = editor.querySelector('[type=submit]');
  submit.disabled = true;
  const poll = async () => {
    if (capturing !== terminal || !editor.open) return;
    try {
      const result = await api('/api/admin/capture-status?terminal=' + encodeURIComponent(terminal));
      if (capturing !== terminal || !editor.open) return;
      const seconds = Math.ceil(result.remaining || 0);
      editor.querySelector('#capture-status').textContent = result.state === 'idle' ? 'Zeitfenster abgelaufen. Starte den Vorgang erneut.' :
        result.state === 'ready' ? 'Karte erfasst. Bestätige innerhalb von ' + seconds + ' s.' : 'Warte auf die neue Karte · ' + seconds + ' s';
      submit.disabled = result.state !== 'ready';
      if (result.state !== 'idle') captureTimer = setTimeout(poll, 700);
    } catch (error) {
      handleError(error);
    }
  };
  poll();
}

editor.addEventListener('close', () => {
  clearTimeout(captureTimer);
  if (capturing) {
    const terminal = capturing;
    capturing = null;
    api('/api/admin/capture-cancel', {terminal}).catch(() => {});
  }
});
editor.addEventListener('cancel', event => { if (busy) event.preventDefault(); });

async function setup() {
  try {
    session = await api('/api/admin/session');
    await refresh();
  } catch (error) {
    signIn();
    if (error.status !== 401) notify(error.message);
  }
}

document.addEventListener('submit', async event => {
  event.preventDefault();
  if (busy) return;
  const form = event.target;
  const formId = form.getAttribute('id');
  const submit = form.querySelector('[type=submit]');
  const fields = new FormData(form);
  busy = true;
  submit.disabled = true;
  try {
    if (formId === 'login-form') {
      await api('/api/admin/login', Object.fromEntries(fields));
      await setup();
    } else if (formId === 'edit-form') {
      const result = await modalAction(fields);
      if (result === false) return;
      capturing = null;
      editor.close();
      if (result?.relogin) {
        signIn();
        notify('Gespeichert. Bitte melde dich erneut an.');
        return;
      }
      try { await refresh('Gespeichert.'); } catch (error) { handleError(error); }
    } else if (formId === 'terms-form') {
      if (form.dataset.document === 'privacy') {
        await api('/api/admin/privacy', {base: privacy.version, body: fields.get('body'), date: fields.get('date')});
        await refresh('Datenschutzerklärung gespeichert.');
      } else {
        await api('/api/admin/terms', {base: terms.version, body: fields.get('body')});
        await refresh('Neue Fassung veröffentlicht.');
      }
    }
  } catch (error) {
    if (formId !== 'login-form' && error.status === 401) handleError(error);
    else form.querySelector('.form-error').textContent = error.message;
  } finally {
    busy = false;
    submit.disabled = false;
  }
});

document.addEventListener('keydown', event => {
  if (event.key !== 'Escape' || editor.open) return;
  const group = admin.querySelector('.admin-nav-group[open]');
  if (group) {
    group.open = false;
    if (group.contains(event.target)) group.querySelector('summary').focus();
  }
});

document.addEventListener('click', async event => {
  for (const group of document.querySelectorAll('.admin-nav-group[open]')) {
    if (!group.contains(event.target)) group.open = false;
  }
  const button = event.target.closest('button');
  if (!button || busy || !session) return;
  const d = button.dataset;
  if ('close' in d) { editor.close(); return; }
  if (d.peopleSort) {
    const key = d.peopleSort;
    const table = document.getElementById('people-table');
    const scrollLeft = table.querySelector('.table-wrap').scrollLeft;
    peopleSort = {key, direction: peopleSort.key === key && peopleSort.direction === 'ascending' ? 'descending' : 'ascending'};
    table.innerHTML = peopleTable();
    table.querySelector('.table-wrap').scrollLeft = scrollLeft;
    table.querySelector(`[data-people-sort="${key}"]`).focus({preventScroll: true});
    sessionTimer();
    return;
  }
  if ('documentExport' in d) {
    const form = button.form;
    const published = d.documentExport === 'published';
    if (!published && !form.reportValidity()) return;
    const errorField = form.querySelector('.form-error');
    const fields = new FormData(form);
    const kind = form.dataset.document;
    if (!published && !fields.get('date')) {
      errorField.textContent = 'Gib ein Standdatum für den Ausdruck an.';
      return;
    }
    button.disabled = true;
    errorField.textContent = '';
    try {
      const current = published ? await api('/api/admin/' + kind) : null;
      const text = current ? (kind === 'privacy' ? current.body : termsText(current)) : fields.get('body');
      const date = current ? current.date : fields.get('date');
      await downloadPrintDocument({kind, text, date});
      notify('Druckfassung exportiert.');
    } catch {
      errorField.textContent = 'Die Druckfassung konnte nicht erstellt werden. Prüfe die Verbindung und versuche es erneut.';
    } finally {
      button.disabled = false;
    }
    return;
  }
  busy = true;
  try {
    if ('adminLogout' in d) {
      await api('/api/admin/logout', {});
      signIn();
      return;
    }
    if (d.tab || d.show) {
      tab = d.tab || 'journal';
      if (d.show) { selectedPerson = d.show; selectedTerminal = ''; }
      if (tab === 'people' || tab === 'preview') overview = await api('/api/admin/overview');
      await loadTab();
      render();
      const selected = admin.querySelector('.admin-navigation [aria-current="page"]');
      (selected?.closest('details')?.querySelector('summary') || selected)?.focus();
    }
    if ('auditNext' in d && audit.next) {
      await loadAudit(auditPage + 1, audit.next);
      render();
      sessionTimer();
    }
    if ('auditPrev' in d && auditPage) {
      await loadAudit(auditPage - 1, auditCursors[auditPage - 1]);
      render();
      sessionTimer();
    }
    if (d.productCategory) { productCategory = d.productCategory; render(); }
    if ('more' in d) { await loadJournal(true); render(); }
    if ('paypalMore' in d) { await loadPayments(true); render(); sessionTimer(); }
    if (d.paypalConfirm) resolvePaypal(Number(d.paypalConfirm), true);
    if (d.paypalReject) resolvePaypal(Number(d.paypalReject), false);
    if ('paypalSettings' in d) editPaypalSettings();
    if (d.resetPin) resetPin(Number(d.resetPin));
    if ('addAdmin' in d) editAdmin();
    if (d.editAdmin) editAdmin(d.editAdmin);
    if (d.removeAdmin) removeAdmin(d.removeAdmin);
    if (d.resetAdminPassword) resetAdminPassword(d.resetAdminPassword);
    if ('createSite' in d) createSite();
    if (d.editSite) renameSite(d.editSite);
    if (d.deleteSite) deleteSite(d.deleteSite);
    if (d.pairSite) pairSite(d.pairSite);
    if (d.unpairSite) unpairSite(d.unpairSite);
    if ('changePassword' in d) changePassword();
    if (d.format) formatDraft(d.format);
    if ('new' in d) editProduct(null);
    if (d.product) editProduct(Number(d.product));
    if (d.archive) archiveProduct(Number(d.archive));
    if (d.deleteProduct) deleteProduct(Number(d.deleteProduct));
    if (d.person) editPerson(Number(d.person));
    if (d.closeAccount) closeAccount(Number(d.closeAccount));
    if (d.book) bookPerson(Number(d.book));
    if (d.reverse) reverseEntry(Number(d.reverse));
    if (d.capture) captureCard(Number(d.capture));
    if (d.tab || d.show || 'more' in d || d.capture) sessionTimer();
  } catch (error) {
    handleError(error);
  } finally {
    busy = false;
  }
});

document.addEventListener('change', async event => {
  if (event.target.name === 'category' && editor.open && editor.querySelector('[name=icon]')) {
    editor.querySelector('[name=icon]').value = iconDefaults[event.target.value];
  }
  const filters = {
    'journal-person': value => { selectedPerson = value; },
    'journal-terminal': value => { selectedTerminal = value; },
    'payment-status': value => { paymentStatus = value; },
    'report-month': value => { reportMonth = value; },
    'report-terminal': value => { reportTerminal = value; },
  };
  if (!filters[event.target.id] || busy) return;
  filters[event.target.id](event.target.value);
  busy = true;
  try { await loadTab(); render(); sessionTimer(); } catch (error) { handleError(error); } finally { busy = false; }
});

document.addEventListener('input', event => {
  if (event.target.id === 'terms-draft') {
    document.getElementById('terms-preview').innerHTML = formattedTerms(event.target.value);
    return;
  }
  if (event.target.id !== 'person-search') return;
  search = event.target.value;
  document.getElementById('people-table').innerHTML = peopleTable();
});

setup();
setInterval(refreshTerminalStatus, 5000);
