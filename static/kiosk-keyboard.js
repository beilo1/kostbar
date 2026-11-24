const rows = ['1234567890', 'qwertzuiopü', 'asdfghjklöä', 'yxcvbnmß-.'];

const pinRows = ['123', '456', '789', '0'];

export function pinField(name, label) {
  return `<label class="kiosk-entry-label">${label}<input type="password" name="${name}" inputmode="none" pattern="[0-9]{4}"
    minlength="4" maxlength="4" autocomplete="off" required></label>`;
}

/** @param {boolean} upper @param {boolean} numeric */
export function keyboardMarkup(upper, numeric = false) {
  const keys = (numeric ? pinRows : rows).map(row => '<div>' + Array.from(row, char => {
    const key = upper ? char.replace('ß', 'ẞ').toUpperCase() : char;
    return '<button type="button" data-key="' + key + '">' + key + '</button>';
  }).join('') + '</div>').join('');
  const letters = '<button type="button" class="key-wide" data-key="shift" aria-label="Großschreibung">⇧</button>' +
    '<button type="button" class="key-wide" data-key="space">Leerzeichen</button>';
  return keys + '<div>' + (numeric ? '' : letters) +
    '<button type="button" class="key-wide" data-key="delete" aria-label="Zeichen löschen">⌫</button>' +
    '<button type="button" class="key-wide" data-key="next">Weiter</button></div>';
}
