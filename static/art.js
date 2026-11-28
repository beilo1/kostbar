const strokes = {
  cup: '<path d="M4 7h13v7a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5V7Zm13 2h2a3 3 0 0 1 0 6h-2M3 22h16M8 2v2m5-2v2"/>',
  glass: '<path d="M6 8h12l-2 13H8L6 8Zm-1 0h14M12 8l2-6h4M8 13h8"/>',
  snack: '<path d="M3 9h18v4H3zm2-1a7 5 0 0 1 14 0M5 15v2a3 3 0 0 0 3 3h8a3 3 0 0 0 3-3v-2M9 7h.01m5 0h.01"/>',
  candy: '<path d="m8 16-5 3 1-5-2-3 5-1m9-2 5-3-1 5 2 3-5 1"/><rect x="7" y="7" width="10" height="10" rx="3" transform="rotate(-35 12 12)"/>',
  card: '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M6 14h4m-4-4h2m6 4a4 4 0 0 0 0-4m3 6a7 7 0 0 0 0-8"/>',
  exit: '<path d="M10 4H5v16h5m4-12 4 4-4 4m-5-4h10"/>',
  cart: '<path d="M2 3h3l3 12h11l3-8H6"/><circle cx="9" cy="20" r="1"/><circle cx="18" cy="20" r="1"/>',
  edit: '<path d="m4 16-1 5 5-1L21 7l-4-4L4 16Zm10-10 4 4"/>',
  trash: '<path d="M3 6h18M9 6V3h6v3m4 0-1 15H6L5 6m5 4v7m4-7v7"/>',
  undo: '<path d="M8 4 3 9l5 5M3 9h11a6 6 0 0 1 0 12h-3"/>',
  key: '<circle cx="16" cy="8" r="5"/><path d="m12 12-9 9v-4l2-2h3v-2l3-3"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
  history: '<path d="M3 12a9 9 0 1 1 3 7M3 6v6h6m3-5v5l3 2"/>',
  wallet: '<rect x="2.5" y="5.5" width="18.5" height="14" rx="2.5"/><path d="M5 5.5 16 2l1 3.5"/><path fill="var(--leaf)" d="M17 10h5v5h-5a2.5 2.5 0 0 1 0-5Z"/><path d="M17 12.5h.1"/>',
  table: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M3 14h18M10 9v11"/>',
  bag: '<path d="M4 8h16l1 13H3L4 8Zm4 1V6a4 4 0 0 1 8 0v3"/>',
  check: '<path d="m4 12 5 5L20 6"/>',
  arrow: '<path d="M4 12h15m-6-6 6 6-6 6"/>',
  up: '<path d="M12 19V5m-6 6 6-6 6 6"/>',
  down: '<path d="M12 5v14m-6-6 6 6 6-6"/>',
  chocolate: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M12 3v18M5 9h14M5 15h14"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/>',
  plus: '<path d="M5 12h14m-7-7v14"/>',
  minus: '<path d="M5 12h14"/>',
  keyboard: '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M6 9h.1m4 0h.1m4 0h.1m4 0h.1M6 13h.1m12 0h.1M9 15h6"/>',
};
export const categoryIcons = {
  drink: 'glass', cold: 'glass', hot: 'cup', snack: 'snack', sweet: 'candy', chocolate: 'chocolate',
};
export function icon(name, size = 24) {
  return '<svg width="' + size + '" height="' + size + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + strokes[name] + '</svg>';
}

export function terminalArt() {
  return `<svg viewBox="0 0 420 340" fill="none" aria-hidden="true">
    <circle cx="212" cy="166" r="134" stroke="#aeca96" stroke-opacity=".33"/>
    <circle cx="212" cy="166" r="108" stroke="#aeca96" stroke-opacity=".4" stroke-dasharray="3 7"/>
    <circle cx="212" cy="166" r="82" fill="#2f5345"/>
    <path d="M80 237h17m-8-8v16m240-151h16m-8-8v16m-203-53h10m-5-5v10" stroke="#d9ebac" stroke-width="2" stroke-linecap="round"/>
    <path d="M52 122h20m287 95h10" stroke="#88a993" stroke-width="2" stroke-linecap="round"/>
    <rect x="144" y="128" width="169" height="112" rx="16" transform="rotate(12 144 128)" fill="#a8caa5" stroke="#132c23" stroke-width="3"/>
    <path d="m148 206 143 30" stroke="#719981" stroke-width="2"/>
    <g transform="rotate(-12 192 148)">
      <rect x="110" y="94" width="173" height="112" rx="16" fill="#e2efae" stroke="#132c23" stroke-width="3"/>
      <rect x="128" y="116" width="52" height="52" rx="10" fill="#f8f9d8" stroke="#203e32" stroke-width="2"/>
      <path d="M142 141h23v8a8 8 0 0 1-8 8h-7a8 8 0 0 1-8-8v-8Zm23 2h3a4 4 0 0 1 0 8h-3m-16-14v-5m9 5v-5" stroke="#203e32" stroke-width="2" stroke-linecap="round"/>
      <path d="M195 136h37m-37 10h23m-66 35h45" stroke="#71936a" stroke-width="2" stroke-linecap="round"/>
      <path d="M246 133a15 15 0 0 1 0 22m6-28a23 23 0 0 1 0 34" stroke="#203e32" stroke-width="2" stroke-linecap="round"/>
    </g>
    <path d="M304 78a40 40 0 0 1 20 38m-15-50a54 54 0 0 1 28 51" stroke="#e2efae" stroke-width="2.5" stroke-linecap="round"/>
    <circle cx="105" cy="192" r="3" fill="#d9ebac"/><circle cx="329" cy="253" r="3" fill="#d9ebac"/>
  </svg>`;
}

const artTones = {
  water: 'sage', lemon: 'yellow', apple: 'sage', energy: 'gray', coffee: 'oat', cappuccino: 'oat',
  milk: 'oat', cola: 'sage', limo: 'sage', salami: 'oat', noodles: 'oat', pasta: 'oat', chips: 'sage',
  peanuts: 'oat', 'trail-mix': 'sage', cookie: 'oat', wafer: 'yellow', bar: 'oat', candy: 'sage',
  'mr-tom': 'oat', hanuta: 'sage', 'knoppers-bar': 'oat', 'chocolate-bar': 'oat', 'chocolate-tablet': 'sage',
  twix: 'oat', mentos: 'sage', maoam: 'oat', ballisto: 'oat', oreo: 'sage', 'double-biscuit': 'oat',
  snickers: 'oat', mars: 'oat',
};

export function productArt(key) {
  const name = Object.hasOwn(artTones, key) ? key : 'bar';
  return `<img class="product-art product-art--image" data-tone="${artTones[name]}"
    src="/static/products/${name}.webp" width="175" height="155" alt="" decoding="async" draggable="false">`;
}
