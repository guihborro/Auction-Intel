/* ═══════════════ Auction Intel — SPA ═══════════════ */
const API = "/api/v1";
let USER = JSON.parse(localStorage.getItem("ai_user") || "null");
let SCAN = [];          // último resultado da varredura
let WATCH = [];         // itens da watchlist
let OCC = "all";        // filtro de ocupação (busca)

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);
const ic = (id, sz) => `<svg class="ic"${sz ? ` style="font-size:${sz}"` : ""}><use href="#${id}"/></svg>`;

/* ---------- Utils ---------- */
const money = (v) =>
  (v == null ? "—" : Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 }));
const clampPct = (v) => Math.max(0, Math.min(100, v));
const discFrac = (im) => {
  const m = im.ml_predicted_price || 0, l = im.auction_price || 0;
  return m > 0 ? (m - l) / m : -1;
};

function toast(msg, kind = "ok") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = msg;
  $("#toasts").appendChild(el);
  setTimeout(() => el.remove(), 3200);
}
async function api(path, opts = {}) {
  const res = await fetch(API + path, { headers: { "Content-Type": "application/json" }, ...opts });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Erro na requisição");
  return data;
}

/* ---------- Tema (claro/escuro) ---------- */
(function initTheme() {
  const root = document.documentElement;
  const sysDark = () => matchMedia("(prefers-color-scheme:dark)").matches;
  const eff = () => root.getAttribute("data-theme") || (sysDark() ? "dark" : "light");
  const paint = () => { const i = $("#theme-ic"); if (i) i.setAttribute("href", eff() === "dark" ? "#i-sun" : "#i-moon"); };
  try { const s = localStorage.getItem("ai_theme"); if (s) root.setAttribute("data-theme", s); } catch (e) {}
  paint();
  $("#theme-btn").addEventListener("click", () => {
    const n = eff() === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", n);
    try { localStorage.setItem("ai_theme", n); } catch (e) {}
    paint();
  });
})();

/* ---------- Auth ---------- */
$$(".auth-tab").forEach((t) =>
  t.addEventListener("click", () => {
    $$(".auth-tab").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    const isLogin = t.dataset.tab === "login";
    $("#login-form").classList.toggle("hidden", !isLogin);
    $("#register-form").classList.toggle("hidden", isLogin);
  })
);

$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#login-msg"); msg.textContent = ""; msg.className = "form-msg";
  try {
    const u = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: $("#login-email").value, password: $("#login-pass").value }),
    });
    setUser(u);
  } catch (err) { msg.textContent = "E-mail ou senha incorretos."; msg.classList.add("error"); }
});

$("#register-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = $("#reg-msg"); msg.textContent = ""; msg.className = "form-msg";
  try {
    await api("/auth/registrar", {
      method: "POST",
      body: JSON.stringify({ email: $("#reg-email").value, password: $("#reg-pass").value }),
    });
    msg.textContent = "Conta criada! Faça login."; msg.classList.add("ok");
    setTimeout(() => $('.auth-tab[data-tab="login"]').click(), 900);
  } catch (err) { msg.textContent = "E-mail já cadastrado ou inválido."; msg.classList.add("error"); }
});

$("#logout-btn").addEventListener("click", () => setUser(null));

function setUser(u) {
  USER = u;
  if (u) localStorage.setItem("ai_user", JSON.stringify(u));
  else localStorage.removeItem("ai_user");
  renderShell();
}
function renderShell() {
  const authed = !!USER;
  $("#auth-view").classList.toggle("hidden", authed);
  $("#app-view").classList.toggle("hidden", !authed);
  if (authed) $("#user-email").textContent = USER.email;
}

/* ---------- Navegação ---------- */
$$(".nav-tab").forEach((t) =>
  t.addEventListener("click", () => {
    $$(".nav-tab").forEach((x) => x.classList.remove("active"));
    t.classList.add("active");
    const v = t.dataset.view;
    $("#busca-view").classList.toggle("hidden", v !== "busca");
    $("#watchlist-view").classList.toggle("hidden", v !== "watchlist");
    if (v === "watchlist") loadWatchlist();
  })
);

