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
    applyState(next) {calls.push(['state', next]);}, kioskPath: p => p,
    kioskApi(p, body) {calls.push(['api', p, body]); return Promise.resolve({remaining: 15});},
  };
  return {context, calls};
}

test('masked PIN fields and touch keypad accept four digits including zero', () => {
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
      overview: {products: [{id: 7, name: 'Old name', cents: 50, terminals: ['a'], active}]},
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
    overview: {people: [], terminals: {}},
    selectedPerson: '',
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
  assert.match(rendered, /Kaffee &lt;alt&gt;/);
  assert.match(rendered, /Grund &lt;b&gt;spät&lt;\/b&gt;/);
  assert.match(rendered, /Zu Kauf #1/);
  context.journal.entries[0].items = [];
  context.journal.entries[0].reverses = null;
  const expired = vm.runInNewContext(script + '\njournalPanel();', context);
  assert.match(expired, /Grund &lt;b&gt;spät&lt;\/b&gt;/);
  assert.doesNotMatch(expired, /Kaffee|Zu Kauf/);
});

test('admin people search shows stamp progress and redeemed totals for each account', () => {
  const context = {
    overview: {people: [
      {id: 1, first: 'Alicia', balance: 0, loyalty: {stamps: 4, target: 10, redeemed: 1}},
      {id: 2, first: 'Bruno', balance: 0, loyalty: {stamps: 0, target: 10, redeemed: 0}},
    ], card_types: {}, card_media: {}},
    search: '', personLabel: p => p.first, personName: p => p.first, esc: String,
    dateTime: () => '', amount: String, consentCell: () => '', rowAction: () => '', exportLink: () => '',
    table: (labels, rows) => ({labels, rows}),
  };
  const render = () => vm.runInNewContext(section(admin, 'function peopleRows()', 'function peoplePanel()') +
    '\npeopleTable();', context);
  const all = render();
  assert.ok(all.labels.includes('Sammelkarte'));
  assert.match(all.rows, /4\/10/);
  assert.match(all.rows, /1 Gratisgetränk eingelöst/);
  context.search = 'bruno';
  const filtered = render();
  assert.match(filtered.rows, /0\/10/);
  assert.match(filtered.rows, /0 Gratisgetränke eingelöst/);
  assert.doesNotMatch(filtered.rows, /Alicia/);
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
