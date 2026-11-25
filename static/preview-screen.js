import {PREVIEW_SCREEN} from './terminal-preview.js';

const viewport = document.getElementById('preview-viewport');
const screen = document.getElementById('preview-screen');
const terminal = new URLSearchParams(location.search).get('terminal');

new ResizeObserver(([entry]) => {
  screen.style.transform = `scale(${entry.contentRect.width / screen.width})`;
}).observe(viewport);
screen.src = PREVIEW_SCREEN + '?' + new URLSearchParams({terminal});
