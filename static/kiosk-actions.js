import {icon} from './art.js';
import {pinField} from './kiosk-keyboard.js';
import {loyaltyCardMarkup} from './loyalty-card.js';
import {api, dateTime, esc, euro, eurosToCents, idempotencyKey, personLabel} from './shared.js';

const monthFormat = new Intl.DateTimeFormat('de-DE', {month: 'long', year: 'numeric', timeZone: 'UTC'});
const historyKinds = {purchase: 'Einkauf', payment: 'Zahlung', correction: 'Korrektur', reversal: 'Storno'};

function moveMonth(month, offset) {
  const [year, number] = month.split('-').map(Number);
  return new Date(Date.UTC(year, number - 1 + offset, 1)).toISOString().slice(0, 7);
}

export function createKioskDialog({path, state, apply, book, cancelManual, request = api, paypalQr, preview = false}) {
  const dialog = document.getElementById('kiosk-dialog');
  const content = document.getElementById('kiosk-dialog-content');
  let generation = 0;
  let focused;
  let timer;

  function close() {
    generation++;
    clearTimeout(timer);
    if (dialog.open) dialog.close();
    content.replaceChildren();
    content.onclick = null;
    focused = null;
  }

  function show(html) {
    content.innerHTML = html;
    focused = content.querySelector('input:not([type=hidden])');
    if (!dialog.open) dialog.showModal();
    focused?.focus();
  }

  function keypad({numeric = false, pin = false, uppercase = false, digits = false} = {}) {
    const rows = numeric ? ['123', '456', '789', pin ? '0⌫' : ',0⌫'] : ['qwertzuiopü', 'asdfghjklöä', 'yxcvbnmß-⌫'];
    if (digits) rows.unshift('1234567890');
    if (uppercase) {
      for (let index = 0; index < rows.length; index++) rows[index] = rows[index].replace('ß', 'ẞ').toUpperCase();
    }
    return '<div class="dialog-keyboard' + (numeric ? ' numeric' : '') + '" aria-label="Bildschirmtastatur">' +
      rows.map(row => '<div>' + [...row].map(char =>
        `<button type="button" data-dialog-key="${char}" aria-label="${char === '⌫' ? 'Zeichen löschen' : char}">${char}</button>`
      ).join('') + '</div>').join('') + (numeric ? '' : '<div><button type="button" data-dialog-key=" ">Leerzeichen</button></div>') + '</div>';
  }

  function heading(title, description) {
    return `<h2 id="kiosk-dialog-title">${title}</h2><p class="muted">${description}</p>`;
  }

  function errors() {
    return '<p class="form-error" role="alert"></p>';
  }

  function showError(error) {
    const element = content.querySelector('.form-error');
    if (element) element.textContent = error.message;
  }

  function manual() {
    close();
    show(heading('Ohne Ausweis anmelden', 'Suche nach deinem Namen oder Referat und wähle dein Konto.') +
      `<label>Name oder Referat suchen<input id="manual-query" type="text" inputmode="none" maxlength="120" autocomplete="off"></label>
      <div id="manual-results" class="manual-results" aria-live="polite">Gib mindestens zwei Zeichen ein.</div>
      ${errors()}${keypad({uppercase: true, digits: true})}`);
  }

  function manualAccount(id, name) {
    show(heading('PIN eingeben', `Konto <strong>${esc(name)}</strong>`) +
      `<form id="manual-form">
        <input type="hidden" name="id" value="${id}">
        ${pinField('pin', 'Vierstellige PIN')}
        ${keypad({numeric: true, pin: true})}${errors()}
        <div class="form-actions"><button type="button" class="button outline" data-manual-back>Zur Suche</button>
        <button class="button primary" type="submit">Anmelden</button></div>
      </form>`);
  }

  async function payment() {
    const visit = state().visit;
    close();
    const revision = generation;
    show(heading('Saldo begleichen', 'Zahlungsmöglichkeiten werden geladen …') + '<p class="form-error" role="alert"></p>');
    let options;
    try {
      options = await request(path('/api/kiosk/payment'));
    } catch (error) {
      if (revision === generation && dialog.open) showError(error);
      return;
    }
    if (revision !== generation || !dialog.open || state()?.visit !== visit) return;
    const open = Math.max(0, -state().profile.balance);
    const methods = '<div class="form-actions"><button class="button primary" data-method="cash">Barzahlung</button>' +
      (options.link ? '<button class="button paypal" data-method="paypal">PayPal</button>' : '') + '</div>';
    show(heading('Saldo begleichen', `Offener Betrag <strong>${euro(open)}</strong>`) + methods +
      (options.pending.length ? '<h3>Offene PayPal-Meldungen</h3><div class="manual-results">' + options.pending.map(item =>
        `<button class="button outline" data-existing="${esc(item.reference)}">${esc(item.reference)} · ${euro(item.cents)}</button>`
      ).join('') + '</div>' : ''));
    content.onclick = event => {
      const button = event.target.closest('button');
      if (!button) return;
      if (button.dataset.method) paymentForm(button.dataset.method, open, options);
      if (button.dataset.existing) {
        const item = options.pending.find(row => row.reference === button.dataset.existing);
        paypalDetails('link' in item ? item.link : options.link, item);
      }
    };
  }

  function paypalImage(link, reference) {
    const params = new URLSearchParams({link});
    if (reference) params.set('reference', reference);
    const image = paypalQr ?? path('/api/kiosk/paypal.svg?' + params);
    return `<div class="paypal-code"><img src="${esc(image)}" alt="${preview ? 'QR-Code mit Testtext' : 'QR-Code zum PayPal.Me-Link'}" width="160" height="160">
      <p class="paypal-link">${esc(link)}</p></div>`;
  }

  function paymentForm(method, open, {link, cash_max: cashMax}) {
    const cash = method === 'cash';
    show(heading(cash ? 'Barzahlung eintragen' : 'PayPal-Zahlung vorbereiten', cash
      ? (preview ? 'Gib einen Testbetrag für die Barzahlung ein.' : 'Lege das Bargeld in die Kasse und gib den gezahlten Betrag ein.')
      : (preview ? 'Gib einen Testbetrag ein und erzeuge eine Testreferenz.'
        : 'Bereite zuerst die Zahlung vor. Übernimm beim Bezahlen am Handy die angezeigte Referenz als Nachricht.')) +
      `<form id="payment-form" data-method="${method}"${cash ? ` data-limit="${cashMax}"` : ''}>
        <label class="amount-entry">Betrag in Euro<input name="amount" type="text" inputmode="none" maxlength="9" required
          value="${open ? esc(((cash ? Math.min(open, cashMax) : open) / 100).toFixed(2).replace('.', ',')) : ''}" placeholder="0,00"></label>
        ${cash ? `<p class="hint cash-limit">Maximal ${euro(cashMax)} je Vorgang</p>` : ''}
        ${keypad({numeric: true})}${errors()}
        <div class="form-actions"><button type="button" class="button outline" data-payment-back>Zurück</button>
        <button class="button ${cash ? 'primary' : 'paypal'}" type="submit">${cash ? 'Bargeld bestätigen' : 'Referenz erzeugen'}</button></div>
      </form>${cash ? '' : paypalImage(link)}`);
    content.dataset.link = link;
    focused?.select();
  }

  function paypalDetails(link, item) {
    const description = preview ? 'Simulierte Zahlungsanweisung mit Testreferenz.'
      : link ? `Scanne den Code, sende <strong>${euro(item.cents)}</strong> und gib diese Referenz als Nachricht ein.`
      : 'Für diese Meldung ist derzeit kein Zahlungslink verfügbar.';
    show(heading('Mit PayPal bezahlen', description) +
      `<p class="payment-reference">${esc(item.reference)}</p>${link ? paypalImage(link, item.reference) : ''}
      <p>Die Meldung ist gespeichert. Der Saldo ändert sich, sobald das Kassen-Team den Zahlungseingang bestätigt.</p>`);
  }

  function loyalty() {
    const card = state().profile.loyalty;
    if (!card) return;
    close();
    show(loyaltyCardMarkup(card, {dialog: true}) +
      '<p class="muted">Jedes bezahlte Heißgetränk bringt einen Stempel. Die Karte gilt an allen Verkaufspunkten. ' +
      'Dein Gratisgetränk wird im Warenkorb automatisch abgezogen.</p>');
  }

  async function confirmPurchase(lines, confirm, catalogChanged) {
    close();
    const visit = state().visit;
    const revision = generation;
    show(heading('Einkauf bestätigen', 'Gesamtbetrag wird berechnet …') + errors());
    let quote;
    try {
      quote = await request(path('/api/kiosk/checkout-quote'), {visit, lines});
    } catch (error) {
      if (revision === generation && dialog.open && state()?.visit === visit) {
        show(heading('Einkauf bestätigen', 'Prüfe deinen Warenkorb und versuche es erneut.') + errors());
        showError(error);
        if (error.status === 409) await catalogChanged();
      }
      return;
    }
    if (revision !== generation || !dialog.open || state()?.visit !== visit) return;
    show(heading('Einkauf bestätigen', 'Prüfe deinen Warenkorb und bestätige den Gesamtbetrag.') +
      `<ul class="purchase-lines">${quote.lines.map(line => {
        const paid = line.qty - line.bonus_qty;
        return `${paid ? `<li><span>${paid} × ${esc(line.name)}</span><strong>${euro(paid * line.cents)}</strong></li>` : ''}
          ${line.bonus_qty ? `<li class="purchase-bonus"><span>${line.bonus_qty} × ${esc(line.name)} · Sammelkartenbonus</span>
          <strong>${euro(0)}</strong></li>` : ''}`;
      }).join('')}</ul>
      ${quote.discount ? `<div class="loyalty-savings">${icon('cup', 18)} Sammelkartenbonus <strong>−${euro(quote.discount)}</strong></div>` : ''}
      <div class="total"><span>Gesamt</span><strong>${euro(quote.total)}</strong></div>
      <button class="button primary" type="button" data-purchase-confirm>${icon('cart', 20)} Kauf bestätigen</button>`);
    content.querySelector('[data-purchase-confirm]').addEventListener('click', () => {
      close();
      confirm({visit, lines, discount: quote.discount});
    }, {once: true});
  }

  function history() {
    close();
    const visit = state().visit;
    const revision = generation;
    let view;
    let entries = [];
    let loading = false;
    show(heading('Deine Buchungen', 'Käufe, Zahlungen und Saldoänderungen.') +
      '<p class="form-error" role="alert"></p><p role="status">Wird geladen …</p>');

    function render() {
      const rows = entries.map(row => {
        const kind = historyKinds[row.kind] + (row.method ? ' · ' + row.method : '');
        const site = row.terminal ? ' · ' + esc(view.terminals[row.terminal]) : '';
        const lines = row.items.map(item => {
          const bonus = item.bonus_quantity ?? 0;
          const paid = item.quantity - bonus;
          return `${paid ? `<li>${paid} × ${esc(item.name)}</li>` : ''}
            ${bonus ? `<li class="history-bonus">${bonus} × ${esc(item.name)} · Sammelkartenbonus (${euro(0)})</li>` : ''}`;
        }).join('');
        return `<li><div><strong>${esc(kind)}</strong><small>${dateTime(row.at)}${site}</small>
          ${lines ? '<ul>' + lines + '</ul>' : ''}</div>
          <strong class="${row.cents < 0 ? 'negative' : ''}">${row.cents > 0 ? '+' : ''}${euro(row.cents)}</strong></li>`;
      }).join('');
      show(heading('Deine Buchungen', 'Käufe, Zahlungen und Saldoänderungen.') +
        `<nav class="history-nav" aria-label="Buchungsmonat">
          <button class="button outline compact" type="button" data-month="-1" aria-label="Vorheriger Monat" ${view.month <= view.oldest ? 'disabled' : ''}>‹</button>
          <strong aria-live="polite">${monthFormat.format(new Date(view.month + '-01T00:00:00Z'))}</strong>
          <button class="button outline compact" type="button" data-month="1" aria-label="Nächster Monat" ${view.month >= view.current ? 'disabled' : ''}>›</button>
        </nav>${errors()}
        <small>Einzelbuchungen der letzten 90 Tage. Dein Saldo enthält auch ältere Buchungen.</small>
        ${rows ? '<ol class="history-entries">' + rows + '</ol>' : '<p>In diesem Monat sind keine Einzelbuchungen mehr verfügbar.</p>'}
        ${view.next ? '<button class="button outline" data-history-more>Ältere Buchungen in diesem Monat</button>' : ''}`);
    }

    async function load(month, before) {
      if (loading) return;
      loading = true;
      try {
        const result = await request(path('/api/kiosk/history'), {visit, month, before});
        if (revision !== generation || !dialog.open || state()?.visit !== visit) return;
        view = result;
        entries = before ? [...entries, ...result.entries] : result.entries;
        render();
      } catch (error) {
        if (revision === generation && dialog.open) showError(error);
      } finally {
        loading = false;
      }
    }
    content.onclick = event => {
      const button = event.target.closest('button');
      if (!button || !view) return;
      if (button.dataset.month) load(moveMonth(view.month, Number(button.dataset.month)));
      if ('historyMore' in button.dataset) load(view.month, view.next);
    };
    load();
  }

  dialog.addEventListener('close', () => {
    if (!dialog.open) {
      const current = state?.();
      close();
      if (current?.stage === 'manual') cancelManual?.(current.visit);
    }
  });
  content.addEventListener('focusin', event => {
    if (event.target.matches('input:not([type=hidden])')) focused = event.target;
  });
  content.addEventListener('pointerdown', event => {
    if (event.target.closest('[data-dialog-key]')) event.preventDefault();
  });
  content.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button) return;
    const d = button.dataset;
    if ('manualBack' in d) manual();
    if ('paymentBack' in d) payment();
    if (d.person) manualAccount(Number(d.person), button.textContent);
    if ('dialogKey' in d && focused?.isConnected) {
      const start = focused.selectionStart, end = focused.selectionEnd;
      const char = d.dialogKey;
      if (char === '⌫') focused.setRangeText('', start === end ? Math.max(0, start - 1) : start, end, 'end');
      else if (focused.value.length - end + start < focused.maxLength) focused.setRangeText(char, start, end, 'end');
      focused.focus();
      focused.dispatchEvent(new Event('input', {bubbles: true}));
    }
  });
  content.addEventListener('input', event => {
    const field = event.target;
    if (field.id !== 'manual-query') return;
    for (const button of content.querySelectorAll('[data-dialog-key]')) {
      const char = button.dataset.dialogKey;
      if (!/^\p{L}$/u.test(char)) continue;
      const letter = field.value ? char.toLowerCase() : char.replace('ß', 'ẞ').toUpperCase();
      if (char === letter) continue;
      button.dataset.dialogKey = letter;
      button.textContent = letter;
      button.setAttribute('aria-label', letter);
    }
    const query = event.target.value.trim();
    const results = content.querySelector('#manual-results');
    clearTimeout(timer);
    results.textContent = query.length >= 2 ? 'Suche läuft …' : 'Gib mindestens zwei Zeichen ein.';
    if (query.length < 2) return;
    timer = setTimeout(async () => {
      try {
        const visit = state()?.stage === 'manual' ? state().visit : null;
        if (!visit) return;
        const found = await request(path('/api/kiosk/manual-search'), {visit, query});
        if (results.isConnected && event.target.value.trim() === query) {
          results.innerHTML = found.people.length ? found.people.map(person =>
            `<button class="button outline" data-person="${person.id}">${esc(personLabel(person))}</button>`
          ).join('') : 'Kein passendes Konto gefunden.';
        }
      } catch (error) {
        if (results.isConnected && event.target.value.trim() === query) results.textContent = error.message;
      }
    }, 220);
  });
  content.addEventListener('submit', async event => {
    event.preventDefault();
    const form = event.target;
    const formId = form.getAttribute('id');
    if (form.dataset.busy) return;
    const revision = generation;
    const fields = new FormData(form);
    const submit = form.querySelector('button[type=submit]');
    form.dataset.busy = '1';
    submit.disabled = true;
    try {
      if (formId === 'manual-form') {
        const visit = state()?.stage === 'manual' ? state().visit : null;
        if (!visit) throw new Error('Die manuelle Anmeldung ist abgelaufen. Beginne erneut.');
        const result = await request(path('/api/kiosk/manual-login'), {visit, id: Number(fields.get('id')), pin: fields.get('pin')});
        if (revision === generation && dialog.open && state()?.stage === 'manual' && state().visit === visit) apply(result);
      } else if (formId === 'payment-form') {
        const cents = eurosToCents(fields.get('amount'));
        if (cents <= 0) throw new Error('Gib einen Betrag größer als 0 € ein.');
        const limit = Number(form.dataset.limit);
        if (limit && cents > limit) throw new Error(`Barzahlungen sind bis ${euro(limit)} pro Vorgang möglich.`);
        const visit = state().visit;
        if (form.dataset.cents !== String(cents)) {
          form.dataset.cents = String(cents);
          form.dataset.request = idempotencyKey();
        }
        const method = form.dataset.method;
        const link = content.dataset.link;
        await book(method, {visit, cents, request: form.dataset.request, ...(method === 'paypal' ? {link} : {})}, result => {
          if (revision !== generation || !dialog.open || state()?.visit !== visit) return false;
          if (method === 'cash') apply(result);
          else paypalDetails(link, result);
          return true;
        });
      }
    } catch (error) {
      if (revision === generation && form.isConnected) {
        if (formId === 'manual-form') {
          form.elements.pin.value = '';
          form.elements.pin.focus();
        }
        showError(formId === 'payment-form' && (!error.status || error.status >= 500) && form.dataset.request
          ? new Error('Buchungsstatus wird geprüft. Warte auf die Bestätigung.') : error);
      }
    } finally {
      delete form.dataset.busy;
      submit.disabled = false;
    }
  });
  return {manual, payment, loyalty, confirmPurchase, history, close};
}
