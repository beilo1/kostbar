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
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 5v2"/>',
  plus: '<path d="M5 12h14m-7-7v14"/>',
  minus: '<path d="M5 12h14"/>',
  keyboard: '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M6 9h.1m4 0h.1m4 0h.1m4 0h.1M6 13h.1m12 0h.1M9 15h6"/>',
};
export const categoryIcons = { cold: 'glass', hot: 'cup', snack: 'snack', sweet: 'candy' };
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

const palettes = {
  water: ['#dfede8', '#77b7ab'], lemon: ['#eff0d6', '#cfcb62'], apple: ['#e4eed9', '#9bb767'],
  energy: ['#e1e7f0', '#8ca9cf'], coffee: ['#eee4d7', '#b17958'], cappuccino: ['#f1e4d2', '#ce9875'],
  milk: ['#e9e7df', '#b19880'], salami: ['#f0e3da', '#cf8975'], noodles: ['#f3e9d1', '#e3b858'],
  pasta: ['#f1e3d6', '#d5926c'], bar: ['#eee3de', '#b98374'], wafer: ['#efe8d4', '#cfa366'],
  candy: ['#e8e3ef', '#aa90ba'], cookie: ['#e0e9ee', '#8da9b9'],
};
const bottle = '<path d="M-9-32h18v12c0 5 12 8 12 17v32c0 5-3 7-7 7h-28c-4 0-7-2-7-7V-3c0-9 12-12 12-17Z" fill="white"/><path d="M-20-2h40v23h-40Z" fill="ACC"/><rect x="-10" y="-38" width="20" height="9" rx="3" fill="ACC"/>';
const mug = '<path d="M19-10h9a10 10 0 0 1 0 20H18" fill="none"/><path d="M-25-14h48v17c0 15-11 23-24 23S-25 18-25 3Z" fill="ACC"/><ellipse cx="-1" cy="-14" rx="24" ry="7" fill="#fff8eb"/><path d="M-11-28c-5-5 4-7 0-12m12 12c-5-5 4-7 0-12m12 12c-5-5 4-7 0-12M-27 30h52" fill="none"/>';
const shapes = {
  water: bottle + '<path d="M-7 11q3-7 7-3t7-3" fill="none"/>',
  lemon: bottle + '<circle r="7" cy="9" fill="#fffae1"/><path d="M0 2v14m-7-7H7" fill="none"/>',
  apple: bottle + '<path d="M0 6c-10-6-11 9-4 11l4-1 4 1c7-2 6-17-4-11Zm0 0q0-6 5-7" fill="#fcfae4"/>',
  energy: '<rect x="-18" y="-34" width="36" height="68" rx="6" fill="ACC"/><path d="M-18-25h36m-36 50h36" fill="none"/><path d="m4-19-14 24H1l-5 14L12-6H1Z" fill="#fff2c7"/>',
  coffee: mug, cappuccino: mug + '<path d="M-12 7h22" fill="none"/>',
  milk: '<path d="M-17-26h34l-5 60h-24Z" fill="#fff8eb"/><path d="M-15-8h30l-2 22h-26Z" fill="ACC"/><path d="M-21-27h42M-14-33h28" fill="none"/>',
  salami: '<path d="M-31-9h61l5-5v28l-5-5h-61l-5 5v-28Z" fill="ACC"/><path d="M-21-9v18m42-18v18m-13-9H-8" fill="none"/>',
  noodles: '<path d="M-27 0h54c-2 15-11 25-27 25S-25 15-27 0Z" fill="ACC"/><path d="M-30 0h60M-17 0c2-12 12-13 14-22m-3 22c2-9 9-11 11-20m0 20c2-8 8-11 10-16m-35-1 42-17m-44 11 44-7" fill="none"/>',
  pasta: '<path d="M-22-16h44l-7 45h-30Z" fill="ACC"/><rect x="-25" y="-22" width="50" height="7" rx="3" fill="#fff8eb"/><path d="M-14 4h28m-23 8h18" fill="none"/>',
  bar: '<path d="m-33-16 8 3h50l8-3v32l-8-3h-50l-8 3Z" fill="ACC"/><path d="M-23-13v26m46-26v26M-11-3h22m-18 7h14" fill="none"/>',
  wafer: '<rect x="-27" y="-17" width="54" height="35" rx="5" fill="ACC"/><path d="M-27-8h54m-54 9h54m-54 9h54m-38-27v35m12-35v35m12-35v35" fill="none"/>',
  candy: '<path d="m-13-6-20-12 4 15-4 19 20-10m26-12 20-12-4 15 4 19-20-10" fill="ACC"/><ellipse rx="17" ry="15" fill="#fcf4ff"/><path d="M-7 4c2-9 10-9 13-4s-2 8-5 6" fill="none"/>',
  cookie: '<circle r="28" fill="ACC"/><circle r="20" fill="none"/><path d="M0-9v18m-9-9H9m-15-6L6 6m0-12L-6 6" fill="none"/>',
};
export function productArt(key) {
  const [paper, accent] = palettes[key] || palettes.bar;
  const shape = (shapes[key] || shapes.bar).replaceAll('ACC', accent);
  return `<svg class="product-art" viewBox="0 0 132 82" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
    <rect width="132" height="82" fill="${paper}"/><circle cx="66" cy="43" r="33" fill="white" opacity=".35"/>
    <path d="M23 23h8m-4-4v8m76 29h8m-4-4v8M30 64h3m67-49h3" stroke="#203e32" stroke-opacity=".33" stroke-linecap="round"/>
    <ellipse cx="66" cy="73" rx="25" ry="3" fill="#26382f" opacity=".12"/>
    <g transform="translate(66 41) scale(.79) rotate(-11)" stroke="#243b31" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round">${shape}</g>
  </svg>`;
}
