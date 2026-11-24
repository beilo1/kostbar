import { api, esc } from './shared.js';
import { PROJECT_LABEL, PROJECT_QR, PROJECT_URL } from './site-chrome.js';

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
    const terms = await api('/api/terms');
    if (version && version !== terms.version) throw new Error('Die Fassung wurde aktualisiert. Öffne die Kasse erneut.');
    node.innerHTML = `<p class="terms-version">${esc(standLabel(terms.date))}</p>` + formattedTerms(termsText(terms));
  } catch (error) {
    node.textContent = error.message;
  }
  node.insertAdjacentHTML('beforeend', projectNotice());
  const license = node.querySelector('.project-license');
  license.addEventListener('toggle', async () => {
    if (!license.open || license.dataset.loading || license.querySelector('pre')) return;
    license.dataset.loading = 'true';
    const content = license.querySelector('.project-license-content');
    try {
      const response = await fetch('/license', {signal: AbortSignal.timeout(5000)});
      if (!response.ok) throw new Error('Lizenztext konnte nicht geladen werden.');
      const text = document.createElement('pre');
      text.textContent = await response.text();
      content.replaceChildren(text);
    } catch {
      content.textContent = 'Lizenztext konnte nicht geladen werden. Schließe und öffne den Abschnitt erneut.';
    } finally {
      delete license.dataset.loading;
    }
  });
}

export function projectNotice({qrSource = PROJECT_QR, print = false} = {}) {
  const license = print
    ? '<p>Der vollständige Lizenztext steht in der Datei <strong>LICENSE</strong> im Projektordner und ist am Terminal lokal einsehbar.</p>'
    : '<details class="project-license"><summary>MIT-Lizenz lokal lesen</summary>' +
      '<div class="project-license-content">Wird geladen …</div></details>';
  return `<section class="project-notice">
    <div>
      <h2>Projekt und Lizenz</h2>
      <p>KoSTbar steht unter der <strong>MIT-Lizenz</strong>. Der Quellcode ist im öffentlichen GitHub-Repository von <strong>beilo1</strong> verfügbar.</p>
      <p><a href="${PROJECT_URL}" target="_blank" rel="noopener noreferrer">github.com/${PROJECT_LABEL}</a></p>
      ${license}
    </div>
    <img class="project-qr" src="${esc(qrSource)}" alt="QR-Code zum KoSTbar-Repository auf GitHub" width="132" height="132">
  </section>`;
}

export function standLabel(date) {
  return 'Stand ' + (date ? date.split('-').reverse().join('.') : '–');
}

export async function renderPrivacy(node) {
  try {
    const document = await api('/api/privacy');
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
