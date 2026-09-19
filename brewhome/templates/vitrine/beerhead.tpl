
  <div class="beer-head">
    ${photoSrc
      ? `<img class="bh-img" src="${_vEsc(photoSrc)}" alt="${_vEsc(beer.name)}" loading="lazy">`
      : `<div class="bh-img bh-img-ph">🍺</div>`}
    <div class="bh-body">
      <div class="bh-name">${_vEsc(beer.name)}</div>
      <div class="bh-meta">
        ${beer.type ? `<span class="bh-type">${_vEsc(beer.type)}</span>` : ''}
        ${abv ? `<span class="bh-abv">ABV <strong>${abv}</strong></span>` : ''}
      </div>
      ${(stock || keg) ? `<div class="bh-stock">${stock}${keg}</div>` : ''}
      ${beer.description ? `<p class="bh-desc">${_vEsc(beer.description)}</p>` : ''}
      ${dates ? `<div class="bh-dates">${dates}</div>` : ''}
      <a class="bh-link" href="../index.html#beer-${beer.id}">Voir dans la cave →</a>
    </div>
  </div>