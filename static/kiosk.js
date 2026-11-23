import {createKioskDialog} from './kiosk-actions.js';
import {animateReceiptCard, loyaltyCardMarkup} from './loyalty-card.js';
import {keyboardMarkup, pinField} from './kiosk-keyboard.js';
import {acceptsState, canExtendVisit, sessionViewChanged} from './kiosk-session.js';
import {createTerminalPreview, PREVIEW_PAGE} from './terminal-preview.js';
import { icon, terminalArt } from './art.js';
import {adjustCart, shopMarkup, showBasket, showCatalog} from './shop-view.js';
import { api, esc, euro, idempotencyKey, kioskPath, notify } from './shared.js';
import { renderPrivacy, renderTerms } from './terms.js';

const screen = document.getElementById('screen');
const top = document.getElementById('top-actions');
const termsLink = document.getElementById('terms-link');
const privacyLink = document.getElementById('privacy-link');
const termsDialog = document.getElementById('terms-dialog');
const termsContent = document.getElementById('terms-dialog-content');
const timeoutDialog = document.getElementById('timeout-dialog');
const timeoutCountdown = document.getElementById('timeout-countdown');
const INACTIVITY_WARNING_SECONDS = 5;
const preview = location.pathname === PREVIEW_PAGE ? createTerminalPreview() : null;
const kioskApi = preview?.request ?? api;
const instance = !preview && /^#setup=([a-f0-9]{64})$/.exec(location.hash)?.[1];
if (instance) history.replaceState(null, '', location.pathname + location.search);
let state = null;
let deadline = 0;
let catalog = {products: [], categories: {}};
let category = 'cold';
let cart = new Map();
let requestKey;
let pending = false;
let uncertainBooking;
let revision = 0;
let lastActivity = -1000;
let activityTimer;
let expiredVisit;
let resuming = false;
const seenBookings = new Map();
const userDialog = createKioskDialog({
  path: kioskPath,
  request: kioskApi,
  paypalQr: preview?.paypalQr,
  preview: !!preview,
  state: () => state,
  book,
  cancelManual(visit) {
    if (state?.stage === 'manual' && state.visit === visit) action('logout', {});
  },
  apply(result) {
    revision++;
    applyState(result);
  },
});
let toastNotice;
let pollErrors = 0;
let pairingMessage;
let renewDeviceAt = 0;
let focusedField = null;
let upper = false;

function renderIdle() {
  top.replaceChildren();
  screen.innerHTML = `<div class="idle-grid">
    <section class="welcome">
      <div class="eyebrow"><span class="status-dot" id="reader-dot"></span><span id="reader-label"></span></div>
      <h1>Zeit für eine<br><em>Pause.</em></h1>
      <p>Hol dir einen Kaffee, etwas Kaltes oder einen Snack. Dein Dienstausweis meldet dich an.</p>
      <ol class="steps">
        <li><span>01</span> Ausweis anhalten</li><li><span>02</span> Produkte wählen</li><li><span>03</span> Kaufen</li>
      </ol>
      <div class="form-actions"><button class="button outline" data-manual>Ohne Ausweis anmelden</button></div>
    </section>
    <section class="tap-panel" aria-label="Anmeldung mit Dienstausweis">
      <div class="tap-tag">${icon('card', 19)}<span>KARTENANMELDUNG</span></div>
      <div class="terminal-art">${terminalArt()}</div>
      <div class="tap-copy"><h2>Ausweis anhalten</h2><p>Halte deinen Dienstausweis kurz an den Kartenleser.</p></div>
    </section>
  </div>`;
}

function updateIdle() {
  screen.querySelector('[data-manual]').disabled = state.maintenance;
  document.getElementById('reader-label').textContent = state.reader ? 'Kasse bereit' : 'Kartenleser nicht verbunden';
  document.getElementById('reader-dot').classList.toggle('offline', !state.reader || state.maintenance);
  if (state.maintenance) document.getElementById('reader-label').textContent = 'Kartenwechsel · bitte kurz warten';
}

