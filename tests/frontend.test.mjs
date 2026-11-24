import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import test from 'node:test';
import vm from 'node:vm';
import {acceptsState, canExtendVisit, sessionViewChanged} from '../static/kiosk-session.js';
import {keyboardMarkup, pinField} from '../static/kiosk-keyboard.js';
import {loyaltyCardMarkup} from '../static/loyalty-card.js';
import {shopMarkup} from '../static/shop-view.js';
import {esc} from '../static/shared.js';
import {mountProjectFooter, PROJECT_URL} from '../static/site-chrome.js';
import {columnHeading, table} from '../static/ui-table.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const kiosk = fs.readFileSync(path.join(root, 'static/kiosk.js'), 'utf8');
const actions = fs.readFileSync(path.join(root, 'static/kiosk-actions.js'), 'utf8');
const admin = fs.readFileSync(path.join(root, 'static/admin.js'), 'utf8');
const technical = fs.readFileSync(path.join(root, 'static/technical-docs.js'), 'utf8');
function section(source, start, end) {
  const first = source.indexOf(start);
  const last = source.indexOf(end, first + start.length);
  assert.ok(first >= 0 && last > first, `Missing source section: ${start}`);
  return source.slice(first, last);
}
const timers = section(kiosk, 'function updateTimers()', '\nasync function updateCatalog()');
const activity = section(kiosk, 'function activity()', '\nfunction adjust(');

function timerContext(stage, seconds) {
  const calls = [];
  const context = {
    state: {stage, visit: 'manual-visit'}, deadline: seconds * 1000, activityTimer: null,
    performance: {now: () => 0}, document: {getElementById: () => null},
    timeoutDialog: {open: false, showModal() {this.open = true;}, close() {this.open = false;}},
    timeoutCountdown: {}, INACTIVITY_WARNING_SECONDS: 5,
    canExtendVisit,
    applyState(next) {calls.push(['state', next]);},
    kioskApi(p, body) {calls.push(['api', p, body]); return Promise.resolve({remaining: 15});},
  };
  return {context, calls};
}

test('masked PIN fields and touch keypad accept four digits including zero', () => {
  assert.match(pinField('pin', 'Vierstellige PIN'), /class="kiosk-entry-label">Vierstellige PIN/);
  assert.match(pinField('pin', 'PIN'), /type="password"/);
  assert.match(pinField('pin_confirmation', 'PIN bestätigen'), /name="pin_confirmation"/);
  assert.match(pinField('pin', 'PIN'), /pattern="\[0-9\]\{4\}"/);
  const keys = Array.from(keyboardMarkup(false, true).matchAll(/data-key="([^"]+)"/g), match => match[1]);
  assert.deepEqual(keys, [...'1234567890', 'delete', 'next']);
  assert.equal(canExtendVisit({stage: 'pin-setup', visit: 'visit'}), true);
});

test('manual login fields are cleared by the same expiry path as a shop session', () => {
  const {context, calls} = timerContext('manual', 0);
  vm.runInNewContext(timers + '\nupdateTimers();', context);
  assert.equal(calls[0][1].stage, 'idle');
  assert.equal(calls[0][1].visit, null);
  assert.equal(calls[1][1], '/api/kiosk/logout');
  assert.equal(calls[1][2].visit, 'manual-visit');
});

test('manual login shows the inactivity warning in its last five seconds', () => {
  const {context} = timerContext('manual', 4);
  vm.runInNewContext(timers + '\nupdateTimers();', context);
  assert.equal(context.timeoutDialog.open, true);
  assert.equal(context.timeoutCountdown.textContent, 4);
});

test('receipt retains its own countdown without an inactivity warning', () => {
  const {context} = timerContext('receipt', 4);
  vm.runInNewContext(timers + '\nupdateTimers();', context);
  assert.equal(context.timeoutDialog.open, false);
});

test('idle screen without a visit does not send repeated logout requests', () => {
  const {context, calls} = timerContext('idle', 0);
  context.state.visit = null;
  vm.runInNewContext(timers + '\nupdateTimers();', context);
  assert.equal(calls.length, 0);
});

