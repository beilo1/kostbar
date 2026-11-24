const currency = new Intl.NumberFormat('de-DE', {style: 'currency', currency: 'EUR'});
const dateFormat = new Intl.DateTimeFormat('de-DE', {day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Berlin'});
export const euro = cents => currency.format(cents / 100);
export const dateTime = iso => dateFormat.format(new Date(iso));
export function personLabel(person) {
  const name = person.name || [person.first, person.last].filter(Boolean).join(' ');
  return name + (person.department ? ' (' + person.department + ')' : '');
}
const entities = {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'};
export const esc = value => String(value ?? '').replace(/[&<>"']/g, c => entities[c]);
export const idempotencyKey = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('');

export async function api(path, body) {
  let response;
  try {
    response = await fetch(path, body === undefined ? {signal: AbortSignal.timeout(5000)} : {
      signal: AbortSignal.timeout(5000), method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
    });
  } catch {
    throw new Error('Keine Verbindung zu KoSTbar. Bitte erneut versuchen.');
  }
  const result = await response.json().catch(() => null);
  if (!response.ok) {
    const error = new Error(result?.error || 'Anfrage fehlgeschlagen.');
    error.status = response.status;
    throw error;
  }
  if (!result) throw new Error('Unvollständige Antwort von KoSTbar. Bitte erneut versuchen.');
  return result;
}

let toastTimer;
export function notify(text) {
  const node = document.getElementById('toast');
  node.textContent = text;
  node.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { node.hidden = true; }, 4600);
}

export function eurosToCents(value) {
  const clean = value.trim();
  if (!/^[+-]?\d{1,6}(?:[,.]\d{1,2})?$/.test(clean)) {
    throw new Error('Gib einen Eurobetrag ein, zum Beispiel 2,50.');
  }
  const [whole, part = ''] = clean.replace(/^[+-]/, '').split(/[,.]/);
  return (clean.startsWith('-') ? -1 : 1) * (Number(whole) * 100 + Number(part.padEnd(2, '0')));
}

const copyrightYear = globalThis.document?.getElementById('copyright-year');
if (copyrightYear) {
  const firstYear = 2026;
  const yearFormat = new Intl.DateTimeFormat('de-DE', {year: 'numeric', timeZone: 'Europe/Berlin'});
  const updateCopyrightYear = () => {
    const year = Number(yearFormat.format(new Date()));
    copyrightYear.textContent = year > firstYear ? String(firstYear) + '-' + year : String(firstYear);
  };
  updateCopyrightYear();
  setInterval(updateCopyrightYear, 60_000);
}