function stageTop() {
  top.innerHTML = `<button class="button outline compact" data-logout>${icon('exit', 19)} <span>Abmelden</span></button>`;
}

function consentFields() {
  return `<div class="consent-box">
    <label class="check-field"><input name="accepted" type="checkbox" required>
      <span>Ich akzeptiere die <a href="${kioskPath('/terms')}" data-terms-link>Nutzungsbedingungen</a>
        und habe die <a href="${kioskPath('/privacy')}" data-privacy-link>Datenschutzerklärung</a> zur Kenntnis genommen.</span></label></div>`;
}

function pinFields() {
  return `<div class="field-pair">
    ${pinField('pin', 'Vierstellige PIN')}${pinField('pin_confirmation', 'PIN bestätigen')}
  </div>`;
}

function renderRegistration() {
  stageTop();
  screen.innerHTML = `<section class="center-card registration registration-entry">
    <div class="round-icon">${icon('card', 27)}</div>
    <p class="eyebrow">ERSTE ANMELDUNG</p><h1>Schön, dass du da bist.</h1>
    <p class="muted">Hinterlege deinen Namen, dein Referat und eine PIN für die Anmeldung ohne Ausweis.</p>
    <form id="register-form">
      <div class="registration-fields">
        <div class="field-pair"><label>Vorname<input name="first" inputmode="none" maxlength="60" autocomplete="off" required></label>
        <label>Nachname<input name="last" inputmode="none" maxlength="60" autocomplete="off" required></label></div>
        <label>Referat<input name="department" inputmode="none" maxlength="80" autocomplete="off" required></label>
        ${pinFields()}
        ${consentFields()}
        <div class="form-actions"><button class="button outline" type="button" data-keyboard>${icon('keyboard', 20)} Tastatur</button>
        <button class="button primary" type="submit">Zum Sortiment ${icon('arrow', 19)}</button></div>
        <p id="register-error" class="form-error" role="alert"></p>
      </div>
      <div id="keyboard" class="keyboard" aria-label="Bildschirmtastatur"></div>
    </form>
  </section>`;
  focusedField = screen.querySelector('[name=first]');
  upper = true;
  renderKeyboard();
  focusedField.focus({preventScroll: true});
}

function renderPinSetup() {
  stageTop();
  screen.innerHTML = `<section class="center-card registration registration-entry">
    <div class="round-icon">${icon('key', 27)}</div>
    <p class="eyebrow">ZUGANG OHNE AUSWEIS</p><h1>Vergib deine PIN.</h1>
    <p class="muted">Wähle vier Ziffern und gib dieselbe PIN zur Bestätigung erneut ein.</p>
    <form id="pin-setup-form">
      <div class="registration-fields">
        ${pinFields()}
        <div class="form-actions"><button class="button primary" type="submit">PIN speichern ${icon('arrow', 19)}</button></div>
        <p id="register-error" class="form-error" role="alert"></p>
      </div>
      <div id="keyboard" class="keyboard" aria-label="Zifferntastatur"></div>
    </form>
  </section>`;
  focusedField = screen.querySelector('[name=pin]');
  renderKeyboard();
  focusedField.focus({preventScroll: true});
}

function renderConsent() {
  stageTop();
  screen.innerHTML = `<section class="center-card registration">
    <div class="round-icon">${icon('card', 27)}</div>
    <p class="eyebrow">VOR DEM EINKAUF</p><h1>Nutzung und Datenschutz</h1>
    <p class="muted">Bitte akzeptiere die Nutzungsbedingungen und lies die Datenschutzerklärung, um dein Konto weiter zu nutzen.</p>
    <form id="consent-form">${consentFields()}
      <div class="form-actions"><button class="button primary" type="submit">Zum Sortiment ${icon('arrow', 19)}</button></div>
      <p id="register-error" class="form-error" role="alert"></p>
    </form></section>`;
  screen.querySelector('[name=accepted]').focus({preventScroll: true});
}