/* ---------- Varredura ---------- */
function skeletons(n) {
  return Array.from({ length: n }).map(() => `
    <article class="card sk" aria-hidden="true">
      <div class="card-img"></div>
      <div class="card-body">
        <div class="ln s"></div><div class="ln t"></div>
        <div class="ln"></div><div class="ln" style="height:62px"></div>
        <div class="ln"></div><div class="ln s"></div>
      </div>
    </article>`).join("");
}

function setLoading(title, sub) {
  const t = $("#busca-loading .bl-title"), s = $("#busca-loading .bl-sub");
  if (t) t.textContent = title;
  if (s) s.textContent = sub;
}

$("#scan-btn").addEventListener("click", () => runVarredura());

/* Varredura PROGRESSIVA: lê o stream NDJSON e monta os cards conforme chegam. */
async function runVarredura() {
  const btn = $("#scan-btn"), lbl = btn.querySelector(".lbl");
  btn.disabled = true; if (lbl) lbl.textContent = "Varrendo…";
  $("#busca-empty").classList.add("hidden");
  $("#filters").classList.add("hidden");
  $("#busca-summary").classList.add("hidden");
  $("#busca-loading").classList.remove("hidden");
  setLoading("Iniciando varredura…", "Abrindo o leilão.");
  $("#cards-grid").innerHTML = skeletons(6);
  SCAN = [];
  let total = 0, done = 0, firstItem = true;

  try {
    const res = await fetch(API + "/leiloes/varredura/stream", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: $("#url-select").value }),
    });
    if (!res.ok || !res.body) throw new Error("Falha ao iniciar a varredura.");

    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done: streamDone } = await reader.read();
      if (streamDone) break;
      buf += dec.decode(value, { stream: true });
      let nl;
      while ((nl = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, nl).trim(); buf = buf.slice(nl + 1);
        if (!line) continue;
        let ev; try { ev = JSON.parse(line); } catch (e) { continue; }

        if (ev.type === "status") {
          setLoading("Buscando lotes nas páginas do leilão…", "Isso leva alguns segundos.");
        } else if (ev.type === "total") {
          total = ev.total;
          setLoading(`Avaliando ${total} imóveis com IA…`, "Os cards vão aparecendo conforme ficam prontos.");
          $("#cards-grid").innerHTML = "";
        } else if (ev.type === "item") {
          if (firstItem) { $("#cards-grid").innerHTML = ""; firstItem = false; }
          SCAN.push(ev.imovel);
          $("#cards-grid").insertAdjacentHTML("beforeend", cardHTML(ev.imovel, false, SCAN.length - 1));
          done++;
          setLoading("Avaliando imóveis com IA…", `${done}${total ? " de " + total : ""} prontos.`);
        } else if (ev.type === "done") {
          break;
        } else if (ev.type === "error") {
          throw new Error(ev.detail || "Falha na varredura.");
        }
      }
    }

    if (!SCAN.length) throw new Error("Nenhum imóvel encontrado.");
    buildFilters(SCAN);
    applyBusca();          // ordena e habilita filtros
    renderSummary(SCAN);   // gráfico-resumo dos descontos
    toast(`${SCAN.length} imóveis analisados.`);
  } catch (err) {
    $("#cards-grid").innerHTML = "";
    toast(err.message || "Falha na varredura.", "error");
    $("#busca-empty").classList.remove("hidden");
  } finally {
    $("#busca-loading").classList.add("hidden");
    btn.disabled = false; if (lbl) lbl.textContent = "Realizar varredura";
  }
}

function buildFilters(list) {
  const sel = $("#bairro-filter");
  const bairros = [...new Set(list.map((i) => i.district).filter(Boolean))].sort();
  sel.innerHTML = '<option value="Todos">Todos os bairros</option>' +
    bairros.map((b) => `<option value="${b}">${b}</option>`).join("");
  sel.onchange = applyBusca;
  $("#ordenar").onchange = applyBusca;
  $$("#filters .chip").forEach((ch) =>
    ch.addEventListener("click", () => {
      $$("#filters .chip").forEach((x) => x.setAttribute("aria-pressed", "false"));
      ch.setAttribute("aria-pressed", "true"); OCC = ch.dataset.occ; applyBusca();
    })
  );
  $("#filters").classList.remove("hidden");
}

