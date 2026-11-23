import {api, esc, idempotencyKey, notify, personLabel} from './shared.js';

const PREVIEW_API = '/api/admin/terminal-preview';
export const PREVIEW_PAGE = PREVIEW_API + '/page';

const monthFormat = new Intl.DateTimeFormat('sv-SE', {year: 'numeric', month: '2-digit', timeZone: 'Europe/Berlin'});
const fail = (message, status = 409) => { throw Object.assign(new Error(message), {status}); };

export function createTerminalPreview() {
  const terminal = new URLSearchParams(location.search).get('terminal');
  const query = '?' + new URLSearchParams({terminal});
  const toolbar = document.getElementById('preview-toolbar');
  const sites = document.getElementById('preview-sites');
  const status = document.getElementById('preview-status');
  const progressField = document.getElementById('preview-progress');
  const [testCard, registrationCard] = toolbar.querySelectorAll('[data-preview-card]');
  const defaultStatus = status.textContent;
  const guest = {id: 1, first: 'Test', last: 'Gast', department: 'Vorschau', pin: '1234',
    balance: 0, progress: 0, payments: [], entries: []};
  let registeredGuest;
  let account;
  let config;
  let catalog;
  let nextRefresh = 0;
  let refreshRequest;
  let stage = 'idle';
  let visit = null;
  let until = 0;
  let receipt;
  let entry = 0;
  let payment = 0;
  let pinFailures = 0;
  let lockedUntil = 0;

  toolbar.hidden = false;
  document.title = 'KoSTbar · Terminal-Vorschau';

  function updateControls(view) {
    const idle = view.stage === 'idle';
    testCard.disabled = !idle;
    registrationCard.disabled = !idle || (!registeredGuest && !config.registration);
    registrationCard.textContent = registeredGuest ? 'Registrierten Testausweis anhalten' : 'Neuen Testausweis anhalten';
    progressField.disabled = !idle && view.stage !== 'shop';
    progressField.value = Math.min((account ?? guest).progress, config.loyalty.target);
  }

  async function refresh(force = false) {
    if (refreshRequest) return refreshRequest;
    if (!force && performance.now() < nextRefresh) return;
    refreshRequest = api(PREVIEW_API + query).then(next => {
      const updatedCatalog = {products: next.products, categories: next.categories};
      if (JSON.stringify(updatedCatalog) !== JSON.stringify(catalog)) catalog = updatedCatalog;
      if (JSON.stringify(next.terminals) !== JSON.stringify(config?.terminals)) {
        sites.innerHTML = Object.entries(next.terminals).map(([id, label]) =>
          `<a class="button outline compact" href="?${new URLSearchParams({terminal: id})}"${terminal === id ? ' aria-current="page"' : ''}>${esc(label)}</a>`).join('');
      }
      if (next.loyalty.target !== config?.loyalty.target) {
        const {target} = next.loyalty;
        progressField.innerHTML = Array.from({length: target + 1}, (_, count) =>
          `<option value="${count}">${count} / ${target}${count === target ? ' · Bonus bereit' : ''}</option>`).join('');
      }
      config = next;
      if (status.textContent !== defaultStatus) status.textContent = defaultStatus;
      nextRefresh = performance.now() + 5000;
    }).catch(error => {
      status.textContent = error.message;
      testCard.disabled = registrationCard.disabled = progressField.disabled = true;
      throw error;
    }).finally(() => { refreshRequest = null; });
    return refreshRequest;
  }

  function openVisit(next, selected) {
    stage = next;
    visit = idempotencyKey();
    account = selected;
    until = performance.now() + config.session_idle * 1000;
  }

  function resetVisit() {
    stage = 'idle';
    visit = null;
    account = null;
    receipt = null;
    until = 0;
  }

  function loyaltyCard(progress) {
    const {target} = config.loyalty;
    return {target, stamps: Math.max(0, Math.min(progress, target)),
      ready: Math.max(0, Math.floor(progress / target)), remaining: Math.max(0, target - progress)};
  }

  function snapshot() {
    const state = {stage, visit, terminal: config.terminal, notice: null, reader: true, maintenance: false,
      remaining: Math.max(0, (until - performance.now()) / 1000),
      version: config.version, privacy_version: config.privacy_version};
    if (stage === 'shop') {
      const {first, balance, progress} = account;
      state.profile = {first, balance, loyalty: loyaltyCard(progress)};
    }
    if (stage === 'receipt') state.receipt = receipt;
    return state;
  }

  async function scan(newCard) {
    try {
      await refresh(true);
      if (stage !== 'idle') return;
      const selected = newCard ? registeredGuest : guest;
      if (selected) openVisit('shop', selected);
      else if (config.registration) openVisit('register');
    } catch (error) {
      notify(error.message);
    }
  }

  testCard.addEventListener('click', () => scan(false));
  registrationCard.addEventListener('click', () => scan(true));
  progressField.addEventListener('change', () => {
    if (stage === 'idle' || stage === 'shop') (account ?? guest).progress = Number(progressField.value);
  });

  function finish(kind, cents, request, {bonus = [], stamps = 0, items = []} = {}) {
    account.balance += cents;
    account.entries.unshift({id: ++entry, kind, cents, at: new Date().toISOString(), terminal, items,
      method: kind === 'payment' ? 'Barzahlung' : null});
    receipt = {entry, kind: kind === 'payment' ? 'cash' : kind, total: Math.abs(cents),
      balance: account.balance, request, bonus, stamps_earned: stamps};
    if (stamps || bonus.length) receipt.loyalty = loyaltyCard(account.progress);
    stage = 'receipt';
    until = performance.now() + config.receipt_seconds * 1000;
    return snapshot();
  }

  function history({month, before}) {
    const current = monthFormat.format(new Date());
    const entries = account.entries.filter(row => monthFormat.format(new Date(row.at)) === (month ?? current) &&
      (!before || row.id < before));
    return {entries: entries.slice(0, 50), next: entries.length > 50 ? entries[49].id : null,
      month: month ?? current, oldest: current, current, terminals: config.terminals};
  }

  async function request(path, body = {}) {
    await refresh();
    if (visit && until <= performance.now()) resetVisit();
    if (path === '/api/catalog') return catalog;
    if (path === '/api/kiosk/state') return snapshot();
    const action = path.replace(/^\/api\/kiosk\//, '');
    if (action === 'manual-start' && stage === 'idle') {
      openVisit('manual');
      return snapshot();
    }
    if (!visit || (body.visit !== visit && action !== 'payment')) fail('Die Testsitzung ist abgelaufen.');
    if (action === 'logout') {
      resetVisit();
      return snapshot();
    }
    if (action === 'activity' && stage !== 'receipt') {
      until = performance.now() + config.session_idle * 1000;
      return {remaining: config.session_idle};
    }
    if (action === 'booking-seen') return {};
    if (stage === 'manual') {
      const guests = [guest, registeredGuest].filter(Boolean);
      if (action === 'manual-search') {
        const people = guests.filter(person => personLabel(person).toLowerCase().includes(body.query.toLowerCase()))
          .map(({id, first, last, department}) => ({id, first, last, department}));
        return {people};
      }
      if (action === 'manual-login') {
        if (performance.now() < lockedUntil) fail('Die PIN-Anmeldung ist vorübergehend gesperrt.', 429);
        const person = guests.find(candidate => candidate.id === body.id && candidate.pin === body.pin);
        if (!person) {
          if (++pinFailures >= 5) {
            lockedUntil = performance.now() + 900_000;
            pinFailures = 0;
          }
          fail('Konto oder PIN ungültig.', 403);
        }
        pinFailures = 0;
        account = person;
        stage = 'shop';
        until = performance.now() + config.session_idle * 1000;
        return snapshot();
      }
    }
    if (stage === 'register' && action === 'register') {
      const first = body.first.trim(), last = body.last.trim(), department = body.department.trim();
      if (!first || !last || !department || !body.accepted) fail('Fülle alle Felder aus und bestätige die Hinweise.', 400);
      if (!/^\d{4}$/.test(body.pin) || body.pin !== body.pin_confirmation) fail('Die vierstelligen PINs müssen übereinstimmen.', 400);
      registeredGuest = {id: 2, first, last, department, pin: body.pin, balance: 0, progress: 0,
        payments: [], entries: []};
      account = registeredGuest;
      stage = 'shop';
      until = performance.now() + config.session_idle * 1000;
      return snapshot();
    }
    if (stage !== 'shop') fail('Die Aktion ist in der aktuellen Testsitzung nicht verfügbar.');
    if (action === 'payment') return {link: config.paypal, cash_max: config.cash_max, pending: account.payments};
    if (action === 'history') return history(body);
    if (action === 'cash' || action === 'paypal') {
      const max = action === 'cash' ? config.cash_max : 1_000_000;
      if (!Number.isInteger(body.cents) || body.cents < 1 || body.cents > max) fail('Ungültiger Zahlungsbetrag.', 400);
      if (action === 'cash') return finish('payment', body.cents, body.request);
      const result = {reference: 'TEST-' + ++payment, cents: body.cents, link: config.paypal};
      account.payments.unshift(result);
      return result;
    }
    if (action === 'checkout-quote' || action === 'checkout') {
      const progress = account.progress;
      const quote = await api(PREVIEW_API + '/quote' + query, {lines: body.lines, progress});
      if (stage !== 'shop' || visit !== body.visit || until <= performance.now() || account.progress !== progress) {
        fail('Die Testsitzung oder Sammelkarte hat sich geändert. Prüfe den Warenkorb.');
      }
      if (action === 'checkout-quote') return quote;
      if (quote.discount !== body.discount) fail('Der Sammelkartenbonus hat sich geändert. Prüfe den Warenkorb.');
      account.progress += quote.loyalty_delta;
      const items = quote.lines.map(({name, qty, bonus_qty}) => ({name, quantity: qty, bonus_quantity: bonus_qty}));
      const bonus = quote.lines.filter(line => line.bonus_qty).map(({name, bonus_qty}) => ({name, qty: bonus_qty}));
      return finish('purchase', -quote.total, body.request, {bonus, items,
        stamps: quote.loyalty_delta + config.loyalty.target * bonus.reduce((total, line) => total + line.qty, 0)});
    }
    fail('Die Aktion ist in der aktuellen Testsitzung nicht verfügbar.');
  }

  return {request, updateControls, catalog: () => catalog, paypalQr: PREVIEW_API + '/paypal.svg'};
}