function showTerms(privacy = false) {
  const content = document.createElement('div');
  content.textContent = 'Wird geladen …';
  termsContent.replaceChildren(content);
  termsContent.scrollTop = 0;
  document.getElementById('terms-title').textContent = privacy ? 'Datenschutzerklärung' : 'Nutzungsbedingungen';
  if (!termsDialog.open) termsDialog.showModal();
  if (privacy) renderPrivacy(content);
  else renderTerms(content, state?.version);
}

termsLink.addEventListener('click', event => {
  if (!state || state.stage === 'idle') return;
  event.preventDefault();
  showTerms();
});

privacyLink.addEventListener('click', event => {
  if (!state || state.stage === 'idle') return;
  event.preventDefault();
  showTerms(true);
});

function renderKeyboard() {
  const keyboard = document.getElementById('keyboard');
  const numeric = focusedField?.type === 'password';
  keyboard.classList.toggle('numeric', numeric);
  keyboard.setAttribute('aria-label', numeric ? 'Zifferntastatur' : 'Bildschirmtastatur');
  keyboard.innerHTML = keyboardMarkup(upper, numeric);
}

function renderShop() {
  stageTop();
  screen.innerHTML = shopMarkup(Boolean(state.profile.loyalty));
  renderCatalog();
  renderBasket();
  updateProfile();
}

function updateProfile() {
  document.getElementById('greeting').textContent = 'Hallo, ' + state.profile.first + '.';
  const balance = document.getElementById('balance');
  balance.textContent = euro(state.profile.balance);
  balance.classList.toggle('negative', state.profile.balance < 0);
  const loyaltyStatus = document.getElementById('loyalty-status');
  if (loyaltyStatus) {
    const card = state.profile.loyalty;
    loyaltyStatus.textContent = card.ready ? 'Bonus bereit' : card.stamps + ' / ' + card.target;
    loyaltyStatus.classList.toggle('ready', card.ready > 0);
  }
}

function renderCatalog() {
  showCatalog(screen, catalog, category);
}

function renderBasket() {
  showBasket(screen, cart, {pending, uncertainBooking});
}

function bonusNames(lines) {
  return lines.map(line => (line.qty === 1 ? '' : line.qty + ' × ') + esc(line.name)).join(' · ');
}

function renderReceipt() {
  top.replaceChildren();
  const receipt = state.receipt;
  const bonus = receipt.bonus ?? [];
  const hasBonus = bonus.length > 0;
  const redeemed = bonus.reduce((sum, line) => sum + line.qty, 0);
  const card = receipt.loyalty ? loyaltyCardMarkup(receipt.loyalty, {newStamps: receipt.stamps_earned, redeemed}) : '';
  const heading = hasBonus ? (redeemed === 1 ? 'Ein Getränk geht aufs Haus.' : 'Diese Getränke gehen aufs Haus.')
    : receipt.kind === 'cash' ? 'Barzahlung gebucht.' : 'Einkauf gebucht.';
  const detail = receipt.kind === 'cash' ? `${euro(receipt.total)} wurden deinem Kassenkonto gutgeschrieben.`
    : receipt.total ? `Deinem Kassenkonto wurden ${euro(receipt.total)} belastet.` : 'Dein Saldo bleibt gleich.';
  screen.innerHTML = `<section class="center-card receipt${card ? ' receipt-with-loyalty' : ''}${hasBonus ? ' bonus-receipt' : ''}">
    <div class="receipt-summary">
      <div class="round-icon success">${icon(hasBonus ? 'cup' : 'check', 34)}</div>
      <p class="eyebrow">${hasBonus ? 'SAMMELKARTENBONUS · ' : ''}BUCHUNG #${receipt.entry}</p>
      <h1>${heading}</h1>
      ${hasBonus ? `<p class="receipt-free">${bonusNames(bonus)} · gratis</p>` : ''}
      <p class="muted">${detail}</p>
      <div class="receipt-balance"><span>Dein neuer Saldo</span><strong class="${receipt.balance < 0 ? 'negative' : ''}">${euro(receipt.balance)}</strong></div>
      <p class="countdown">Automatische Abmeldung in <strong id="countdown">${Math.ceil(state.remaining)}</strong> s</p>
      <button class="button outline" data-logout>Jetzt abmelden</button>
    </div>
    ${card}
  </section>`;
  animateReceiptCard(screen);
}

