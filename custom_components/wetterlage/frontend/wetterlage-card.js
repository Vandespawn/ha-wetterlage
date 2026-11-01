/*
 * Wetterlage-Karte für Home Assistant.
 * Wird mit der Integration ausgeliefert. Daten kommen per WebSocket („wetterlage/karte/abonnieren“).
 * Jede Kartenoption überschreibt die Einstellung der Integration (Bereich „karte“) nur für diese Karte.
 */
const WL_VERSION = "0.2.0";

const WL_SECTIONS = {
  kopf: "Kopf mit gefühlter Temperatur",
  warnungen: "Amtliche Warnungen",
  hinweise: "Eigene Hinweise",
  regen: "Regen nächste Stunde",
  bericht: "Tagesbericht",
  tage: "Tagesvorhersage",
  pollen: "Pollenflug",
};

const WL_ICON = {
  "sunny": "☀️", "clear-night": "🌙", "partlycloudy": "⛅", "cloudy": "☁️", "rainy": "🌧️", "pouring": "🌧️",
  "lightning-rainy": "⛈️", "snowy": "❄️", "snowy-rainy": "🌨️", "fog": "🌫️", "exceptional": "⚠️",
};
const WL_MDI = {
  "sunny": "mdi:weather-sunny", "clear-night": "mdi:weather-night", "partlycloudy": "mdi:weather-partly-cloudy",
  "cloudy": "mdi:weather-cloudy", "rainy": "mdi:weather-rainy", "pouring": "mdi:weather-pouring",
  "lightning-rainy": "mdi:weather-lightning-rainy", "snowy": "mdi:weather-snowy", "snowy-rainy": "mdi:weather-snowy-rainy",
  "fog": "mdi:weather-fog", "exceptional": "mdi:alert-circle-outline",
};

const wlEsc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

class WetterlageCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
    this._error = null;
    this._unsub = null;
    this._subscribing = false;
  }

  static getStubConfig() {
    return {};
  }

  static getConfigElement() {
    return document.createElement("wetterlage-card-editor");
  }

  setConfig(config) {
    if (!config || typeof config !== "object") throw new Error("Ungültige Konfiguration");
    const changedEntry = this._config && this._config.eintrag !== config.eintrag;
    this._config = { ...config };
    if (changedEntry) {
      this._unsubscribe();
      this._subscribe();
    }
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._unsub && !this._subscribing && this.isConnected) this._subscribe();
  }

  connectedCallback() {
    if (this._hass && !this._unsub) this._subscribe();
  }

  disconnectedCallback() {
    this._unsubscribe();
  }

  getCardSize() {
    return 9;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  async _subscribe() {
    if (!this._hass || this._subscribing || this._unsub) return;
    this._subscribing = true;
    try {
      const msg = { type: "wetterlage/karte/abonnieren" };
      if (this._config && this._config.eintrag) msg.eintrag = this._config.eintrag;
      this._unsub = await this._hass.connection.subscribeMessage((data) => {
        this._data = data;
        this._error = null;
        this._render();
      }, msg);
    } catch (err) {
      this._error = (err && (err.message || err.code)) || String(err);
      this._render();
    } finally {
      this._subscribing = false;
    }
  }

  _unsubscribe() {
    if (this._unsub) {
      try { this._unsub(); } catch (e) { /* Verbindung schon weg */ }
      this._unsub = null;
    }
  }

  // Einstellungen: Integration als Grundlage, Kartenoptionen gehen vor.
  _settings() {
    const k = (this._data && this._data.karte) || {};
    const c = this._config || {};
    let sections;
    if (Array.isArray(c.abschnitte)) sections = c.abschnitte.filter((id) => WL_SECTIONS[id]);
    else sections = (k.abschnitte || []).filter((a) => a.an).map((a) => a.id);
    const colors = {};
    for (let i = 0; i <= 4; i++) colors[i] = c[`farbe_stufe_${i}`] || k[`farbe_stufe_${i}`] || ["#2e9e5b", "#d6b400", "#f08a00", "#e0362c", "#8e24aa"][i];
    return {
      sections,
      tage: Number(c.tage ?? k.tage ?? 7),
      dez: Number(c.dezimalstellen ?? k.dezimalstellen ?? 1),
      design: c.design || k.design || "auto",
      symbole: c.symbole || k.symbole || "emoji",
      colors,
      regen: c.farbe_regen || k.farbe_regen || "#2f80ed",
      radius: c.eckenradius_px ?? k.eckenradius_px,
      titel: c.titel,
      hinweiseAlle: Boolean(c.hinweise_alle),
    };
  }

  _fmt(v, d) {
    if (v === null || v === undefined || Number.isNaN(v)) return "–";
    if (Math.abs(v) < 0.5 * 10 ** -d) v = 0;
    return Number(v).toLocaleString("de-DE", { minimumFractionDigits: d, maximumFractionDigits: d });
  }

  _time(iso) {
    if (!iso) return "–";
    const tz = (this._hass && this._hass.config && this._hass.config.time_zone) || undefined;
    return new Date(iso).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit", timeZone: tz });
  }

  _icon(cond, s, size) {
    if (s.symbole === "text") return "";
    if (s.symbole === "mdi") return `<ha-icon icon="${WL_MDI[cond] || WL_MDI.exceptional}" style="--mdc-icon-size:${size}px"></ha-icon>`;
    return `<span style="font-size:${size}px">${WL_ICON[cond] || ""}</span>`;
  }

  _section(id, d, s) {
    const f = (v, dd = s.dez) => this._fmt(v, dd);
    const signed = (v) => (v >= 0 ? "+" : "−") + f(Math.abs(v));
    switch (id) {
      case "kopf": {
        const j = d.jetzt, g = d.gefuehlt;
        const parts = g.anteile.map((p) => `${wlEsc(p.grund)} ${signed(p.delta)} °C`).join(" · ") || "keine Korrektur";
        return `<div class="top"><div><div class="place">${wlEsc(s.titel || d.titel)}</div>
          <div class="muted">${wlEsc(j.zustand)} · ${f(j.temperatur)} °C · ${f(j.feuchte, 0)} % · Wind ${f(j.wind, 0)} km/h</div></div>
          <div class="icon">${this._icon(j.zustand_ha, s, 42)}</div></div>
          <div><span class="big">${f(g.wert)} °C</span> <span class="muted">gefühlt, ${wlEsc(g.wort)}</span><br>
          <small class="muted">${parts}</small></div>`;
      }
      case "warnungen": {
        if (!d.warnungen_anzeigen) return "";
        if (!d.warnungen.length) {
          const ab = d.mindeststufe > 1 ? ` ab Stufe ${d.mindeststufe}` : "";
          return `<div class="warn" style="--c:var(--s0)"><b>Keine amtlichen Warnungen</b> für ${wlEsc(d.warngebiet || "deinen Ort")}${ab}</div>`;
        }
        return d.warnungen.map((w) => `<div class="warn" style="--c:var(--s${Math.min(4, w.stufe)})">
          <b>Amtliche Warnung des DWD</b> · ${wlEsc(w.ueberschrift)}<br>
          <small>${this._time(w.beginn)} bis ${w.ende ? this._time(w.ende) : "–"} Uhr${w.beschreibung ? ` · ${wlEsc(w.beschreibung)}` : ""}</small>
          ${w.verhaltenshinweise ? `<small class="instr">${wlEsc(w.verhaltenshinweise)}</small>` : ""}</div>`).join("");
      }
      case "hinweise": {
        const on = d.hinweise.filter((h) => h.an);
        if (!on.length) return "";
        // Ruhige Hinweise in einer Zeile, außer die Karte soll alle einzeln zeigen.
        const active = s.hinweiseAlle ? on : on.filter((h) => h.stufe > 0 || h.amtlich);
        const calm = s.hinweiseAlle ? [] : on.filter((h) => !(h.stufe > 0 || h.amtlich));
        const chips = active.length ? `<div class="chips">${active.map((h) => `<div class="chip" style="--c:var(--s${Math.min(4, h.stufe)})">
          <span class="dot"></span><div><b>${wlEsc(h.label)}</b><br><small>${wlEsc(h.text)}</small><br>
          <small class="src">${h.amtlich ? "amtlich (DWD)" : "eigener Hinweis, berechnet"}</small></div></div>`).join("")}</div>` : "";
        const calmLine = calm.length ? `<div class="calm" style="--c:var(--s0)"><span class="dot"></span>
          <span>Ruhig: ${calm.map((h) => wlEsc(h.label)).join(", ")}</span></div>` : "";
        return chips + calmLine;
      }
      case "regen": {
        const r = d.regen;
        if (r.aus) return "";
        const max = Math.max(1, ...r.schritte.map((x) => x.mmh || 0));
        const bars = r.schritte.map((x) => {
          const gap = x.mmh === null || x.mmh === undefined;
          const h = gap ? 100 : ((x.mmh || 0) / max) * 100;
          const title = `${this._time(x.t)} · ${gap ? "keine Daten" : f(x.mmh) + " mm/h"}`;
          return `<div class="${gap ? "gap" : ""}" title="${title}" style="height:${h}%"></div>`;
        }).join("");
        const first = r.schritte[0], last = r.schritte[r.schritte.length - 1];
        return `<div><b>Regen</b> <span class="muted">· ${wlEsc(r.text)}</span>
          <div class="rain">${bars}</div>
          <div class="rainx"><span>${first ? this._time(first.t) : ""}</span><span>${last ? this._time(last.t) : ""}</span></div></div>`;
      }
      case "bericht":
        return d.bericht ? `<div class="bericht"><b>Tagesbericht</b><br>${wlEsc(d.bericht)}</div>` : "";
      case "tage": {
        const ds = d.tage.slice(0, Math.max(1, s.tage));
        if (!ds.length) return "";
        return `<div class="days" style="grid-template-columns:repeat(${Math.min(ds.length, 7)},1fr)">${ds.map((x) => `<div>
          <div>${wlEsc(x.name)}</div>
          <div class="i">${s.symbole === "text" ? `<small>${wlEsc(x.zustand)}</small>` : this._icon(x.zustand_ha, s, 24)}</div>
          <div><b>${f(x.tx, 0)}°</b> <span class="muted">${f(x.tn, 0)}°</span></div>
          <div class="rr">${x.regen >= 0.1 ? f(x.regen) + " mm" : "&nbsp;"}</div></div>`).join("")}</div>`;
      }
      case "pollen": {
        const p = d.pollen;
        if (!p.arten.length) return "";
        return `<div><b>Pollenflug</b> <span class="muted">· ${wlEsc(p.region || "")}, ${wlEsc(p.tag)}</span>
          <div class="pollen">${p.arten.map((a) => `<div>${wlEsc(a.name)}<br><small class="muted">${wlEsc(a.label)}</small>
          <div class="bar"><span style="width:${(a.index / 3) * 100}%"></span></div></div>`).join("")}</div></div>`;
      }
      default:
        return "";
    }
  }

  _render() {
    if (!this.shadowRoot) return;
    const s = this._settings();
    let body;
    if (this._error) body = `<div class="msg">Wetterlage: ${wlEsc(this._error)}</div>`;
    else if (!this._data) body = `<div class="msg muted">Wetterlage lädt …</div>`;
    else if (!this._data.bereit) body = `<div class="msg muted">Noch keine Daten vom DWD.</div>`;
    else body = s.sections.map((id) => this._section(id, this._data, s)).join("");
    const vars = Object.entries(s.colors).map(([i, c]) => `--s${i}:${c};`).join("") + `--rain:${s.regen};`
      + (s.radius !== undefined && s.radius !== null ? `--ha-card-border-radius:${Number(s.radius)}px;` : "");
    const foot = `Datenbasis: Deutscher Wetterdienst (<a href="https://creativecommons.org/licenses/by/4.0/deed.de" target="_blank" rel="noopener">CC BY 4.0</a>), Werte teils von der Integration berechnet. Eigene Hinweise sind Schätzungen, keine amtlichen Warnungen.`;
    this.shadowRoot.innerHTML = `<style>${WL_CSS}</style>
      <ha-card class="design-${wlEsc(s.design)}" style="${vars}"><div class="wrap">${body}<div class="foot">${foot}</div></div></ha-card>`;
  }
}