function applyBusca() {
  let list = SCAN.slice();
  const b = $("#bairro-filter").value;
  if (b && b !== "Todos") list = list.filter((i) => i.district === b);
  if (OCC !== "all") list = list.filter((i) => (i.occupancy || "") === OCC);
  const k = $("#ordenar").value;
  list.sort((a, b) => {
    if (k === "lance") return (a.auction_price || 0) - (b.auction_price || 0);
    if (k === "area") return (b.area_m2 || 0) - (a.area_m2 || 0);
    return discFrac(b) - discFrac(a);
  });
  $("#result-count").innerHTML = `<b>${list.length}</b> imóveis`;
  renderCards(list, "#cards-grid", false);
}

/* Gráfico-resumo: distribuição de desconto (lance vs. mercado) do lote varrido */
function renderSummary(list) {
  const box = $("#busca-summary");
  const withMkt = list.filter((i) => (i.ml_predicted_price || 0) > 0);
  if (!withMkt.length) { box.classList.add("hidden"); return; }
  const discs = withMkt.map((i) => discFrac(i) * 100).sort((a, b) => a - b);
  const median = discs[Math.floor(discs.length / 2)];
  const buckets = [
    { lab: "Acima do mercado", cls: "b0", test: (d) => d < 0 },
    { lab: "0–15% abaixo", cls: "b1", test: (d) => d >= 0 && d < 15 },
    { lab: "15–30% abaixo", cls: "b2", test: (d) => d >= 15 && d < 30 },
    { lab: "30–45% abaixo", cls: "b3", test: (d) => d >= 30 && d < 45 },
    { lab: "45%+ abaixo", cls: "b4", test: (d) => d >= 45 },
  ].map((b) => ({ ...b, n: discs.filter(b.test).length }));
  const max = Math.max(1, ...buckets.map((b) => b.n));
  box.innerHTML = `
    <div class="sum-head">
      <h3>Panorama da varredura</h3>
      <span class="sum-median">Mediana de desconto <b>${Math.round(median)}%</b></span>
    </div>
    <div class="sum-chart">
      ${buckets.map((b) => `
        <div class="sum-row">
          <span class="sum-lab">${b.lab}</span>
          <div class="sum-track"><div class="sum-fill ${b.cls}" style="width:${(b.n / max) * 100}%"></div></div>
          <span class="sum-n">${b.n}</span>
        </div>`).join("")}
    </div>`;
  box.classList.remove("hidden");
}

/* ---------- Watchlist ---------- */
async function loadWatchlist() {
  try {
    WATCH = await api(`/watchlist/${USER.id}`);
    if (!WATCH.length) { $("#watchlist-empty").classList.remove("hidden"); $("#watchlist-grid").innerHTML = ""; }
    else { $("#watchlist-empty").classList.add("hidden"); renderCards(WATCH, "#watchlist-grid", true); }
  } catch (err) { toast("Erro ao carregar watchlist.", "error"); }
}
async function saveToWatchlist(imovel) {
  const payload = {
    title: imovel.title, district: imovel.district, area_m2: imovel.area_m2,
    bedrooms: imovel.bedrooms || 0, parking_spaces: imovel.parking_spaces || 0,
    bathrooms: imovel.bathrooms || 0, auction_price: imovel.auction_price,
    ml_predicted_price: imovel.ml_predicted_price || 0, roi_potential: imovel.roi_potential || 0,
    itbi_price: imovel.itbi_price || null,
    link: imovel.link, image_url: imovel.image_url || null, owner_id: USER.id,
  };
  try { await api("/watchlist/", { method: "POST", body: JSON.stringify(payload) }); toast("Imóvel salvo!"); }
  catch (err) { toast("Erro ao salvar.", "error"); }
}
async function deleteFromWatchlist(id) {
  try { await api(`/watchlist/${id}`, { method: "DELETE" }); toast("Removido."); loadWatchlist(); }
  catch (err) { toast("Erro ao remover.", "error"); }
}