function renderRecoveredBooking() {
  stageTop();
  const booking = state.booking;
  const paypal = booking.kind === 'paypal';
  const title = paypal ? 'PayPal-Meldung gefunden.' : booking.kind === 'cash' ? 'Barzahlung gebucht.' : 'Einkauf gebucht.';
  const detail = paypal ? `Referenz <strong>${esc(booking.reference)}</strong> · ${euro(booking.total)}.
    ${booking.status === 'pending' ? 'Öffne „Saldo begleichen“, um diese Meldung weiterzuverwenden.' : 'Das Kassen-Team hat diese Meldung bereits bearbeitet.'}`
    : `Der Vorgang über <strong>${euro(booking.total)}</strong> wurde bereits gebucht.`;
  screen.innerHTML = `<section class="center-card receipt">
    <div class="round-icon success">${icon('check', 34)}</div><h1>${title}</h1>
    <p>${detail}</p>
    ${booking.bonus?.length ? `<p class="receipt-free">${bonusNames(booking.bonus)} · gratis mit deiner Sammelkarte</p>` : ''}
    <div class="receipt-balance"><span>Dein aktueller Saldo</span><strong>${euro(state.profile.balance)}</strong></div>
    <div class="form-actions centered-actions"><button class="button primary" data-booking-seen>Verstanden und weiter</button></div>
  </section>`;
}

async function confirmSeen(visit, kind, request) {
  const existing = seenBookings.get(request);
  if (existing?.sending || existing?.done) return;
  const confirmation = {visit, kind, sending: true};
  seenBookings.set(request, confirmation);
  try {
    await kioskApi(kioskPath('/api/kiosk/booking-seen'), {visit, kind, request});
    confirmation.done = true;
  } catch (error) {
    if (error.status && error.status < 500) seenBookings.delete(request);
  } finally {
    confirmation.sending = false;
  }
}

async function book(method, body, onSuccess) {
  if (pending || state?.booking || (uncertainBooking && uncertainBooking.body.request !== body.request)) return;
  pending = true;
  revision++;
  renderBasket();
  try {
    const result = await kioskApi(kioskPath('/api/kiosk/' + method), body);
    uncertainBooking = undefined;
    if (state?.visit === body.visit && onSuccess(result)) {
      confirmSeen(body.visit, method === 'checkout' ? 'purchase' : method, body.request);
    }
  } catch (error) {
    uncertainBooking = (!error.status || error.status >= 500) && state?.visit === body.visit
      ? {method, body, onSuccess} : undefined;
    throw error;
  } finally {
    pending = false;
    revision++;
    renderBasket();
  }
}

function applyState(next) {
  if (!acceptsState(next, expiredVisit)) return;
  const changed = sessionViewChanged(state, next);
  const previousVisit = state?.visit ?? uncertainBooking?.body.visit;
  const newVisit = next.visit !== previousVisit;
  state = next;
  preview?.updateControls(next);
  document.getElementById('site-name').textContent = next.terminal;
  termsLink.href = kioskPath('/terms');
  privacyLink.href = kioskPath('/privacy');
  deadline = performance.now() + next.remaining * 1000;
  if (newVisit || next.stage === 'idle') {
    cart = new Map();
    requestKey = undefined;
    category = 'cold';
  }
  if (newVisit) seenBookings.clear();
  if (next.booking || next.stage !== 'shop' || uncertainBooking?.body.visit !== next.visit) uncertainBooking = undefined;
  if (changed) {
    if (timeoutDialog.open) timeoutDialog.close();
    userDialog.close();
    if (termsDialog.open) termsDialog.close();
    if (next.stage === 'idle') renderIdle();
    if (next.stage === 'manual') {
      renderIdle();
      userDialog.manual();
    }
    if (next.stage === 'register') renderRegistration();
    if (next.stage === 'consent') renderConsent();
    if (next.stage === 'pin-setup') renderPinSetup();
    if (next.stage === 'shop') {
      if (next.booking) {
        cart.clear();
        requestKey = undefined;
        renderRecoveredBooking();
      } else {
        renderShop();
        updateCatalog().catch(error => notify(error.message));
      }
    }
    if (next.stage === 'receipt') renderReceipt();
  }
  if (next.stage === 'idle' || next.stage === 'manual') {
    updateIdle();
    if (next.notice && next.notice !== toastNotice) notify(next.notice);
    toastNotice = next.notice;
  }
  if (next.stage === 'shop' && !next.booking) updateProfile();
  updateTimers();
}

