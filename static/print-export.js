import { esc } from './shared.js';
import { formattedTerms, standLabel } from './terms.js';

const documents = {
  terms: {title: 'Nutzungshinweise', filename: 'KoSTbar-Nutzungshinweise-A4.html'},
  privacy: {title: 'Datenschutzerklärung', filename: 'KoSTbar-Datenschutzerklaerung-A4.html'},
};

export function termsPrintDate(version, now = new Date()) {
  const published = /^(\d{4})(\d{2})(\d{2})-[a-f0-9]{6}$/i.exec(version);
  if (published) return published.slice(1).join('-');
  return new Intl.DateTimeFormat('sv-SE', {
    timeZone: 'Europe/Berlin', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(now);
}

function takeContact(text) {
  const lines = text.split(/\r?\n/);
  const start = lines.findIndex(line => /^##\s+Kontakt bei Rückfragen\s*$/i.test(line.trim()));
  if (start === -1) return {body: text, contact: ''};
  const next = lines.findIndex((line, i) => i > start && /^##\s/.test(line.trim()));
  const end = next === -1 ? lines.length : next;
  return {body: [...lines.slice(0, start), '', ...lines.slice(end)].join('\n'),
    contact: lines.slice(start, end).join('\n')};
}

export function renderPrintDocument(template, {kind, text, date}) {
  const type = documents[kind];
  if (!type || !text.trim()) throw new Error('Gib zuerst den Text für den Ausdruck ein.');
  const {body, contact} = kind === 'terms' ? takeContact(text) : {body: text, contact: ''};
  const draft = kind === 'privacy' && /\[\s*EINTRAGEN\s*:/i.test(text);
  const note = draft ? '## Vor Veröffentlichung\nMarkierte Betreiberangaben ergänzen und mit der Fassung am Terminal abgleichen.' : contact;
  const content = formattedTerms(body).replace(/\[\s*EINTRAGEN\s*:[^\]<]*\]/gi,
    match => '<span class="placeholder">' + match + '</span>');
  const values = {
    TITLE: esc(type.title),
    DATE: esc((draft ? 'Vorlage · ' : '') + standLabel(date)),
    CONTENT: content,
    FOOTER: note ? '<footer class="print-footer" data-editable contenteditable="plaintext-only">' +
      formattedTerms(note) + '</footer>' : '',
    FILENAME: type.filename,
  };
  return {filename: type.filename, html: template.replace(/@@(TITLE|DATE|CONTENT|FOOTER|FILENAME)@@/g,
    (_, key) => values[key])};
}

export async function downloadPrintDocument(data) {
  const response = await fetch('/static/print-document.html', {signal: AbortSignal.timeout(5000)});
  if (!response.ok) throw new Error('Die Druckvorlage konnte nicht geladen werden.');
  const {filename, html} = renderPrintDocument(await response.text(), data);
  const url = URL.createObjectURL(new Blob([html], {type: 'text/html;charset=utf-8'}));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}
