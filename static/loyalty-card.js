import {icon} from './art.js';

const FIRST_STAMP_MS = 320;
const STAMP_INTERVAL_MS = 110;
const STAMP_DURATION_MS = 440;
const REDEEM_DURATION_MS = 650;
const TURN_DURATION_MS = 340;

function cardFace(stamps, target, {newStamps, startAt, dialog = false, spent = false}) {
  const firstNewStamp = Math.max(0, stamps - newStamps);
  const slots = Array.from({length: target}, (_, index) => {
    const filled = index < stamps;
    const fresh = filled && index >= firstNewStamp;
    const highlight = index === stamps - 1 && (fresh || stamps === target);
    const cup = filled ? icon('cup', 23) : '';
    const delay = startAt + (index - firstNewStamp) * STAMP_INTERVAL_MS;
    return `<span class="loyalty-stamp${filled ? ' filled' : ''}${highlight ? ' final-stamp' : ''}${fresh ? ' new-stamp' : ''}"${fresh ? ` data-stamp-delay="${delay}"` : ''}>
      ${fresh ? `<span class="loyalty-stamp-number">${index + 1}</span><span class="loyalty-stamp-seal">${cup}</span>` : cup || index + 1}</span>`;
  }).join('');

  return `<div class="loyalty-face${spent ? ' loyalty-face-spent' : ' loyalty-face-current'}"${spent ? ' aria-hidden="true"' : ''}>
    <div class="loyalty-card-head"><h2${dialog ? ' id="kiosk-dialog-title"' : ''}>Deine Sammelkarte</h2>
      <strong aria-label="${stamps} von ${target} Stempeln">${stamps} / ${target}</strong></div>
    <div class="loyalty-stamp-grid" aria-hidden="true">${slots}</div>
  </div>`;
}

export function loyaltyCardMarkup({stamps, target, ready, remaining}, {newStamps = 0, redeemed = 0, dialog = false} = {}) {
  const animate = redeemed > 0 || newStamps > 0;
  const unlocked = redeemed === 0 && ready > 0 && newStamps > 0;
  const stampsOnCurrentCard = Math.min(stamps, newStamps);
  const stampsOnSpentCard = Math.min(target, newStamps - stampsOnCurrentCard);
  const rewardStamps = redeemed ? stampsOnSpentCard : stampsOnCurrentCard;
  const rewardAt = rewardStamps > 0
    ? FIRST_STAMP_MS + (rewardStamps - 1) * STAMP_INTERVAL_MS + STAMP_DURATION_MS
    : 520;
  const turnAt = rewardAt + REDEEM_DURATION_MS;
  const currentFace = cardFace(stamps, target, {newStamps: stampsOnCurrentCard,
    startAt: redeemed ? turnAt + TURN_DURATION_MS : FIRST_STAMP_MS, dialog});
  const spentFace = redeemed ? cardFace(target, target, {newStamps: stampsOnSpentCard,
    startAt: FIRST_STAMP_MS, spent: true}) : '';

  const readyText = ready === 1 ? '1 Gratisgetränk verfügbar' : `${ready} Gratisgetränke verfügbar`;
  const earnedText = newStamps === 1 ? '1 neuer Stempel gesammelt' : `${newStamps} neue Stempel gesammelt`;
  let message;
  if (redeemed) message = redeemed === 1 ? '1 Gratisgetränk eingelöst' : `${redeemed} Gratisgetränke eingelöst`;
  else if (ready) message = unlocked ? 'Gratisgetränk freigeschaltet' : readyText;
  else message = remaining === 1 ? 'Noch ein Heißgetränk bis zum Gratisgetränk' : `Noch ${remaining} Heißgetränke bis zum Gratisgetränk`;

  const notes = [
    redeemed > 0 && ready > 0 && readyText,
    newStamps > 0 && earnedText,
    remaining > target && 'Ein früherer Storno wird mit neuen Stempeln verrechnet.',
  ].filter(Boolean);

  const timing = animate ? ` data-reward-delay="${rewardAt}" data-turn-delay="${turnAt}"` : '';
  return `<section class="loyalty-card${unlocked ? ' loyalty-unlocked' : ''}${redeemed ? ' loyalty-redeemed' : ''}"${timing}>
    <div class="loyalty-faces">${currentFace}${spentFace}</div>
    <p class="loyalty-card-message">${icon(redeemed || ready ? 'check' : 'cup', 18)} ${message}</p>
    ${notes.length ? `<p class="loyalty-card-note">${notes.join(' · ')}</p>` : ''}
  </section>`;
}

export function animateReceiptCard(screen) {
  const card = screen.querySelector('.loyalty-card[data-reward-delay]');
  if (!card) return;

  card.style.setProperty('--stamp-duration', STAMP_DURATION_MS + 'ms');
  card.style.setProperty('--turn-duration', TURN_DURATION_MS + 'ms');
  card.style.setProperty('--reward-delay', card.dataset.rewardDelay + 'ms');
  card.style.setProperty('--turn-delay', card.dataset.turnDelay + 'ms');
  for (const stamp of card.querySelectorAll('[data-stamp-delay]')) {
    stamp.style.setProperty('--stamp-delay', stamp.dataset.stampDelay + 'ms');
  }
  card.classList.add('loyalty-card-motion');
}
