import { api, esc, kioskPath } from './shared.js';

export function termsText(terms) {
  if (typeof terms.body === 'string') return terms.body;
  return [
    ...terms.sections.map(section => '## ' + section.title + '\n' + section.text),
    '## Kontakt bei Rückfragen\n**' + terms.contact + '**\n' + terms.reach,
  ].join('\n\n');
}

function inline(text) {
  return esc(text).replace(/\*\*([^*]+)\*\*|__([^_]+)__/g, (_, bold, underlined) =>
    bold ? '<strong>' + bold + '</strong>' : '<u>' + underlined + '</u>');
}

export function formattedTerms(text) {
  const output = [];
  let bullets = [];
  function flush() {
    if (bullets.length) {
      output.push('<ul>' + bullets.map(line => '<li>' + inline(line) + '</li>').join('') + '</ul>');
      bullets = [];
    }
  }
  for (const raw of text.split('\n')) {
    const line = raw.trim();
    if (line.startsWith('- ')) {
      bullets.push(line.slice(2));
      continue;
    }
    flush();
    if (line.startsWith('### ')) output.push('<h3>' + inline(line.slice(4)) + '</h3>');
    else if (line.startsWith('## ')) output.push('<h2>' + inline(line.slice(3)) + '</h2>');
    else if (line) output.push('<p>' + inline(line) + '</p>');
  }
  flush();
  return '<div class="terms-rich">' + output.join('') + '</div>';
}

export async function renderTerms(node, version) {
  try {
    const terms = await api(kioskPath('/api/terms'));
    if (version && version !== terms.version) throw new Error('Die Fassung wurde aktualisiert. Öffne die Kasse erneut.');
    node.innerHTML = `<p class="terms-version">${esc(standLabel(terms.date))}</p>` + formattedTerms(termsText(terms));
  } catch (error) {
    node.textContent = error.message;
  }
}

export function standLabel(date) {
  return 'Stand ' + (date ? date.split('-').reverse().join('.') : '–');
}

export async function renderPrivacy(node) {
  try {
    const document = await api(kioskPath('/api/privacy'));
    node.innerHTML = `<p class="terms-version">${esc(standLabel(document.date))}</p>` +
      (document.template ? '<p class="notice">Vorlage. Die Angaben des Betreibers sind noch zu ergänzen.</p>' : '') +
      formattedTerms(document.body);
  } catch (error) {
    node.textContent = error.message;
  }
}

const standalone = document.getElementById('terms-content');
if (standalone) renderTerms(standalone);
const privacyPage = document.getElementById('privacy-content');
if (privacyPage) renderPrivacy(privacyPage);
