/** @typedef {'idle'|'manual'|'register'|'consent'|'card-setup'|'pin-setup'|'shop'|'receipt'} Stage */
/**
 * @typedef {object} KioskSession
 * @property {Stage} stage
 * @property {string|null} visit
 * @property {number} remaining
 * @property {string} terminal
 * @property {boolean} reader
 * @property {string} [version]
 * @property {string} [privacy_version]
 * @property {string|null} [notice]
 * @property {{request: string}} [booking]
 */

/** @type {ReadonlySet<Stage>} */
const interactive = new Set(['manual', 'register', 'consent', 'card-setup', 'pin-setup', 'shop']);

/** @param {KioskSession|null} state @param {string|null|undefined} visit */
export function canExtendVisit(state, visit = state?.visit) {
  return Boolean(state && visit && state.visit === visit && interactive.has(state.stage));
}

/** @param {KioskSession|null} before @param {KioskSession} after */
export function sessionViewChanged(before, after) {
  return !before || before.stage !== after.stage || before.visit !== after.visit ||
    before.version !== after.version || before.privacy_version !== after.privacy_version ||
    before.booking?.request !== after.booking?.request;
}

/** @param {KioskSession} next @param {string|undefined} expiredVisit */
export function acceptsState(next, expiredVisit) {
  return !next.visit || next.visit !== expiredVisit;
}
