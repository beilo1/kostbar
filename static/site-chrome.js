import {icon} from './art.js';
import {esc} from './shared.js';

export const PROJECT_LABEL = 'beilo1/kostbar';
export const PROJECT_URL = 'https://github.com/' + PROJECT_LABEL;
export const PROJECT_QR = '/static/project-qr.svg';
const PROJECT_TITLE = 'Projekt und Lizenz';

export function projectNotice({qrSource = PROJECT_QR, print = false, showTitle = true} = {}) {
  const license = print
    ? '<p>Der vollständige Lizenztext steht in der Datei <strong>LICENSE</strong> im Projektordner und ist am Terminal lokal einsehbar.</p>'
    : '<details class="project-license"><summary>MIT-Lizenz lokal lesen</summary>' +
      '<div class="project-license-content">Wird geladen …</div></details>';
  return `<section class="project-notice">
    <div>
      ${showTitle ? `<h2>${PROJECT_TITLE}</h2>` : ''}
      <p>KoSTbar steht unter der <strong>MIT-Lizenz</strong>. Der Quellcode ist im öffentlichen GitHub-Repository von <strong>beilo1</strong> verfügbar.</p>
      <p><a href="${PROJECT_URL}" target="_blank" rel="noopener noreferrer">github.com/${PROJECT_LABEL}</a></p>
      ${license}
    </div>
    <img class="project-qr" src="${esc(qrSource)}" alt="QR-Code zum KoSTbar-Repository auf GitHub" width="132" height="132"${print ? '' : ' loading="lazy"'}>
  </section>`;
}

export function bindProjectLicense(root) {
  const license = root.querySelector('.project-license');
  license.addEventListener('toggle', async () => {
    if (!license.open || license.dataset.loading || license.querySelector('pre')) return;
    license.dataset.loading = 'true';
    const content = license.querySelector('.project-license-content');
    try {
      const response = await fetch('/license', {signal: AbortSignal.timeout(5000)});
      if (!response.ok) throw new Error('Lizenztext konnte nicht geladen werden.');
      const text = license.ownerDocument.createElement('pre');
      text.textContent = await response.text();
      content.replaceChildren(text);
    } catch {
      content.textContent = 'Lizenztext konnte nicht geladen werden. Schließe und öffne den Abschnitt erneut.';
    } finally {
      delete license.dataset.loading;
    }
  });
}

export function mountProjectFooter(footer) {
  footer.innerHTML = `<span>© <span data-copyright-year></span> |</span>
    <button type="button" class="footer-link" aria-haspopup="dialog" aria-controls="project-dialog">${PROJECT_LABEL}</button>`;
  const yearLabel = footer.querySelector('[data-copyright-year]');
  const yearFormat = new Intl.DateTimeFormat('de-DE', {year: 'numeric', timeZone: 'Europe/Berlin'});
  const updateYear = () => {
    const year = Number(yearFormat.format(new Date()));
    yearLabel.textContent = year > 2026 ? `2026-${year}` : '2026';
  };
  updateYear();
  setInterval(updateYear, 60_000);

  const dialog = footer.ownerDocument.createElement('dialog');
  dialog.id = 'project-dialog';
  dialog.className = 'panel-dialog';
  dialog.setAttribute('aria-labelledby', 'project-title');
  dialog.innerHTML = `<header class="dialog-header">
      <h2 id="project-title">${PROJECT_TITLE}</h2>
      <button type="button" class="button outline dialog-close" aria-label="Fenster schließen" autofocus>${icon('close', 22)}</button>
    </header>
    <div class="dialog-content project-dialog-content">${projectNotice({showTitle: false})}</div>`;
  bindProjectLicense(dialog);
  footer.ownerDocument.body.append(dialog);
  const trigger = footer.querySelector('button');
  trigger.addEventListener('click', () => dialog.showModal());
  dialog.querySelector('button').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => {
    const {activeElement, body} = footer.ownerDocument;
    if (!activeElement || activeElement === body || dialog.contains(activeElement)) trigger.focus();
  });
}

const projectFooter = globalThis.document?.querySelector('[data-project-footer]');
if (projectFooter) mountProjectFooter(projectFooter);