const WL_CSS = `
:host{display:block}
ha-card{display:block;--c-bg:var(--ha-card-background,var(--card-background-color,#fff));--c-fg:var(--primary-text-color,#1f2328);
  --c-muted:var(--secondary-text-color,#5f6670);--c-line:var(--divider-color,#e3e5e8);--c-accent:var(--primary-color,#1e66d0);
  background:var(--c-bg);color:var(--c-fg);overflow:hidden}
ha-card.design-hell{--c-bg:#fff;--c-fg:#1f2328;--c-muted:#5f6670;--c-line:#e3e5e8;--c-accent:#1e66d0}
ha-card.design-dunkel{--c-bg:#1c1f24;--c-fg:#e8eaed;--c-muted:#9aa1a9;--c-line:#2c3036;--c-accent:#6aa5ff}
.wrap{padding:16px;display:grid;gap:14px}
.muted{color:var(--c-muted)}
.msg{padding:8px 0}
.top{display:flex;justify-content:space-between;gap:12px}.place{font-weight:600;font-size:1.05em}
.big{font-size:44px;font-weight:300;line-height:1}.icon{line-height:1}
.warn{border-left:5px solid var(--c);background:color-mix(in srgb,var(--c) 14%,transparent);padding:8px 12px;border-radius:8px}
.instr{display:block;margin-top:4px}
.chips{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}
.chip{display:flex;gap:8px;border:1px solid var(--c-line);border-radius:10px;padding:8px;font-size:13px}
.dot{width:10px;height:10px;border-radius:50%;background:var(--c);margin-top:5px;flex:none}
.src{color:var(--c-muted);font-size:11px}
.calm{display:flex;gap:8px;align-items:center;font-size:13px;color:var(--c-muted)}.calm .dot{margin-top:0}
.rain{display:flex;align-items:flex-end;gap:2px;height:56px;border-bottom:1px solid var(--c-line);margin-top:4px}
.rain div{flex:1;background:var(--rain);border-radius:3px 3px 0 0;min-height:2px;opacity:.85}
.rain div.gap{background:repeating-linear-gradient(45deg,var(--c-line) 0 3px,transparent 3px 6px);opacity:1}
.rainx{display:flex;justify-content:space-between;font-size:11px;color:var(--c-muted)}
.days{display:grid;text-align:center;font-size:13px;gap:4px}
.days .i{min-height:30px;display:flex;align-items:center;justify-content:center}.days .rr{color:var(--rain);font-size:11px}
.pollen{display:grid;grid-template-columns:repeat(auto-fill,minmax(105px,1fr));gap:6px;font-size:12px;margin-top:4px}
.pollen>div{border:1px solid var(--c-line);border-radius:8px;padding:4px 6px}
.bar{height:4px;border-radius:2px;background:var(--c-line);margin-top:3px}.bar span{display:block;height:100%;border-radius:2px;background:var(--s2)}
.bericht{background:color-mix(in srgb,var(--c-accent) 9%,transparent);border-radius:10px;padding:10px 12px}
.foot{font-size:11px;color:var(--c-muted);border-top:1px solid var(--c-line);padding-top:8px}
.foot a{color:inherit}
`;