test('activity during manual login requests an extension for that visit', async () => {
  const {context, calls} = timerContext('manual', 7);
  context.lastActivity = -1000;
  let scheduled;
  context.setTimeout = fn => {scheduled = fn; return 1;};
  vm.runInNewContext(activity + '\nactivity();', context);
  assert.equal(typeof scheduled, 'function');
  scheduled();
  await Promise.resolve();
  assert.equal(calls[0][1], '/api/kiosk/activity');
  assert.equal(calls[0][2].visit, 'manual-visit');
  assert.equal(context.deadline, 15000);
});

test('late activity response cannot extend a replacement visit', async () => {
  const {context} = timerContext('manual', 7);
  context.lastActivity = -1000;
  let scheduled, answer;
  context.setTimeout = fn => {scheduled = fn; return 1;};
  context.kioskApi = () => new Promise(resolve => {answer = resolve;});
  vm.runInNewContext(activity + '\nactivity();', context);
  scheduled();
  context.state = {stage: 'manual', visit: 'replacement'};
  answer({remaining: 15});
  await Promise.resolve();
  assert.equal(context.deadline, 7000);
});

test('expired visits cannot repaint the kiosk and receipts cannot be extended', () => {
  const visit = {stage: 'shop', visit: 'old'};
  assert.equal(acceptsState(visit, 'old'), false);
  assert.equal(acceptsState({...visit, visit: 'new'}, 'old'), true);
  assert.equal(sessionViewChanged(visit, {...visit, remaining: 4}), false);
  assert.equal(sessionViewChanged(visit, {...visit, stage: 'receipt'}), true);
  assert.equal(canExtendVisit({...visit, stage: 'receipt'}, 'old'), false);
  assert.match(keyboardMarkup(true), /data-key="ẞ"/);
  assert.match(keyboardMarkup(false), /data-key="7"/);
});

test('shop shows the loyalty button next to the two grouped financial actions', () => {
  assert.match(shopMarkup(true), /data-loyalty[\s\S]+class="account-finance"[\s\S]+data-payment[\s\S]+Bezahlen[\s\S]+data-history[\s\S]+Dein Saldo/);
  assert.doesNotMatch(shopMarkup(false), /data-loyalty/);
});

