(function () {
  'use strict';

  // -------- STATE --------
  let data = { categories: [], subcategories: {}, models: [] };
  let filterState = {
    category: null,
    subcategory: null,
    search: '',
    sort: 'default'
  };

  // -------- DOM --------
  const els = {
    categoryChips: document.getElementById('categoryChips'),
    subcategoryGroup: document.getElementById('subcategoryGroup'),
    subcategoryChips: document.getElementById('subcategoryChips'),
    searchInput: document.getElementById('searchInput'),
    searchClear: document.getElementById('searchClear'),
    sortSelect: document.getElementById('sortSelect'),
    resultsCount: document.getElementById('resultsCount'),
    catalogGrid: document.getElementById('catalogGrid'),
    catalogEmpty: document.getElementById('catalogEmpty'),
    resetFilters: document.getElementById('resetFilters'),
    featuredGrid: document.getElementById('featuredGrid')
  };

  // -------- HELPERS --------
  function getCategoryName(id) {
    const cat = data.categories.find(c => c.id === id);
    return cat ? cat.name : id;
  }

  function getSubcategoryName(catId, subId) {
    const subs = data.subcategories[catId] || [];
    const sub = subs.find(s => s.id === subId);
    return sub ? sub.name : subId;
  }

  function getMaterialPrices() {
    const prices = {};
    document.querySelectorAll('#materials-grid .material').forEach(el => {
      const mat = el.dataset.material;
      const price = parseFloat(el.dataset.price);
      if (mat && !isNaN(price)) prices[mat] = price;
    });
    return prices;
  }

  function estimateCost(model) {
    const prices = getMaterialPrices();
    const mat = model.material || 'PLA';
    const price = prices[mat] || 5;
    if (model.weight == null) return null;
    return Math.round(model.weight * price);
  }

  function formatSpec(model) {
    const parts = [];
    if (model.weight != null) parts.push(`${model.weight} г`);
    if (model.printTime != null) {
      if (model.printTime > 60) {
        parts.push(`${(model.printTime / 60).toFixed(1)} ч`);
      } else {
        parts.push(`${model.printTime} мин`);
      }
    }
    const cost = estimateCost(model);
    if (cost != null) parts.push(`~${cost} ₽`);
    if (!parts.length) return null;
    return parts.join(' · ');
  }

  function highlightText(text, query) {
    if (!query) return text;
    const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    return text.replace(new RegExp(`(${escaped})`, 'gi'), '<mark>$1</mark>');
  }

  // -------- RENDER --------
  function cardHTML(model, opts) {
    opts = opts || {};
    const showSource = opts.showSource !== false;
    const sourceURL = model.url || '#';
    const spec = formatSpec(model);
    const searchLower = filterState.search.toLowerCase();
    const nameMatchesSearch = searchLower && model.name.toLowerCase().includes(searchLower);
    const nameHTML = nameMatchesSearch ? highlightText(model.name, filterState.search) : model.name;

    const tagsHTML = [
      `<span class="chip">${getCategoryName(model.category)}</span>`,
      `<span class="chip chip-material">${model.material}</span>`
    ].join('');

    let subTag = '';
    if (model.subcategory) {
      subTag = `<span class="chip chip-sub">${getSubcategoryName(model.category, model.subcategory)}</span>`;
    }

    let specHTML = '';
    if (spec) {
      specHTML = `<div class="work-spec">${spec}</div>`;
    }

    let linkAttrs = `class="work-card" target="_blank" rel="noopener"`;
    if (!model.url) {
      linkAttrs = `class="work-card work-card-no-link"`;
    }

    return `
      <a ${linkAttrs} href="${sourceURL}">
        <div class="work-img">
          <img src="${model.image}" alt="${model.name}" loading="lazy" onerror="this.classList.add('img-error')">
        </div>
        <div class="work-info">
          <div class="work-tags">${tagsHTML}${subTag}</div>
          <h3>${nameHTML}</h3>
          ${specHTML}
        </div>
      </a>
    `;
  }

  function renderCategoryChips() {
    const allChip = `<button class="chip-btn ${filterState.category === null ? 'active' : ''}" data-cat="">Все</button>`;
    const catChips = data.categories.map(c => `
      <button class="chip-btn ${filterState.category === c.id ? 'active' : ''}" data-cat="${c.id}">${c.name}</button>
    `).join('');
    els.categoryChips.innerHTML = allChip + catChips;

    Array.from(els.categoryChips.querySelectorAll('.chip-btn')).forEach(btn => {
      btn.addEventListener('click', () => {
        const newCat = btn.dataset.cat || null;
        if (newCat === filterState.category) return;
        filterState.category = newCat;
        // reset subcategory when category changes
        filterState.subcategory = null;
        updateURL();
        renderAll();
      });
    });
  }

  function renderSubcategoryChips() {
    const subs = (filterState.category && data.subcategories[filterState.category]) || [];
    if (!subs.length) {
      els.subcategoryGroup.hidden = true;
      els.subcategoryChips.innerHTML = '';
      return;
    }
    els.subcategoryGroup.hidden = false;
    const allChip = `<button class="chip-btn chip-btn-sub ${filterState.subcategory === null ? 'active' : ''}" data-sub="">Все</button>`;
    const subChips = subs.map(s => `
      <button class="chip-btn chip-btn-sub ${filterState.subcategory === s.id ? 'active' : ''}" data-sub="${s.id}">${s.name}</button>
    `).join('');
    els.subcategoryChips.innerHTML = allChip + subChips;

    Array.from(els.subcategoryChips.querySelectorAll('.chip-btn')).forEach(btn => {
      btn.addEventListener('click', () => {
        filterState.subcategory = btn.dataset.sub || null;
        updateURL();
        renderAll();
      });
    });
  }

  function getFilteredModels() {
    const q = filterState.search.toLowerCase();
    return data.models.filter(m => {
      if (filterState.category && m.category !== filterState.category) return false;
      if (filterState.subcategory && m.subcategory !== filterState.subcategory) return false;
      if (q) {
        const haystack = [
          m.name,
          getCategoryName(m.category),
          m.material,
          ...(m.tags || [])
        ].join(' ').toLowerCase();
        if (m.subcategory) haystack += ' ' + getSubcategoryName(m.category, m.subcategory).toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });
  }

  function sortModels(list) {
    const sorted = list.slice();
    switch (filterState.sort) {
      case 'name':
        sorted.sort((a, b) => a.name.localeCompare(b.name, 'ru'));
        break;
      case 'weight-asc':
        sorted.sort((a, b) => (a.weight ?? Infinity) - (b.weight ?? Infinity));
        break;
      case 'weight-desc':
        sorted.sort((a, b) => (b.weight ?? -1) - (a.weight ?? -1));
        break;
    }
    return sorted;
  }

  function renderResults() {
    const filtered = sortModels(getFilteredModels());
    els.resultsCount.textContent = filtered.length === 1
      ? 'Найдена 1 модель'
      : `Найдено ${filtered.length} ${pluralModels(filtered.length)}`;

    if (!filtered.length) {
      els.catalogGrid.innerHTML = '';
      els.catalogEmpty.hidden = false;
      return;
    }
    els.catalogEmpty.hidden = true;
    els.catalogGrid.innerHTML = filtered.map(m => cardHTML(m)).join('');
  }

  function pluralModels(n) {
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return 'модель';
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'модели';
    return 'моделей';
  }

  function renderFeatured() {
    if (!els.featuredGrid) return;
    const featured = data.models.filter(m => m.featured);
    if (!featured.length) {
      els.featuredGrid.innerHTML = '<div class="catalog-loading">Пока нет featured моделей</div>';
      return;
    }
    els.featuredGrid.innerHTML = featured.map(m => cardHTML(m)).join('');
  }

  function renderAll() {
    renderCategoryChips();
    renderSubcategoryChips();
    renderResults();
  }

  // -------- URL PARAMS --------
  function readURL() {
    const params = new URLSearchParams(location.search);
    const cat = params.get('cat');
    if (cat && data.categories.some(c => c.id === cat)) {
      filterState.category = cat;
      const sub = params.get('sub');
      const validSubs = data.subcategories[cat] || [];
      if (sub && validSubs.some(s => s.id === sub)) {
        filterState.subcategory = sub;
      }
    }
    const q = params.get('q');
    if (q) {
      filterState.search = q;
      els.searchInput.value = q;
      els.searchClear.hidden = !q;
    }
    const sort = params.get('sort');
    if (sort && ['default', 'name', 'weight-asc', 'weight-desc'].includes(sort)) {
      filterState.sort = sort;
      els.sortSelect.value = sort;
    }
  }

  function updateURL() {
    const params = new URLSearchParams();
    if (filterState.category) params.set('cat', filterState.category);
    if (filterState.subcategory) params.set('sub', filterState.subcategory);
    if (filterState.search) params.set('q', filterState.search);
    if (filterState.sort !== 'default') params.set('sort', filterState.sort);
    const qs = params.toString();
    const url = location.pathname + (qs ? '?' + qs : '');
    history.replaceState(null, '', url);
  }

  // -------- EVENTS --------
  function bindEvents() {
    if (els.searchInput) {
      let t = null;
      els.searchInput.addEventListener('input', e => {
        const v = e.target.value;
        clearTimeout(t);
        t = setTimeout(() => {
          filterState.search = v.trim();
          els.searchClear.hidden = !filterState.search;
          updateURL();
          renderResults();
        }, 200);
      });
    }

    if (els.searchClear) {
      els.searchClear.addEventListener('click', () => {
        els.searchInput.value = '';
        filterState.search = '';
        els.searchClear.hidden = true;
        els.searchInput.focus();
        updateURL();
        renderResults();
      });
    }

    if (els.sortSelect) {
      els.sortSelect.addEventListener('change', e => {
        filterState.sort = e.target.value;
        updateURL();
        renderResults();
      });
    }

    if (els.resetFilters) {
      els.resetFilters.addEventListener('click', () => {
        filterState.category = null;
        filterState.subcategory = null;
        filterState.search = '';
        filterState.sort = 'default';
        els.searchInput.value = '';
        els.searchClear.hidden = true;
        els.sortSelect.value = 'default';
        updateURL();
        renderAll();
      });
    }
  }

  // -------- INIT --------
  async function init() {
    try {
      const res = await fetch('data/models.json', { cache: 'no-store' });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      // Защита от UTF-8 BOM: некоторые серверы присылают application/json
      // без charset, и BOM ломает парсинг. Читаем как текст и срезаем.
      const text = await res.text();
      const clean = text.charCodeAt(0) === 0xFEFF ? text.slice(1) : text;
      data = JSON.parse(clean);
    } catch (err) {
      console.error('Failed to load models.json', err);
      els.catalogGrid.innerHTML = `
        <div class="catalog-error">
          <h3>Ошибка загрузки</h3>
          <p>Не удалось загрузить каталог. Откройте страницу через локальный сервер, не file://</p>
        </div>
      `;
      return;
    }

    // mark featured for the home page only if it has a featured grid
    if (els.featuredGrid) {
      renderFeatured();
      return;
    }

    // catalog page
    readURL();
    bindEvents();
    renderAll();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