// ---------- Editor ----------
const WL_LABELS = {
  eintrag: "Ort", titel: "Titel (leer = Name des Ortes)", abschnitte: "Abschnitte (Haken entfernen = ausblenden, ziehen = Reihenfolge)",
  tage: "Anzahl Tage", design: "Design", symbole: "Wettersymbole", dezimalstellen: "Nachkommastellen",
  hinweise_alle: "Ruhige Hinweise einzeln zeigen",
};

class WetterlageCardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._entries) {
      this._entries = [];
      hass.callWS({ type: "wetterlage/eintraege" }).then((e) => { this._entries = e; this._render(); }).catch(() => {});
    }
    this._render();
  }

  _schema() {
    const opt = (pairs) => pairs.map(([value, label]) => ({ value, label }));
    return [
      { name: "eintrag", selector: { select: { mode: "dropdown", options: opt([["", "erster eingerichteter Ort"], ...this._entries.map((e) => [e.entry_id, e.title])]) } } },
      { name: "titel", selector: { text: {} } },
      { name: "abschnitte", selector: { select: { multiple: true, reorder: true, mode: "list", options: opt(Object.entries(WL_SECTIONS)) } } },
      { name: "tage", selector: { number: { min: 1, max: 10, mode: "box" } } },
      { name: "design", selector: { select: { mode: "dropdown", options: opt([["", "wie in der Integration"], ["auto", "wie Home Assistant"], ["hell", "hell"], ["dunkel", "dunkel"]]) } } },
      { name: "symbole", selector: { select: { mode: "dropdown", options: opt([["", "wie in der Integration"], ["emoji", "Symbole"], ["mdi", "Home-Assistant-Icons"], ["text", "nur Text"]]) } } },
      { name: "dezimalstellen", selector: { number: { min: 0, max: 2, mode: "box" } } },
      { name: "hinweise_alle", selector: { boolean: {} } },
    ];
  }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) => WL_LABELS[s.name] || s.name;
      this._form.addEventListener("value-changed", (ev) => {
        const cfg = { ...ev.detail.value };
        for (const k of Object.keys(cfg)) {
          if (cfg[k] === "" || cfg[k] === undefined || cfg[k] === null || (Array.isArray(cfg[k]) && !cfg[k].length)) delete cfg[k];
        }
        this._config = cfg;
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: cfg }, bubbles: true, composed: true }));
      });
      const note = document.createElement("p");
      note.style.cssText = "font-size:12px;color:var(--secondary-text-color)";
      note.textContent = "Alle weiteren Einstellungen (Farben, Schwellen, Texte) stehen in der Integration. Hier gesetzte Werte gelten nur für diese Karte.";
      this.appendChild(this._form);
      this.appendChild(note);
    }
    this._form.hass = this._hass;
    // Ohne eigene Auswahl alle Abschnitte angehakt zeigen, damit man einzelne abwählen kann.
    this._form.data = { abschnitte: Object.keys(WL_SECTIONS), ...this._config };
    this._form.schema = this._schema();
  }
}

if (!customElements.get("wetterlage-card")) customElements.define("wetterlage-card", WetterlageCard);
if (!customElements.get("wetterlage-card-editor")) customElements.define("wetterlage-card-editor", WetterlageCardEditor);

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "wetterlage-card")) {
  window.customCards.push({
    type: "wetterlage-card",
    name: "Wetterlage",
    description: "DWD-Vorhersage, amtliche Warnungen, Hinweise, Regen der nächsten Stunde, Tagesbericht und Pollenflug.",
    preview: true,
    documentationURL: "https://github.com/Vandespawn/ha-wetterlage",
  });
}
console.info(`%c WETTERLAGE-KARTE %c ${WL_VERSION} `, "background:#b87333;color:#fff;font-weight:bold", "background:#222;color:#fff");