test('receipt gives each newly earned stamp its own animation and marks a full card', () => {
  const html = loyaltyCardMarkup({stamps: 10, target: 10, ready: 1, remaining: 0}, {newStamps: 2});
  assert.equal(Array.from(html.matchAll(/class="loyalty-stamp /g)).length, 10);
  assert.equal(Array.from(html.matchAll(/new-stamp/g)).length, 2);
  assert.match(html, /final-stamp new-stamp/);
  assert.match(html, /data-stamp-delay="320"[\s\S]+data-stamp-delay="430"/);
  assert.doesNotMatch(html, /\sstyle=/);
  assert.match(html, /Gratisgetränk freigeschaltet/);
});

test('redeemed card shows the reward and transitions from the used card to the current card', () => {
  const html = loyaltyCardMarkup({stamps: 0, target: 10, ready: 0, remaining: 10}, {redeemed: 1});
  assert.match(html, /1 Gratisgetränk eingelöst/);
  assert.match(html, /loyalty-face-current[\s\S]+0 \/ 10[\s\S]+loyalty-face-spent" aria-hidden="true"[\s\S]+10 \/ 10/);
  assert.doesNotMatch(html, /new-stamp/);
});

test('checkout applies new stamps before redemption and keeps the earned remainder on the current card', () => {
  const html = loyaltyCardMarkup({stamps: 2, target: 10, ready: 0, remaining: 8}, {newStamps: 3, redeemed: 1});
  const current = section(html, 'loyalty-face-current', 'loyalty-face-spent');
  assert.equal(Array.from(current.matchAll(/new-stamp/g)).length, 2);
  assert.equal(Array.from(html.matchAll(/new-stamp/g)).length, 3);
});

function dialogContext(stage) {
  const handlers = {};
  const cancellations = [];
  const content = {addEventListener() {}, replaceChildren() {}};
  const dialog = {open: false, addEventListener(name, fn) {handlers[name] = fn;}};
  const context = {document: {getElementById: id => id === 'kiosk-dialog' ? dialog : content},
                   Intl, clearTimeout() {}, cancellations, stage};
  const source = actions.replace(/^import .*;\r?\n/gm, '').replace('export function createKioskDialog', 'function createKioskDialog');
  vm.runInNewContext(source + `\ncreateKioskDialog({state: () => ({stage, visit: 'current'}), request() {}, cancelManual: visit => cancellations.push(visit)});`, context);
  return {handlers, cancellations};
}

test('closing a manual dialog cancels the corresponding server visit', () => {
  const {handlers, cancellations} = dialogContext('manual');
  handlers.close();
  assert.deepEqual(cancellations, ['current']);
});

test('closing a normal account dialog does not log out its user', () => {
  const {handlers, cancellations} = dialogContext('shop');
  handlers.close();
  assert.deepEqual(cancellations, []);
});

test('archive and reactivate submit only the desired status from a stale product view', () => {
  for (const active of [1, 0]) {
    const calls = [];
    const context = {
      productsView: {products: [{id: 7, name: 'Old name', cents: 50, terminals: ['a'], active}]},
      esc: String,
      modal: (title, html, label, confirm) => confirm(),
      api: (path, payload) => calls.push([path, JSON.parse(JSON.stringify(payload))]),
    };
    vm.runInNewContext(section(admin, 'function archiveProduct(', 'function editPerson(') + '\narchiveProduct(7);', context);
    assert.deepEqual(calls, [['/api/admin/product-status', {id: 7, active: !active}]]);
  }
});

test('admin journal shows escaped reversal details, the reason and the original booking', () => {
  const context = {
    journal: {entries: [{
      id: 2, reverses: 1, kind: 'reversal', cents: 130, note: 'Grund <b>spät</b>',
      items: [{name: 'Kaffee <alt>', quantity: 1, price: 130}],
    }], next: null},
    sites: {terminals: {}, retired_terminals: {}},
    selectedPersonLabel: '',
    showReversals: false,
    selectedTerminal: '',
    esc: value => String(value).replaceAll('<', '&lt;').replaceAll('>', '&gt;'),
    euro: String,
    amount: String,
    dateTime: () => '',
    personName: () => 'Gast',
    options: () => '',
    kinds: {reversal: 'Storno'},
    table: (_headings, rows) => rows,
  };
  const script = section(admin, 'function historicalSites(', 'function editProduct(') +
    section(admin, 'function journalPanel(', 'function consentCell(');
  const rendered = vm.runInNewContext(script + '\njournalPanel();', context);
  assert.match(rendered, /class="pill danger">Storno<\/span>/);
  assert.match(rendered, /Kaffee &lt;alt&gt;/);
  assert.match(rendered, /Grund &lt;b&gt;spät&lt;\/b&gt;/);
  assert.match(rendered, /Zu Kauf #1/);
  assert.match(rendered, /id="journal-reversals"\s*> Stornos anzeigen/);
  context.showReversals = true;
  assert.match(vm.runInNewContext(script + '\njournalPanel();', context), /id="journal-reversals" checked/);
  context.journal.entries[0].items = [];
  context.journal.entries[0].reverses = null;
  const expired = vm.runInNewContext(script + '\njournalPanel();', context);
  assert.match(expired, /Grund &lt;b&gt;spät&lt;\/b&gt;/);
  assert.doesNotMatch(expired, /Kaffee|Zu Kauf/);
  context.journal.entries[0].kind = 'purchase';
  context.journal.entries[0].reversed_by = 3;
  context.kinds.purchase = 'Kauf';
  assert.match(vm.runInNewContext(script + '\njournalPanel();', context), /class="pill good">Kauf<\/span>/);
});

test('admin people renders the server page in order and keeps account fields and card labels', () => {
  const loyalty = {stamps: 0, target: 10, redeemed: 0};
  const context = {
    peopleView: {people: [
      {id: 1, last: 'Ährens', first: 'Alicia', department: 'R 10', balance: -1000, card_medium: 'badge',
        terms_current: true, manual_enabled: true, consents: [{version: 'historical-policy-id'}],
        loyalty: {stamps: 4, target: 10, redeemed: 1}},
      {id: 2, last: 'Berg', first: 'Bruno', department: 'R 2', balance: 90, card_type: 'classic', loyalty},
      {id: 3, last: 'Caro', first: 'Anna', department: 'R 3 <Nord>', balance: -90, card_type: 'classic',
        card_medium: 'badge', loyalty},
      {id: 4, last: 'Dorn', first: 'Dana', department: '', balance: 1000, loyalty},
    ], card_types: {classic: 'MIFARE Classic'}, card_media: {badge: 'Dienstausweis'}},
    esc, peopleSort: {key: 'last', direction: 'ascending'},
    columnHeading, table, dateTime: () => '', amount: String,
    rowAction: action => `<button data-test-action="${action}"></button>`,
    exportLink: () => '<button data-test-action="export"></button>',
  };
  const script = section(admin, 'const peopleSortKeys', 'let session') +
    section(admin, 'function consentCell(', 'function peoplePanel(');
  const render = () => vm.runInNewContext('(() => {\n' + script + '\nreturn peopleTable();\n})()', context);
  const ids = html => Array.from(html.matchAll(/Konto #(\d+)/g), match => Number(match[1]));
  const all = render();
  assert.match(all, /class="consent-status"><span class="pill good">Bestätigt<\/span><\/td>/);
  assert.match(all, /class="consent-status"><span class="pill off">Offen<\/span><\/td>/);
  assert.doesNotMatch(all, /historical-policy-id|Frühere Bestätigungen/);
  assert.match(all, /<th scope="col" aria-sort="ascending">\s*<button[^>]+data-people-sort="last">Name/);
  assert.match(all, /<td><strong>Ährens<\/strong><\/td><td><strong>Alicia<\/strong><\/td>\s*<td>R 10<\/td>/);
  assert.match(all, /<th scope="col">Aktionen<\/th><th scope="col">Kontodetails<\/th>/);
  const groups = Array.from(all.matchAll(/class="action-list account-action-row">([^]*?)<\/div>/g),
    match => Array.from(match[1].matchAll(/data-test-action="([^"]+)"/g), action => action[1]));
  assert.deepEqual(groups.slice(0, 2), [['book', 'person', 'capture', 'show'], ['export', 'reset-pin', 'close-account']]);
  assert.match(all, /<td class="account-details"><strong>Konto #1<\/strong>/);
  assert.match(all, /<td>R 3 &lt;Nord&gt;<\/td>/);
  assert.match(all, /4\/10/);
  assert.match(all, /1 Gratisgetränk eingelöst/);
  assert.match(all, /Konto #1[^]*?<small>Dienstausweis<\/small>/);
  assert.match(all, /Konto #2[^]*?<small>MIFARE Classic<\/small>/);
  assert.match(all, /Konto #3[^]*?<small>Dienstausweis · MIFARE Classic<\/small>/);
  assert.match(all, /Konto #4[^]*?<small>Kartentyp nicht bestimmt<\/small>/);
  assert.equal((all.match(/Kartentyp nicht bestimmt/g) ?? []).length, 1);
  assert.deepEqual(ids(all), [1, 2, 3, 4]);
  context.peopleView.people = [context.peopleView.people[2], context.peopleView.people[1]];
  context.peopleSort = {key: 'balance', direction: 'descending'};
  const page = render();
  assert.deepEqual(ids(page), [3, 2]);
  assert.match(page, /aria-sort="descending"[^]*?data-people-sort="balance"/);
  assert.match(page, /0\/10/);
  assert.match(page, /0 Gratisgetränke eingelöst/);
  assert.doesNotMatch(page, /Alicia/);
});

test('the shared footer opens the repository dialog and keeps the Berlin copyright year', t => {
  const year = {};
  const trigger = new EventTarget();
  const close = new EventTarget();
  const dialog = new EventTarget();
  dialog.setAttribute = () => {};
  dialog.querySelector = () => close;
  dialog.showModal = () => { dialog.open = true; };
  dialog.close = () => { dialog.open = false; dialog.dispatchEvent(new Event('close')); };
  let focused = false;
  trigger.focus = () => { focused = true; };
  const footer = {
    querySelector: selector => selector === 'button' ? trigger : year,
    ownerDocument: {createElement: () => dialog, body: {append: element => assert.equal(element, dialog)}},
  };
  let update;
  t.mock.method(globalThis, 'setInterval', callback => { update = callback; });
  t.mock.timers.enable({apis: ['Date'], now: new Date('2026-12-31T22:59:59Z')});
  mountProjectFooter(footer);
  assert.equal(year.textContent, '2026');
  t.mock.timers.tick(1000);
  update();
  assert.equal(year.textContent, '2026-2027');
  assert.match(footer.innerHTML, /aria-haspopup="dialog"[^>]*>beilo1\/kostbar/);
  assert.ok(dialog.innerHTML.includes(`href="${PROJECT_URL}"`));
  assert.match(dialog.innerHTML, /src="\/static\/project-qr.svg"/);
  trigger.dispatchEvent(new Event('click'));
  assert.equal(dialog.open, true);
  close.dispatchEvent(new Event('click'));
  assert.equal(dialog.open, false);
  assert.equal(focused, true);
});

test('the public legal pages both return to the same kiosk page', () => {
  for (const page of ['terms', 'privacy']) {
    const html = fs.readFileSync(path.join(root, 'static', page + '.html'), 'utf8');
    assert.match(html, /href="\/">Zurück zur Kasse<\/a>/);
    assert.match(html, /data-project-footer/);
    assert.doesNotMatch(html, /INFORMATION ZUR KoSTbar/);
  }
});

test('admin loads only the active panel and passes the reversal filter to the journal cursor', async () => {
  const requests = [];
  const context = {
    URLSearchParams, tab: 'journal', selectedPerson: '7', selectedTerminal: 'b', showReversals: false,
    session: {super_admin: false}, peopleRequest: 0, peopleSort: {key: 'balance', direction: 'descending'},
    search: 'Name Referat', journal: {entries: []},
    async api(path) {
      requests.push(path);
      if (path.startsWith('/api/admin/journal?')) return {entries: [], next: 42};
      if (path.startsWith('/api/admin/people?')) return {people: [{id: 7}], page: 2};
      if (path.startsWith('/api/admin/payments?')) return {payments: [], next: null};
      return {};
    },
  };
  const source = section(admin, 'async function loadJournal(', 'function sessionTimer(');
  const js = vm.createContext(context);
  vm.runInContext(source, js);
  await vm.runInContext('loadTab()', js);
  assert.deepEqual(requests.splice(0), ['/api/admin/journal?reversals=0&person=7&terminal=b', '/api/admin/sites']);
  context.showReversals = true;
  await vm.runInContext('loadJournal();', js);
  await vm.runInContext('loadJournal(true);', js);
  assert.deepEqual(requests.splice(0), ['/api/admin/journal?reversals=1&person=7&terminal=b',
    '/api/admin/journal?reversals=1&person=7&terminal=b&before=42']);
  context.tab = 'people';
  await vm.runInContext('loadTab(2)', js);
  assert.deepEqual(requests.splice(0), ['/api/admin/people?search=Name+Referat&page=2&sort=balance&direction=descending']);
  context.tab = 'payments';
  context.paymentStatus = 'pending';
  await vm.runInContext('loadTab()', js);
  assert.deepEqual(requests, ['/api/admin/payments?status=pending', '/api/admin/sites']);
});

test('a late account search response cannot replace the newer page', async () => {
  const resolve = [];
  const context = {
    URLSearchParams, tab: 'people', session: {}, peopleRequest: 0, search: 'Alt',
    peopleSort: {key: 'last', direction: 'ascending'},
    api: () => new Promise(done => resolve.push(done)),
  };
  const js = vm.createContext(context);
  vm.runInContext(section(admin, 'async function loadPeople(', 'async function loadReport('), js);
  const older = vm.runInContext('loadPeople()', js);
  context.search = 'Neu';
  const newer = vm.runInContext('loadPeople()', js);
  resolve[1]({people: [{id: 2}], page: 1});
  assert.equal(await newer, true);
  resolve[0]({people: [{id: 1}], page: 1});
  assert.equal(await older, false);
  assert.equal(context.peopleView.people[0].id, 2);
});

test('technical view shows cleanup failure and the last successful run', () => {
  const context = {
    doc: {
      deployment: 'QNAP', images: [], dependencies: [], pi_packages: [], terminals: {},
      retention: {failed_since: 'FAILURE-TIME', last_success: 'SUCCESS-TIME'},
    },
    esc: String,
    dateTime: value => value,
    table: (_headings, rows) => rows.join(' '),
    purpose: {},
  };
  const script = section(technical, 'function packageVersions(', 'function apiReference(');
  const failed = vm.runInNewContext(script + '\npackageVersions(doc);', context);
  assert.match(failed, /Gestört seit FAILURE-TIME/);
  assert.match(failed, /Letzter Erfolg · SUCCESS-TIME/);
  context.doc.retention.failed_since = null;
  const recovered = vm.runInNewContext(script + '\npackageVersions(doc);', context);
  assert.match(recovered, /Datenbereinigung,Bereit/);
});