/* ---------- Render de cards ---------- */
function dealBar(im) {
  const mkt = im.ml_predicted_price || 0, lance = im.auction_price || 0, piso = im.itbi_price;
  if (!(mkt > 0 && lance > 0)) return "";
  const d = (mkt - lance) / mkt;
  const cls = d >= 0.25 ? "good" : d >= 0.10 ? "mid" : d > 0 ? "low" : "bad";
  const txt = d >= 0 ? `${Math.round(d * 100)}% abaixo` : `${Math.round(-d * 100)}% acima`;
  const fill = clampPct((lance / mkt) * 100);
  const tick = piso ? `<span class="deal-tick" style="left:${clampPct((piso / mkt) * 100)}%" title="Piso ITBI"></span>` : "";
  return `
    <div class="deal">
      <div class="deal-head"><span>Lance vs. mercado</span><span class="deal-disc ${cls}">${txt}</span></div>
      <div class="deal-track"><div class="deal-fill" style="width:${fill}%"></div>${tick}</div>
      <div class="deal-scale"><span>R$ 0</span><span><b>Mercado ${money(mkt)}</b></span></div>
    </div>`;
}

function cardHTML(im, isWatch, idx) {
  const mkt = im.ml_predicted_price || 0, lance = im.auction_price || 0;
  const d = mkt > 0 ? (mkt - lance) / mkt : null;
  const bCls = d == null ? "low" : d >= 0.25 ? "good" : d >= 0.10 ? "mid" : d > 0 ? "low" : "bad";
  const bTxt = d == null ? "—" : d >= 0 ? `${Math.round(d * 100)}% abaixo` : `${Math.round(-d * 100)}% acima`;
  const badge = `<span class="badge ${bCls}">${ic("i-check", "13px")}${bTxt}</span>`;
  const img = im.image_url
    ? `<img src="${im.image_url}" alt="" loading="lazy" onerror="this.style.display='none';this.nextElementSibling.style.display='grid'"/><div class="no-img" style="display:none">${ic("i-building")}</div>`
    : `<div class="no-img">${ic("i-building")}</div>`;
  const occ = im.occupancy ? `<span class="occ-tag">${im.occupancy}</span>` : "";
  const floor = im.itbi_price
    ? `<div class="price-row floor"><span class="label">Piso ITBI (conservador)</span><span class="val">${money(im.itbi_price)}</span></div>`
    : "";
  const action = isWatch
    ? `<button class="btn btn-ghost btn-sm" data-action="del" data-id="${im.id}">${ic("i-trash")}<span>Remover</span></button>`
    : `<button class="btn btn-ghost btn-sm" data-action="save" data-link="${im.link}">${ic("i-bookmark")}<span>Salvar</span></button>`;
  return `
  <article class="card">
    <div class="card-img">${img}${badge}${occ}</div>
    <div class="card-body">
      <span class="card-district">${ic("i-pin")}${im.district || "São Paulo"}</span>
      <h3 class="card-title">${im.title}</h3>
      <div class="card-meta">
        <span>${ic("i-area")}${Math.round(im.area_m2 || 0)} m²</span>
        <span>${ic("i-bed")}${im.bedrooms || 0}</span>
        <span>${ic("i-bath")}${im.bathrooms || 0}</span>
        <span>${ic("i-car")}${im.parking_spaces || 0}</span>
      </div>
      ${dealBar(im)}
      <div class="price-block">
        <div class="price-row"><span class="label">Lance atual</span><span class="val">${money(im.auction_price)}</span></div>
        <div class="price-row market"><span class="label">Valor de mercado</span><span class="val">${money(im.ml_predicted_price)}</span></div>
        ${floor}
      </div>
      <div class="card-actions">
        ${action}
        <a class="btn btn-primary btn-sm link-btn" href="${im.link}" target="_blank" rel="noopener">Ver leilão ${ic("i-ext")}</a>
      </div>
      <button class="btn btn-ghost btn-sm edital-btn" data-action="edital"
        data-link="${im.link}" data-mkt="${im.ml_predicted_price || 0}" data-lance="${im.auction_price || 0}">
        ${ic("i-scale")} Analisar edital com IA
      </button>
    </div>
  </article>`;
}

