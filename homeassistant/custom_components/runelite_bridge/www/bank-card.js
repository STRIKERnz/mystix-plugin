class RuneLiteBankCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.data = null;
    this.source = "bank";
    this.search = "";
    this.page = 0;
    this.pageSize = 100;
  }

  set hass(hass) {
    this._hass = hass;
    const entity = hass.states["sensor.runelite_bridge_bank"];
    const signature = entity ? `${entity.state}:${entity.last_updated}` : "none";
    if (signature !== this.signature) {
      this.signature = signature;
      this.load();
    }
  }

  setConfig(config) {
    this.config = config;
    if (config.page_size) this.pageSize = Number(config.page_size);
  }

  getCardSize() { return 8; }

  async load() {
    if (!this._hass) return;
    try {
      this.data = await this._hass.callApi("GET", "runelite_bridge/dashboard/bank");
      if (!this.data.sources[this.source]) {
        this.source = Object.keys(this.data.sources)[0] || "bank";
      }
      this.page = 0;
      this.render();
    } catch (error) {
      this.error = String(error);
      this.render();
    }
  }

  render() {
    if (!this.shadowRoot) return;
    if (!this.data) {
      this.shadowRoot.innerHTML = `<ha-card><div class="loading">${this.error || "Loading bank…"}</div></ha-card>`;
      return;
    }
    const all = this.data.sources[this.source] || [];
    const needle = this.search.toLowerCase();
    const filtered = all.filter(item => !needle || String(item.item_id).includes(needle) || item.name.toLowerCase().includes(needle));
    const pages = Math.max(1, Math.ceil(filtered.length / this.pageSize));
    this.page = Math.min(this.page, pages - 1);
    const items = filtered.slice(this.page * this.pageSize, (this.page + 1) * this.pageSize);
    const tabs = Object.entries(this.data.sources).map(([source, values]) =>
      `<button class="tab ${source === this.source ? "active" : ""}" data-source="${source}">${source.replaceAll("_", " ")} (${values.length})</button>`
    ).join("");
    const cells = items.map(item => `
      <div class="item" title="${escapeHtml(item.name)} · Item ID ${item.item_id}">
        <img src="${item.icon}" loading="lazy">
        <span class="quantity">${Number(item.quantity).toLocaleString()}</span>
        <span class="name">${escapeHtml(item.name)}</span>
        <span class="id">#${item.item_id}</span>
      </div>`).join("");
    this.shadowRoot.innerHTML = `
      <style>
        ha-card { padding: 16px; }
        h2 { margin: 0 0 12px; font-size: 20px; }
        .toolbar, .tabs, .pager { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:12px; }
        button, input { border:1px solid var(--divider-color); border-radius:8px; padding:8px 10px; background:var(--card-background-color); color:var(--primary-text-color); }
        button { cursor:pointer; text-transform:capitalize; }
        button.active { background:var(--primary-color); color:var(--text-primary-color); }
        input { flex:1; min-width:160px; }
        .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(72px,1fr)); gap:8px; }
        .item { position:relative; min-height:92px; padding:6px; border-radius:8px; background:var(--secondary-background-color); text-align:center; }
        .item img { width:40px; height:40px; object-fit:contain; image-rendering:auto; }
        .quantity { position:absolute; right:4px; top:3px; color:#fff; font-size:11px; font-weight:700; text-shadow:1px 1px 2px #000,-1px -1px 2px #000; }
        .name { display:block; overflow:hidden; white-space:nowrap; text-overflow:ellipsis; font-size:11px; }
        .id { display:block; color:var(--secondary-text-color); font-size:9px; }
        .pager { justify-content:space-between; margin:14px 0 0; }
        .loading { padding:20px; }
      </style>
      <ha-card>
        <h2>${this.config?.title || "RuneLite Bank"}${this.data.player ? ` — ${this.data.player}` : ""}</h2>
        <div class="tabs">${tabs}</div>
        <div class="toolbar"><input type="search" placeholder="Search item name or ID" value="${escapeHtml(this.search)}"></div>
        <div class="grid">${cells || "No matching items"}</div>
        <div class="pager"><button data-page="prev">Previous</button><span>Page ${this.page + 1} of ${pages} · ${filtered.length} items</span><button data-page="next">Next</button></div>
      </ha-card>`;
    this.shadowRoot.querySelectorAll("[data-source]").forEach(button => button.onclick = () => {
      this.source = button.dataset.source; this.page = 0; this.render();
    });
    this.shadowRoot.querySelector("input").oninput = event => {
      this.search = event.target.value.trim(); this.page = 0; this.render();
      requestAnimationFrame(() => { const input=this.shadowRoot.querySelector("input"); input.focus(); input.setSelectionRange(input.value.length,input.value.length); });
    };
    this.shadowRoot.querySelector('[data-page="prev"]').onclick = () => { if (this.page > 0) { this.page--; this.render(); } };
    this.shadowRoot.querySelector('[data-page="next"]').onclick = () => { if (this.page + 1 < pages) { this.page++; this.render(); } };
  }
}

function escapeHtml(value) {
  return String(value).replace(/[&<>'"]/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[character]);
}

if (!customElements.get("runelite-bank-card")) {
  customElements.define("runelite-bank-card", RuneLiteBankCard);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "runelite-bank-card",
  name: "RuneLite Bank",
  description: "Searchable RuneLite bank and inventory browser",
});