function updateTimers() {
  const remaining = Math.max(0, Math.ceil((deadline - performance.now()) / 1000));
  const countdown = document.getElementById('countdown');
  if (countdown) countdown.textContent = remaining;
  const warn = state?.visit && state.stage !== 'receipt' && remaining > 0 && remaining <= INACTIVITY_WARNING_SECONDS;
  if (warn) {
    timeoutCountdown.textContent = remaining;
    if (!timeoutDialog.open) timeoutDialog.showModal();
  } else if (timeoutDialog.open) {
    timeoutDialog.close();
  }
  if (!remaining && state?.visit && !activityTimer) {
    const visit = state.visit;
    expiredVisit = visit;
    applyState({...state, stage: 'idle', visit: null, remaining: 0, notice: null});
    kioskApi(kioskPath('/api/kiosk/logout'), {visit}).catch(() => {});
  }
}

async function updateCatalog() {
  catalog = await kioskApi(kioskPath('/api/catalog'));
  renderCatalog();
}

async function poll() {
  const stamp = revision;
  let delay = 550;
  try {
    if (!pending) {
      const next = await kioskApi(kioskPath('/api/kiosk/state'));
      if (stamp === revision) {
        const request = next.booking?.request || next.receipt?.request;
        const seen = seenBookings.get(request);
        if (next.booking && seen?.visit === next.visit && !state?.booking) {
          delete next.booking;
          confirmSeen(seen.visit, seen.kind, request);
        }
        applyState(next);
        if (preview && next.stage === 'shop' && catalog !== preview.catalog()) {
          catalog = preview.catalog();
          renderCatalog();
        }
        if (next.stage === 'receipt' && request && state?.visit === next.visit) {
          confirmSeen(next.visit, next.receipt.kind === 'cash' ? 'cash' : 'purchase', request);
        }
        if (uncertainBooking) {
          const {method, body, onSuccess} = uncertainBooking;
          await book(method, body, onSuccess).catch(error => {
            if (error.status && error.status < 500) notify(error.message);
          });
        }
      }
      pollErrors = 0;
      const clock = performance.now();
      if (!preview && clock >= renewDeviceAt) {
        renewDeviceAt = clock + 86_400_000;
        api('/api/kiosk/pair', {}).catch(() => { renewDeviceAt = performance.now() + 60_000; });
      }
    }
  } catch (error) {
    if (!preview && error.status === 403 && stamp === revision) {
      if (state) {
        applyState({stage: 'idle', visit: null, remaining: 0, terminal: '', reader: false});
        state = null;
      }
      delay = 2000;
      try {
        const pairing = await api('/api/kiosk/pair', {instance});
        if (pairing.paired) {
          pairingMessage = null;
          renewDeviceAt = performance.now() + 86_400_000;
          delay = 0;
        } else {
          showPairing(pairing, '');
        }
      } catch (failure) {
        showPairing(null, failure.message);
      }
      return;
    }
    pollErrors++;
    if (stamp === revision && (pollErrors >= 2 || (preview && [400, 401, 403].includes(error.status)))) {
      state = null;
      pairingMessage = null;
      if (timeoutDialog.open) timeoutDialog.close();
      userDialog.close();
      if (termsDialog.open) termsDialog.close();
      cart.clear();
      top.replaceChildren();
      screen.innerHTML = '<section class="center-card"><h1>Terminal wartet</h1><p class="muted">' +
        (uncertainBooking ? 'Der Buchungsstatus wird nach der Wiederverbindung geprüft.' : esc(error.message)) +
        '</p><p>Die Verbindung wird automatisch erneut aufgebaut.</p></section>';
    }
  } finally {
    setTimeout(poll, delay);
  }
}

