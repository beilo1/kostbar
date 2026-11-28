import {categoryIcons, icon, productArt} from './art.js';
import {esc, euro} from './shared.js';

export const terminalCategories = {drink: 'Getränke', snack: 'Snacks', sweet: 'Süßes', chocolate: 'Schokoladiges'};

export function terminalCategory(category) {
  return category === 'cold' || category === 'hot' ? 'drink' : category;
}

export function shopMarkup(hasLoyalty) {
  return `<div class="shop-layout"><section class="menu-area">
    <div class="shop-intro">
      <div class="shop-greeting"><p class="eyebrow">DEINE PAUSE</p><h1 id="greeting"></h1></div>
      <div class="account-tools">
        ${hasLoyalty ? `<button type="button" class="account-button loyalty-link" data-loyalty aria-haspopup="dialog">
          ${icon('cup', 21)}<span class="account-button-text">Sammelkarte<strong id="loyalty-status"></strong></span>
        </button>` : ''}
        <div class="account-finance" role="group" aria-label="Kasse">
          <button type="button" class="account-button payment-link" data-payment aria-haspopup="dialog" title="Saldo begleichen">
            ${icon('wallet', 21)}<span class="account-button-text">Bezahlen</span>
          </button>
          <button type="button" class="account-button balance-chip" data-history aria-haspopup="dialog" title="Persönliche Buchungen ansehen">
            ${icon('history', 21)}<span class="account-button-text">Dein Saldo<strong id="balance"></strong></span>
          </button>
        </div>
      </div>
    </div>
    <nav id="categories" class="category-tabs" aria-label="Produktkategorien"></nav>
    <div class="section-heading"><h2 id="category-title"></h2><span id="category-count"></span></div>
    <div id="products" class="products"></div>
  </section><aside id="basket" class="basket" aria-label="Warenkorb"></aside></div>`;
}

export function showCatalog(screen, catalog, category) {
  const tabs = screen.querySelector('#categories');
  if (!tabs) return;
  tabs.innerHTML = Object.entries(terminalCategories).map(([key, label]) =>
    `<button class="category-tab" data-category="${key}" aria-pressed="${key === category}">${icon(categoryIcons[key], 20)}<span>${esc(label)}</span></button>`
  ).join('');
  screen.querySelector('#category-title').textContent = terminalCategories[category] || 'Sortiment';
  const products = catalog.products.filter(p => terminalCategory(p.category) === category);
  screen.querySelector('#category-count').textContent = products.length === 1 ? '1 Produkt' : products.length + ' Produkte';
  screen.querySelector('#products').innerHTML = products.length ? products.map(p =>
    `<button class="product-card" data-add="${p.id}" aria-label="${esc(p.name)}, ${esc(euro(p.cents))}, hinzufügen">
       ${productArt(p.icon)}<span class="product-info"><strong>${esc(p.name)}</strong><span class="product-price">${euro(p.cents)}</span><span class="product-add">${icon('plus', 19)}</span></span>
     </button>`
  ).join('') : '<p class="empty-products">Hier sind aktuell keine Produkte verfügbar.</p>';
}

export function showBasket(screen, cart, {pending = false, uncertainBooking = false} = {}) {
  const basket = screen.querySelector('#basket');
  if (!basket) return;
  const lines = Array.from(cart.values());
  const total = lines.reduce((sum, p) => sum + p.cents * p.qty, 0);
  const count = lines.reduce((sum, p) => sum + p.qty, 0);
  basket.innerHTML = `<div class="basket-head"><div class="basket-icon">${icon('bag', 20)}</div><h2>Warenkorb</h2><span class="basket-count">${count}</span></div>
    <div class="basket-body">${lines.length ? '<ul class="basket-lines">' + lines.map(p =>
      `<li><div class="line-info"><strong>${esc(p.name)}</strong><span>${euro(p.cents * p.qty)}</span></div>
      <div class="quantity"><button type="button" data-qty="${p.id}" data-step="-1" aria-label="${esc(p.name)} entfernen">${icon('minus', 17)}</button>
      <span>${p.qty}</span><button type="button" data-qty="${p.id}" data-step="1" aria-label="${esc(p.name)} hinzufügen">${icon('plus', 17)}</button></div></li>`
    ).join('') + '</ul>' : '<div class="basket-empty"><span>' + icon('bag', 31) + '</span><p>Noch ist dein Warenkorb leer.</p><small>Tippe auf ein Produkt, um es hinzuzufügen.</small></div>'}</div>
    <div class="basket-bottom"><div class="total"><span>${lines.some(p => p.category === 'hot') ? 'Zwischensumme' : 'Gesamt'}</span><strong>${euro(total)}</strong></div>
    <button class="button primary checkout" data-checkout ${count && !pending && !uncertainBooking ? '' : 'disabled'}>${icon('cart', 21)} ${uncertainBooking ? 'Buchungsstatus wird geprüft …' : pending ? 'Wird gebucht …' : 'Kaufen'}</button>
    <p class="basket-note">Der Gesamtbetrag inklusive Sammelkartenbonus erscheint vor der Buchung.</p></div>`;
}

export function adjustCart(cart, catalog, id, step) {
  const product = cart.get(id) || catalog.products.find(p => p.id === id);
  if (!product) return;
  const qty = Math.max(0, Math.min(99, (product.qty || 0) + step));
  if (!qty) cart.delete(id);
  else cart.set(id, {...product, qty});
}