function renderCards(list, sel, isWatch) {
  $(sel).innerHTML = list.map((im, i) => cardHTML(im, isWatch, i)).join("");
}

/* Delegação: salvar / remover / analisar edital */
$("#cards-grid").addEventListener("click", (e) => {
  const save = e.target.closest("[data-action='save']");
  if (save) { const im = SCAN.find((x) => x.link === save.dataset.link); if (im) saveToWatchlist(im); return; }
  const ed = e.target.closest("[data-action='edital']");
  if (ed) analisarEdital(ed);
});
$("#watchlist-grid").addEventListener("click", (e) => {
  const del = e.target.closest("[data-action='del']");
  if (del) return deleteFromWatchlist(del.dataset.id);
  const ed = e.target.closest("[data-action='edital']");
  if (ed) analisarEdital(ed);
});

/* ---------- Dossiê do edital (LLM) ---------- */
async function analisarEdital(btn) {
  const link = btn.dataset.link;
  const mkt = +btn.dataset.mkt || 0;
  const lance = +btn.dataset.lance || 0;
  openEdital(`<div class="ed-loading"><div class="mini-scope"><div class="scope-ring"></div></div>
    <div><p class="bl-title">Lendo edital e matrícula com IA…</p>
    <p class="bl-sub">Baixando os PDFs, lendo tudo e traduzindo para linguagem simples.
      Leva cerca de <b>1 minuto</b> — pode aguardar.</p></div></div>`);
  try {
    const d = await api("/leiloes/edital", { method: "POST", body: JSON.stringify({ link }) });
    renderDossie(d, mkt, lance);
  } catch (err) {
    openEdital(`<p class="ed-error">Falha ao analisar: ${err.message}</p>`);
  }
}