function showPairing(pairing, message) {
  const key = pairing?.code || message;
  if (key === pairingMessage) return;
  pairingMessage = key;
  top.replaceChildren();
  screen.innerHTML = `<section class="center-card"><h1>Terminal koppeln</h1>
    ${pairing ? `<p><strong>${esc(pairing.label)} (Terminal ${esc(pairing.site)})</strong></p>
      <p>Bestätige diesen Code unter Verwaltung → Verkaufspunkte beim angezeigten Terminal.</p>
      <p class="pairing-code">${esc(pairing.code)}</p><p>Der Code ist fünf Minuten gültig.</p>` :
      `<p role="status">${esc(instance ? message : 'Starte Chromium über den Kiosk-Autostart auf dem Raspberry Pi.')}</p>`}
    </section>`;
}

async function action(path, body, handleError = error => notify(error.message)) {
  if (pending) return;
  const visit = state?.visit;
  pending = true;
  revision++;
  renderBasket();
  try {
    const result = await kioskApi(kioskPath('/api/kiosk/' + path), {visit, ...body});
    if (state?.visit === visit) applyState(result);
  } catch (error) {
    await handleError(error);
  } finally {
    pending = false;
    revision++;
    renderBasket();
  }
}

function activity() {
  if (timeoutDialog.open || !canExtendVisit(state)) return;
  const visit = state.visit;
  const wait = Math.max(0, 250 - (performance.now() - lastActivity));
  if (activityTimer) return;
  activityTimer = setTimeout(() => {
    activityTimer = null;
    if (!canExtendVisit(state, visit)) return;
    lastActivity = performance.now();
    kioskApi(kioskPath('/api/kiosk/activity'), {visit}).then(response => {
      if (canExtendVisit(state, visit)) deadline = performance.now() + response.remaining * 1000;
    }).catch(() => {});
  }, wait);
}

function adjust(id, step) {
  adjustCart(cart, catalog, id, step);
  requestKey = undefined;
  renderBasket();
}

function pressKey(key) {
  if (!focusedField?.isConnected) return;
  if (key === 'shift') {
    upper = !upper;
    renderKeyboard();
    return;
  }
  if (key === 'next') {
    const inputs = Array.from(focusedField.form.querySelectorAll('input:not([type=checkbox])'));
    inputs[(inputs.indexOf(focusedField) + 1) % inputs.length].focus();
    return;
  }
  const input = focusedField;
  const start = input.selectionStart;
  const end = input.selectionEnd;
  if (key === 'delete') input.setRangeText('', start === end ? Math.max(0, start - 1) : start, end, 'end');
  else {
    const value = key === 'space' ? ' ' : key;
    if (input.value.length - (end - start) + value.length <= input.maxLength) input.setRangeText(value, start, end, 'end');
  }
  input.focus();
  if (input.type !== 'password' && ((upper && /^\p{L}$/u.test(key)) || (key === 'delete' && !input.value))) {
    upper = !input.value;
    renderKeyboard();
  }
}

