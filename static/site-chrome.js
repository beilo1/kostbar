import {icon} from './art.js';

export const PROJECT_LABEL = 'beilo1/kostbar';
export const PROJECT_URL = 'https://github.com/' + PROJECT_LABEL;
export const PROJECT_QR = '/static/project-qr.svg';

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
      <h2 id="project-title">KoSTbar auf GitHub</h2>
      <button type="button" class="button outline dialog-close" aria-label="Fenster schließen" autofocus>${icon('close', 22)}</button>
    </header>
    <div class="dialog-content project-dialog-content">
      <img class="project-qr" src="${PROJECT_QR}" alt="QR-Code zum KoSTbar-Repository auf GitHub" width="176" height="176" loading="lazy">
      <a href="${PROJECT_URL}" target="_blank" rel="noopener noreferrer">github.com/${PROJECT_LABEL}</a>
    </div>`;
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