function renderDossie(d, mkt, lance) {
  if (!d.ok) {
    openEdital(`<p class="ed-error">${ic("i-alert")} ${d.reason || "Não foi possível analisar."}</p>
      <p class="ed-hint">Configure a chave do LLM no <code>.env</code> (LLM_API_KEY) para habilitar.</p>`);
    return;
  }
  const debito = d.debito_total_arrematante || 0;
  const custo = lance + debito;
  const roiReal = custo > 0 ? ((mkt - custo) / custo) * 100 : 0;
  const roiNaive = lance > 0 ? ((mkt - lance) / lance) * 100 : 0;
  const roiCls = roiReal > 0 ? "pos" : "neg";
  const riscoCls = { "Baixo": "pos", "Médio": "warn", "Alto": "neg" }[d.nivel_risco] || "warn";
  const m0 = (v) => (v == null ? null : money(v));

  const tags = [d.tipo_leilao, d.tipo_direito, d.ocupacao, d.aceita_financiamento ? "Aceita financiamento" : null]
    .filter(Boolean).map((t) => `<span class="ed-tag">${t}</span>`).join("");

  const list = (arr, cls, icon) =>
    (arr && arr.length) ? `<ul class="ed-list ${cls}">${arr.map((x) => `<li>${ic(icon)}<span>${x}</span></li>`).join("")}</ul>` : "";

  const row = (k, v) => (v == null || v === "") ? "" : `<div class="ed-row"><span>${k}</span><b>${v}</b></div>`;
  const detalhes = [
    row("Débito de IPTU", m0(d.debito_iptu)),
    row("Débito de condomínio", m0(d.debito_condominio)),
    row("Dívida ativa", m0(d.divida_ativa)),
    row("Dívidas por conta de", d.debitos_responsavel),
    row("Valor de avaliação", m0(d.valor_avaliacao)),
    row("Condições de pagamento", d.condicoes_pagamento),
    row("Comissão do leiloeiro", d.comissao_leiloeiro),
    row("Desocupação", d.prazo_desocupacao),
  ].join("");

  const onus = (d.onus_gravames || []).length
    ? list(d.onus_gravames, "alert", "i-alert")
    : `<p class="ed-okline">${ic("i-check")} Nenhum ônus/gravame relevante encontrado na matrícula.</p>`;

  const glos = (d.glossario || []).length
    ? `<div class="ed-section"><h4>${ic("i-book")} Glossário — o que os termos significam</h4>
        <dl class="ed-glos">${d.glossario.map((g) =>
          `<div><dt>${g.termo || g.term || ""}</dt><dd>${g.explicacao || g.definicao || ""}</dd></div>`).join("")}</dl></div>`
    : "";

  // barra de composição de custo (lance + dívidas vs mercado)
  let cost = "";
  if (mkt > 0) {
    const lW = clampPct((lance / mkt) * 100);
    const dW = clampPct((debito / mkt) * 100);
    const gW = Math.max(0, 100 - lW - dW);
    const over = custo > mkt;
    cost = `
      <div class="ed-section"><h4>${ic("i-coins")} Quanto você paga de verdade</h4>
        <div class="cost">
          <div class="cbar">
            <div class="seg lance" style="width:${lW}%">Lance</div>
            ${dW > 0 ? `<div class="seg div" style="width:${dW}%" title="Dívidas herdadas"></div>` : ""}
            ${over ? `<div class="seg over" style="width:${clampPct(((custo - mkt) / mkt) * 100)}%">acima do mercado</div>`
                   : `<div class="seg gain" style="width:${gW}%">ganho</div>`}
          </div>
          <div class="clegend">
            <span><span class="dot" style="background:var(--primary)"></span>Lance ${money(lance)}</span>
            <span><span class="dot" style="background:var(--warn)"></span>Dívidas herdadas ${money(debito)}</span>
            <span><span class="dot" style="background:color-mix(in srgb,var(--good) 40%,var(--surface))"></span>Mercado ${money(mkt)}</span>
          </div>
          <div class="ed-roi-final ${roiCls}"><span class="k">ROI real (já descontando as dívidas)</span>
            <span class="v">${roiReal > 0 ? "+" : ""}${roiReal.toFixed(0)}%</span></div>
          <p class="ed-hint">Sem contar as dívidas, pareceria ${roiNaive > 0 ? "+" : ""}${roiNaive.toFixed(0)}%. Mostramos o número honesto.</p>
        </div>
      </div>`;
  }

  openEdital(`
    <div class="ed-head">
      <span class="ed-risco ${riscoCls}">${ic("i-shield", "13px")} Risco: ${d.nivel_risco || "—"}</span>
      <div class="ed-tags">${tags}</div>
    </div>
    ${d.resumo_leigo ? `<p class="ed-resumo">${d.resumo_leigo}</p>` : ""}
    ${d.recomendacao ? `<div class="ed-reco"><b>Em resumo:</b> ${d.recomendacao}</div>` : ""}
    ${cost}
    ${(d.pontos_positivos || []).length ? `<div class="ed-section"><h4>${ic("i-check")} Pontos positivos</h4>${list(d.pontos_positivos, "ok-list", "i-check")}</div>` : ""}
    ${(d.pontos_atencao || []).length ? `<div class="ed-section"><h4>${ic("i-alert")} Pontos de atenção</h4>${list(d.pontos_atencao, "alert", "i-alert")}</div>` : ""}
    ${detalhes ? `<div class="ed-section"><h4>${ic("i-list")} Detalhes financeiros</h4><div class="ed-rows">${detalhes}</div></div>` : ""}
    <div class="ed-section"><h4>${ic("i-shield")} Ônus / gravames (matrícula)</h4>${onus}</div>
    ${glos}
    ${(d.fonte_pdfs || []).length ? `<p class="ed-src">Baseado em ${d.fonte_pdfs.length} documento(s): edital e matrícula.</p>` : ""}
  `);
}

function openEdital(html) {
  $("#edital-body").innerHTML = html;
  $("#edital-modal").classList.remove("hidden");
}
$("#edital-close").addEventListener("click", () => $("#edital-modal").classList.add("hidden"));
$("#edital-modal").addEventListener("click", (e) => { if (e.target.id === "edital-modal") $("#edital-modal").classList.add("hidden"); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") $("#edital-modal").classList.add("hidden"); });

/* ---------- Boot ---------- */
renderShell();