document.addEventListener('pointerdown', event => {
  activity();
  if (event.target.closest('[data-key]')) event.preventDefault();
});
document.addEventListener('focusin', event => {
  if (event.target !== focusedField && event.target.matches('#register-form input:not([type=checkbox]), #pin-setup-form input')) {
    focusedField = event.target;
    upper = !focusedField.value;
    renderKeyboard();
  }
});
document.addEventListener('input', event => {
  if (event.target === focusedField && focusedField.type !== 'password') {
    const empty = focusedField.value === '';
    if (empty !== upper) {
      upper = empty;
      renderKeyboard();
    }
  }
  activity();
});
document.addEventListener('keydown', activity);
document.addEventListener('click', activity);
timeoutDialog.addEventListener('cancel', event => event.preventDefault());
timeoutDialog.querySelector('[data-resume]').addEventListener('click', async () => {
  if (resuming || !state?.visit) return;
  const visit = state.visit;
  resuming = true;
  const stamp = ++revision;
  try {
    const response = await kioskApi(kioskPath('/api/kiosk/activity'), {visit});
    if (state?.visit === visit && revision === stamp) {
      deadline = performance.now() + response.remaining * 1000;
      updateTimers();
    }
  } catch (error) {
    if (state?.visit === visit) notify(error.message);
  } finally {
    resuming = false;
    revision++;
  }
});
document.addEventListener('click', event => {
  if (event.target.closest('[data-privacy-link]')) {
    event.preventDefault();
    showTerms(true);
    return;
  }
  if (event.target.closest('[data-terms-link]')) {
    event.preventDefault();
    showTerms();
    return;
  }
  const button = event.target.closest('button');
  if (!button || pending || !state) return;
  const d = button.dataset;
  if ('manual' in d) action('manual-start', {});
  if ('payment' in d && !uncertainBooking) userDialog.payment();
  if ('history' in d) userDialog.history();
  if ('loyalty' in d) userDialog.loyalty();
  if ('bookingSeen' in d && state.booking) {
    const {visit, booking} = state;
    button.disabled = true;
    confirmSeen(visit, booking.kind, booking.request).finally(() => { button.disabled = false; });
  }
  if ('logout' in d) action('logout', {});
  if (d.category) {
    category = d.category;
    renderCatalog();
  }
  if (d.add && !uncertainBooking) adjust(Number(d.add), 1);
  if (d.qty && !uncertainBooking) adjust(Number(d.qty), Number(d.step));
  if ('keyboard' in d) {
    const keyboard = document.getElementById('keyboard');
    keyboard.hidden = !keyboard.hidden;
    if (!keyboard.hidden) focusedField?.focus();
  }
  if (d.key) pressKey(d.key);
  if ('checkout' in d && cart.size) {
    const visit = state.visit;
    const refreshCart = async () => {
      if (state?.visit !== visit || state.stage !== 'shop') return;
      await updateCatalog().catch(() => {});
      if (state?.visit !== visit || state.stage !== 'shop') return;
      for (const [id, line] of cart) {
        const replacement = catalog.products.find(p => p.id === id);
        if (replacement) cart.set(id, {...replacement, qty: line.qty});
        else cart.delete(id);
      }
      requestKey = undefined;
      renderBasket();
    };
    const lines = Array.from(cart.values(), ({id, qty, cents}) => ({id, qty, cents}));
    userDialog.confirmPurchase(lines, async quote => {
      requestKey ||= idempotencyKey();
      try {
        await book('checkout', {...quote, request: requestKey}, result => {
          applyState(result);
          return result.stage === 'receipt';
        });
      } catch (error) {
        notify(error.status && error.status < 500 ? error.message : 'Buchungsstatus wird geprüft. Warte auf die Bestätigung.');
        if (error.status === 409) await refreshCart();
      }
    }, refreshCart);
  }
});
document.addEventListener('submit', event => {
  const path = {'register-form': 'register', 'consent-form': 'accept-terms', 'pin-setup-form': 'pin-setup'}[event.target.id];
  if (!path) return;
  event.preventDefault();
  const fields = new FormData(event.target);
  const error = document.getElementById('register-error');
  error.textContent = '';
  const body = Object.fromEntries(fields);
  if (path !== 'pin-setup') {
    Object.assign(body, {accepted: fields.has('accepted'), version: state.version, privacy_version: state.privacy_version});
  }
  action(path, body, failure => { error.textContent = failure.message; });
});
setInterval(updateTimers, 200);
poll();
