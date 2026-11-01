/*
 * Wetterlage-Karte für Home Assistant.
 * Wird mit der Integration ausgeliefert. Daten kommen per WebSocket („wetterlage/karte/abonnieren“).
 * Jede Kartenoption überschreibt die Einstellung der Integration (Bereich „karte“) nur für diese Karte.
 * Im Kartenkonfig steht nur, was vom Standard abweicht.
 */
const WL_VERSION = "0.2.3";

const WL_SECTIONS = {
  kopf: "Kopf mit gefühlter Temperatur",
  warnungen: "Amtliche Warnungen",
  hinweise: "Eigene Hinweise",
  regen: "Regen nächste Stunde",
  bericht: "Tagesbericht",
  tage: "Tagesvorhersage",
  pollen: "Pollenflug",
};
const WL_HINTS = { frost: "Frost", gewitter: "Gewitter", hitze: "Hitze", sturm: "Sturm", starkregen: "Starkregen" };
const WL_POLLEN = ["Hasel", "Erle", "Esche", "Birke", "Gräser", "Roggen", "Beifuß", "Ambrosia"];

// Standardwerte der feinen Optionen. Nur Abweichungen landen in der Kartenkonfiguration.
const WL_DEFAULTS = {
  kopf_ort: true, kopf_zustand: true, kopf_messwerte: true, kopf_symbol: true, kopf_gross: "gefuehlt", kopf_wort: true,
  kopf_begruendung: true,
  warnungen_keine: true, warnungen_zeitraum: true, warnungen_beschreibung: true, warnungen_verhalten: true,
  hinweise_auswahl: Object.keys(WL_HINTS), hinweise_alle: false, hinweise_ruhig: true, hinweise_quelle: true,
  regen_balken: true, regen_text: true, regen_zeiten: true, regen_nur_bei_regen: false,
  bericht_ueberschrift: true,
  tage_symbol: true, tage_tiefstwert: true, tage_regen: true, tage_sonne: false,
  pollen_auswahl: [...WL_POLLEN], pollen_nur_belastet: false, pollen_ausblenden_wenn_keine: false, pollen_balken: true,
  fuss: "lang",
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
const wlSame = (a, b) => JSON.stringify(a) === JSON.stringify(b);

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
    clearTimeout(this._retry);
    clearInterval(this._watchdog);
    this._watchdog = null;
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
        if (data && data.neu_verbinden) {
          // Die Integration lädt neu (z. B. nach geänderten Einstellungen): neu verbinden.
          this._resubscribe(3000);
          return;
        }
        this._data = data;
        this._lastData = Date.now();
        this._error = null;
        this._starting = false;
        this._render();
      }, msg);
      this._startWatchdog();
    } catch (err) {
      const code = err && err.code;
      if (code === "not_found") {
        // Home Assistant startet noch oder die Integration lädt gerade.
        this._starting = true;
        this._error = null;
      } else {
        this._error = (err && (err.message || err.code)) || String(err);
      }
      this._render();
      this._resubscribe(10000);
    } finally {
      this._subscribing = false;
    }
  }

  _resubscribe(delay) {
    this._unsubscribe();
    clearTimeout(this._retry);
    this._retry = setTimeout(() => {
      this._retry = null;
      if (this.isConnected) this._subscribe();
    }, delay);
  }

  // Kommen 12 Minuten lang keine Daten, neu verbinden (z. B. nach einem Neustart von Home Assistant).
  _startWatchdog() {
    if (this._watchdog) return;
    this._lastData = this._lastData || Date.now();
    this._watchdog = setInterval(() => {
      if (this._unsub && Date.now() - this._lastData > 12 * 60 * 1000) {
        this._lastData = Date.now();
        this._resubscribe(0);
      }
    }, 60 * 1000);
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
    const o = {};
    for (const [key, def] of Object.entries(WL_DEFAULTS)) o[key] = c[key] ?? def;
    return {
      sections,
      o,
      tage: Number(c.tage ?? k.tage ?? 7),
      dez: Number(c.dezimalstellen ?? k.dezimalstellen ?? 1),
      design: c.design || k.design || "auto",
      symbole: c.symbole || k.symbole || "emoji",
      colors,
      regen: c.farbe_regen || k.farbe_regen || "#2f80ed",
      radius: c.eckenradius_px ?? k.eckenradius_px,
      titel: c.titel,
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
    const o = s.o;
    const f = (v, dd = s.dez) => this._fmt(v, dd);
    const signed = (v) => (v >= 0 ? "+" : "−") + f(Math.abs(v));
    switch (id) {
      case "kopf": {
        const j = d.jetzt, g = d.gefuehlt;
        const line = [o.kopf_zustand ? wlEsc(j.zustand) : "",
          o.kopf_messwerte ? `${f(j.temperatur)} °C · ${f(j.feuchte, 0)} % · Wind ${f(j.wind, 0)} km/h` : ""].filter(Boolean).join(" · ");
        const head = (o.kopf_ort || line || o.kopf_symbol) ? `<div class="top"><div>
          ${o.kopf_ort ? `<div class="place">${wlEsc(s.titel || d.titel)}</div>` : ""}
          ${line ? `<div class="muted">${line}</div>` : ""}</div>
          ${o.kopf_symbol ? `<div class="icon">${this._icon(j.zustand_ha, s, 42)}</div>` : ""}</div>` : "";
        let big = "";
        if (o.kopf_gross === "gefuehlt") {
          big = `<span class="big">${f(g.wert)} °C</span> <span class="muted">gefühlt${o.kopf_wort ? `, ${wlEsc(g.wort)}` : ""}</span>`;
          if (o.kopf_begruendung) big += `<br><small class="muted">${g.anteile.map((p) => `${wlEsc(p.grund)} ${signed(p.delta)} °C`).join(" · ") || "keine Korrektur"}</small>`;
        } else if (o.kopf_gross === "temperatur") {
          big = `<span class="big">${f(j.temperatur)} °C</span> <span class="muted">gefühlt ${f(g.wert)} °C${o.kopf_wort ? `, ${wlEsc(g.wort)}` : ""}</span>`;
          if (o.kopf_begruendung) big += `<br><small class="muted">${g.anteile.map((p) => `${wlEsc(p.grund)} ${signed(p.delta)} °C`).join(" · ") || "keine Korrektur"}</small>`;
        }
        return head + (big ? `<div>${big}</div>` : "");
      }
      case "warnungen": {
        if (!d.warnungen_anzeigen) return "";
        if (!d.warnungen.length) {
          if (!o.warnungen_keine) return "";
          const ab = d.mindeststufe > 1 ? ` ab Stufe ${d.mindeststufe}` : "";
          return `<div class="warn" style="--c:var(--s0)"><b>Keine amtlichen Warnungen</b> für ${wlEsc(d.warngebiet || "deinen Ort")}${ab}</div>`;
        }
        return d.warnungen.map((w) => {
          const details = [o.warnungen_zeitraum ? `${this._time(w.beginn)} bis ${w.ende ? this._time(w.ende) : "–"} Uhr` : "",
            o.warnungen_beschreibung && w.beschreibung ? wlEsc(w.beschreibung) : ""].filter(Boolean).join(" · ");
          return `<div class="warn" style="--c:var(--s${Math.min(4, w.stufe)})">
            <b>Amtliche Warnung des DWD</b> · ${wlEsc(w.ueberschrift)}${details ? `<br><small>${details}</small>` : ""}
            ${o.warnungen_verhalten && w.verhaltenshinweise ? `<small class="instr">${wlEsc(w.verhaltenshinweise)}</small>` : ""}</div>`;
        }).join("");
      }
      case "hinweise": {
        const on = d.hinweise.filter((h) => h.an && o.hinweise_auswahl.includes(h.id));
        if (!on.length) return "";
        // Ruhige Hinweise in einer Zeile, außer die Karte soll alle einzeln zeigen.
        const isActive = (h) => h.stufe > 0 || h.amtlich;
        const active = o.hinweise_alle ? on : on.filter(isActive);
        const calm = o.hinweise_alle ? [] : on.filter((h) => !isActive(h));
        const chips = active.length ? `<div class="chips">${active.map((h) => `<div class="chip" style="--c:var(--s${Math.min(4, h.stufe)})">
          <span class="dot"></span><div><b>${wlEsc(h.label)}</b><br><small>${wlEsc(h.text)}</small>
          ${o.hinweise_quelle ? `<br><small class="src">${h.amtlich ? "amtlich (DWD)" : "eigener Hinweis, berechnet"}</small>` : ""}</div></div>`).join("")}</div>` : "";
        const calmLine = calm.length && o.hinweise_ruhig ? `<div class="calm" style="--c:var(--s0)"><span class="dot"></span>
          <span>Ruhig: ${calm.map((h) => wlEsc(h.label)).join(", ")}</span></div>` : "";
        return chips + calmLine;
      }
      case "regen": {
        const r = d.regen;
        if (r.aus) return "";
        const wet = r.schritte.some((x) => (x.mmh || 0) >= 0.1);
        if (o.regen_nur_bei_regen && !wet) return "";
        const max = Math.max(1, ...r.schritte.map((x) => x.mmh || 0));
        const bars = r.schritte.map((x) => {
          const gap = x.mmh === null || x.mmh === undefined;
          const h = gap ? 100 : ((x.mmh || 0) / max) * 100;
          const title = `${this._time(x.t)} · ${gap ? "keine Daten" : f(x.mmh) + " mm/h"}`;
          return `<div class="${gap ? "gap" : ""}" title="${title}" style="height:${h}%"></div>`;
        }).join("");
        const first = r.schritte[0], last = r.schritte[r.schritte.length - 1];
        return `<div><b>Regen</b>${o.regen_text ? ` <span class="muted">· ${wlEsc(r.text)}</span>` : ""}
          ${o.regen_balken ? `<div class="rain">${bars}</div>` : ""}
          ${o.regen_balken && o.regen_zeiten ? `<div class="rainx"><span>${first ? this._time(first.t) : ""}</span><span>${last ? this._time(last.t) : ""}</span></div>` : ""}</div>`;
      }
      case "bericht":
        return d.bericht ? `<div class="bericht">${o.bericht_ueberschrift ? "<b>Tagesbericht</b><br>" : ""}${wlEsc(d.bericht)}</div>` : "";
      case "tage": {
        const ds = d.tage.slice(0, Math.max(1, s.tage));
        if (!ds.length) return "";
        return `<div class="days" style="grid-template-columns:repeat(${Math.min(ds.length, 7)},1fr)">${ds.map((x) => `<div>
          <div>${wlEsc(x.name)}</div>
          ${o.tage_symbol ? `<div class="i">${s.symbole === "text" ? `<small>${wlEsc(x.zustand)}</small>` : this._icon(x.zustand_ha, s, 24)}</div>` : ""}
          <div><b>${f(x.tx, 0)}°</b>${o.tage_tiefstwert ? ` <span class="muted">${f(x.tn, 0)}°</span>` : ""}</div>
          ${o.tage_regen ? `<div class="rr">${x.regen >= 0.1 ? f(x.regen) + " mm" : "&nbsp;"}</div>` : ""}
          ${o.tage_sonne ? `<div class="sun">${f(x.sonne_h, 0)} h ☀</div>` : ""}</div>`).join("")}</div>`;
      }
      case "pollen": {
        const p = d.pollen;
        let arten = p.arten.filter((a) => o.pollen_auswahl.includes(a.name));
        const belastet = arten.filter((a) => a.index > 0);
        if (o.pollen_nur_belastet) arten = belastet;
        if (o.pollen_ausblenden_wenn_keine && !belastet.length) return "";
        const head = `<b>Pollenflug</b> <span class="muted">· ${wlEsc(p.region || "")}, ${wlEsc(p.tag)}</span>`;
        if (!arten.length) return `<div>${head}<div class="muted small">Kein Pollenflug</div></div>`;
        return `<div>${head}<div class="pollen">${arten.map((a) => `<div>${wlEsc(a.name)}<br><small class="muted">${wlEsc(a.label)}</small>
          ${o.pollen_balken ? `<div class="bar"><span style="width:${(a.index / 3) * 100}%"></span></div>` : ""}</div>`).join("")}</div></div>`;
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
    else if (!this._data && this._starting) body = `<div class="msg muted">Wetterlage startet … (die Integration holt gerade die DWD-Daten)</div>`;
    else if (!this._data) body = `<div class="msg muted">Wetterlage lädt …</div>`;
    else if (!this._data.bereit) body = `<div class="msg muted">Noch keine Daten vom DWD.</div>`;
    else body = s.sections.map((id) => this._section(id, this._data, s)).join("");
    const vars = Object.entries(s.colors).map(([i, c]) => `--s${i}:${c};`).join("") + `--rain:${s.regen};`
      + (s.radius !== undefined && s.radius !== null ? `--ha-card-border-radius:${Number(s.radius)}px;` : "");
    const lic = `<a href="https://creativecommons.org/licenses/by/4.0/deed.de" target="_blank" rel="noopener">CC BY 4.0</a>`;
    // Der Quellenvermerk ist Pflicht (CC BY 4.0) und lässt sich nur kürzen, nicht entfernen.
    const foot = s.o.fuss === "kurz"
      ? `Datenbasis: DWD (${lic}), teils berechnet`
      : `Datenbasis: Deutscher Wetterdienst (${lic}), Werte teils von der Integration berechnet. Eigene Hinweise sind Schätzungen, keine amtlichen Warnungen.`;
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
.muted{color:var(--c-muted)}.small{font-size:13px;margin-top:4px}
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
.days .sun{color:var(--c-muted);font-size:11px}
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
  tage: "Anzahl Tage", design: "Design", symbole: "Wettersymbole", dezimalstellen: "Nachkommastellen", fuss: "Quellenvermerk",
  kopf_ort: "Ortsname", kopf_zustand: "Wetterlage als Text", kopf_messwerte: "Messwerte (Temperatur, Feuchte, Wind)",
  kopf_symbol: "Wettersymbol", kopf_gross: "Große Zahl", kopf_wort: "Wort (z. B. „kühl“)", kopf_begruendung: "Begründung der gefühlten Temperatur",
  warnungen_keine: "„Keine Warnungen“ anzeigen", warnungen_zeitraum: "Zeitraum", warnungen_beschreibung: "Beschreibung",
  warnungen_verhalten: "Verhaltenshinweise (wenn in der Integration eingeschaltet)",
  hinweise_auswahl: "Welche Hinweise", hinweise_alle: "Ruhige Hinweise einzeln als Kästchen", hinweise_ruhig: "Zeile „Ruhig: …“",
  hinweise_quelle: "Herkunft (amtlich / berechnet)",
  regen_balken: "Balken", regen_text: "Text", regen_zeiten: "Uhrzeiten unter den Balken", regen_nur_bei_regen: "Nur zeigen, wenn Regen kommt",
  bericht_ueberschrift: "Überschrift „Tagesbericht“",
  tage_symbol: "Wettersymbol", tage_tiefstwert: "Tiefstwert", tage_regen: "Regenmenge", tage_sonne: "Sonnenstunden",
  pollen_auswahl: "Welche Pollenarten", pollen_nur_belastet: "Nur Arten mit Belastung", pollen_ausblenden_wenn_keine: "Abschnitt ausblenden, wenn kein Pollenflug",
  pollen_balken: "Balken",
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
    const bools = (...keys) => keys.map((name) => ({ name, selector: { boolean: {} } }));
    const group = (title, icon, schema) => ({ type: "expandable", flatten: true, title, icon, schema });
    return [
      { name: "eintrag", selector: { select: { mode: "dropdown", options: opt([["", "erster eingerichteter Ort"], ...this._entries.map((e) => [e.entry_id, e.title])]) } } },
      { name: "titel", selector: { text: {} } },
      { name: "abschnitte", selector: { select: { multiple: true, reorder: true, mode: "list", options: opt(Object.entries(WL_SECTIONS)) } } },
      group("Kopf", "mdi:thermometer", [
        ...bools("kopf_ort", "kopf_zustand", "kopf_messwerte", "kopf_symbol"),
        { name: "kopf_gross", selector: { select: { mode: "dropdown", options: opt([["gefuehlt", "gefühlte Temperatur"], ["temperatur", "gemessene Temperatur"], ["keine", "keine"]]) } } },
        ...bools("kopf_wort", "kopf_begruendung"),
      ]),
      group("Amtliche Warnungen", "mdi:alert", bools("warnungen_keine", "warnungen_zeitraum", "warnungen_beschreibung", "warnungen_verhalten")),
      group("Eigene Hinweise", "mdi:alert-circle-outline", [
        { name: "hinweise_auswahl", selector: { select: { multiple: true, mode: "list", options: opt(Object.entries(WL_HINTS)) } } },
        ...bools("hinweise_alle", "hinweise_ruhig", "hinweise_quelle"),
      ]),
      group("Regen", "mdi:weather-rainy", bools("regen_text", "regen_balken", "regen_zeiten", "regen_nur_bei_regen")),
      group("Tagesbericht", "mdi:text-box-outline", bools("bericht_ueberschrift")),
      group("Tagesvorhersage", "mdi:calendar-week", [
        { name: "tage", selector: { number: { min: 1, max: 10, mode: "box" } } },
        ...bools("tage_symbol", "tage_tiefstwert", "tage_regen", "tage_sonne"),
      ]),
      group("Pollenflug", "mdi:flower-pollen", [
        { name: "pollen_auswahl", selector: { select: { multiple: true, mode: "list", options: opt(WL_POLLEN.map((p) => [p, p])) } } },
        ...bools("pollen_nur_belastet", "pollen_ausblenden_wenn_keine", "pollen_balken"),
      ]),
      group("Aussehen", "mdi:palette", [
        { name: "design", selector: { select: { mode: "dropdown", options: opt([["", "wie in der Integration"], ["auto", "wie Home Assistant"], ["hell", "hell"], ["dunkel", "dunkel"]]) } } },
        { name: "symbole", selector: { select: { mode: "dropdown", options: opt([["", "wie in der Integration"], ["emoji", "Symbole"], ["mdi", "Home-Assistant-Icons"], ["text", "nur Text"]]) } } },
        { name: "dezimalstellen", selector: { number: { min: 0, max: 2, mode: "box" } } },
        { name: "fuss", selector: { select: { mode: "dropdown", options: opt([["lang", "ausführlich"], ["kurz", "kurz (Pflichtangaben)"]]) } } },
      ]),
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
          const v = cfg[k];
          const empty = v === "" || v === undefined || v === null;
          const isDefault = k in WL_DEFAULTS && wlSame(v, WL_DEFAULTS[k]);
          const allSections = k === "abschnitte" && wlSame(v, Object.keys(WL_SECTIONS));
          if (empty || isDefault || allSections) delete cfg[k];
        }
        this._config = cfg;
        this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: cfg }, bubbles: true, composed: true }));
      });
      const note = document.createElement("p");
      note.style.cssText = "font-size:12px;color:var(--secondary-text-color)";
      note.textContent = "Hier gesetzte Werte gelten nur für diese Karte. Farben, Schwellen und Texte stehen in der Integration. Der Quellenvermerk des DWD ist Pflicht und bleibt sichtbar.";
      this.appendChild(this._form);
      this.appendChild(note);
    }
    this._form.hass = this._hass;
    // Standardwerte zeigen, damit jeder Schalter seinen aktuellen Zustand hat.
    this._form.data = { abschnitte: Object.keys(WL_SECTIONS), ...WL_DEFAULTS, ...this._config };
    this._form.schema = this._schema();
  }
}

// Anmelden. Manche andere Karten ersetzen nach dem Laden window.customElements durch eine eigene
// Registry (Polyfill); eine vorher angemeldete Karte ist darin unbekannt und Home Assistant zeigt
// „Konfigurationsfehler“. Darum eine Minute lang prüfen und bei Bedarf neu anmelden.
function wlRegister() {
  try {
    if (!customElements.get("wetterlage-card")) customElements.define("wetterlage-card", WetterlageCard);
    if (!customElements.get("wetterlage-card-editor")) customElements.define("wetterlage-card-editor", WetterlageCardEditor);
  } catch (err) {
    console.warn("Wetterlage-Karte: Anmeldung fehlgeschlagen", err);
  }
}
wlRegister();
let wlChecks = 0;
const wlTimer = setInterval(() => {
  wlRegister();
  if (++wlChecks >= 60) clearInterval(wlTimer);
}, 1000);

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
