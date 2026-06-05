/* ── Fuse.js instant search ─────────────────────────────────
   Loaded on /search page. INDEX_DATA is injected by the template.
   Falls back to /api/search for server-side rapidfuzz results.
─────────────────────────────────────────────────────────── */

let fuse = null;
let debounceTimer = null;
const DEBOUNCE_MS = 220;

function initFuse(indexData) {
  fuse = new Fuse(indexData, {
    keys: [
      { name: 'name_en', weight: 0.7 },
      { name: 'name_jp', weight: 0.2 },
      { name: 'set_name', weight: 0.1 },
    ],
    threshold: 0.4,       // 0=exact, 1=anything — 0.4 is good for typos
    distance: 200,
    includeScore: true,
    minMatchCharLength: 2,
  });
}

function renderResults(items) {
  const container = document.getElementById('search-results');
  if (!container) return;

  if (!items || items.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">◌</div>
        <div class="empty-text">No results found — try a different spelling</div>
      </div>`;
    return;
  }

  container.innerHTML = items.map(item => {
    const r = item.item || item;   // fuse wraps in .item, server returns flat
    const typeBadge = r.type === 'card'
      ? `<span class="badge badge-pack">Card</span>`
      : `<span class="badge badge-box">${(r.product_type || 'Product').replace('_', ' ')}</span>`;
    const langBadge = r.is_japanese !== false
      ? `<span class="badge badge-jp">JP</span>`
      : `<span class="badge badge-en">EN</span>`;
    const detailUrl = r.type === 'card'
      ? `/search?q=${encodeURIComponent(r.name_en)}`
      : `/sets/${r.set_id || ''}`;
    return `
    <a href="${detailUrl}" class="search-result-item fade-in" style="text-decoration:none">
      <div style="flex:1;min-width:0">
        <div class="result-name">${r.name_en}</div>
        ${r.name_jp ? `<div class="result-name-jp">${r.name_jp}</div>` : ''}
        <div class="result-set" style="margin-top:3px">${r.set_name || ''}</div>
      </div>
      <div style="display:flex;gap:5px;flex-shrink:0">
        ${typeBadge}
        ${langBadge}
      </div>
    </a>`;
  }).join('');
}

async function serverSearch(q) {
  try {
    const r = await fetch(`/api/search?q=${encodeURIComponent(q)}&limit=20`);
    const data = await r.json();
    return data;
  } catch {
    return [];
  }
}

async function handleInput(q) {
  if (!q || q.trim().length < 2) {
    const container = document.getElementById('search-results');
    if (container) container.innerHTML = '';
    return;
  }

  // Client-side Fuse first (instant)
  let results = [];
  if (fuse) {
    results = fuse.search(q, { limit: 20 }).map(r => r.item);
  }

  // If Fuse found fewer than 3 results, augment with server rapidfuzz
  if (results.length < 3) {
    const serverResults = await serverSearch(q);
    const existing = new Set(results.map(r => `${r.type}:${r.id}`));
    for (const sr of serverResults) {
      const key = `${sr.type}:${sr.id}`;
      if (!existing.has(key)) {
        results.push(sr);
        existing.add(key);
      }
    }
  }

  renderResults(results);
}

// ── Init ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const indexEl = document.getElementById('search-index-data');
  if (indexEl) {
    try {
      const data = JSON.parse(indexEl.textContent);
      initFuse(data);
    } catch (e) {
      console.warn('Failed to init Fuse.js:', e);
    }
  }

  const input = document.getElementById('search-input');
  if (!input) return;

  // Pre-fill from URL and run if non-empty
  const urlQ = new URLSearchParams(window.location.search).get('q') || '';
  if (urlQ) {
    input.value = urlQ;
    handleInput(urlQ);
  }

  input.addEventListener('input', e => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => handleInput(e.target.value.trim()), DEBOUNCE_MS);
  });

  input.focus();
});
