const $ = (s, el = document) => el.querySelector(s);
const h = (tag, props = {}, ...kids) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
};
const show = id => document.querySelectorAll(".view").forEach(v => (v.hidden = v.id !== id));
const STAGES = [["read", "Reading"], ["cites", "Citations"], ["digest", "Digesting"], ["summary", "Summary"], ["review", "Reviewing"], ["global", "Cross-check"], ["verdict", "Verdict"]];
const SEV = ["critical", "major", "minor"];
const RECS = { "accept": "accept", "minor revision": "minor", "major revision": "major", "reject": "reject" };

let file = null, R = null, sevFilter = "all", catFilter = "all", showAll = false;

async function pollHealth() {
  try {
    const s = await (await fetch("/api/health")).json();
    const m = $("#model");
    m.className = "model " + s.state;
    $("span", m).textContent = s.state === "ready" ? `${s.model} · ${s.device}` : s.state === "error" ? "API key / model problem · hover" : `loading ${s.model}…`;
    if (s.state === "error") m.title = s.error;
    if (s.state === "loading" || s.state === "idle") setTimeout(pollHealth, 2000);
  } catch { setTimeout(pollHealth, 3000); }
}
pollHealth();

const drop = $("#drop"), input = $("#file");
function pick(f) {
  if (!f) return;
  file = f;
  drop.classList.add("has");
  $("#drop-title").textContent = f.name;
  $("#drop-sub").textContent = (f.size / 1048576).toFixed(1) + " MB · ready";
  $("#go").disabled = false;
  $("#err").textContent = "";
}
input.addEventListener("change", () => pick(input.files[0]));
["dragenter", "dragover"].forEach(e => drop.addEventListener(e, ev => { ev.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach(e => drop.addEventListener(e, ev => { ev.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", ev => pick(ev.dataTransfer.files[0]));
$("#go").addEventListener("click", start);
$("#x-new").addEventListener("click", () => { file = null; R = null; drop.classList.remove("has"); $("#drop-title").textContent = "Drop a paper here"; $("#drop-sub").textContent = "PDF, DOCX, TXT or MD · or click to browse"; $("#go").disabled = true; input.value = ""; show("v-upload"); });
$("#tabs").addEventListener("click", e => { const t = e.target.dataset.t; if (t) tab(t); });

function tab(t) {
  document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("on", b.dataset.t === t));
  ["review", "summary", "cites"].forEach(n => ($("#t-" + n).hidden = n !== t));
}

async function start() {
  const fd = new FormData();
  fd.append("file", file);
  fd.append("verify_online", $("#online").checked);
  $("#rail").replaceChildren(...STAGES.map(([k, l]) => h("li", { dataset: { k } }, l)));
  $("#log").textContent = "";
  setProgress(0, "read");
  show("v-run");
  const r = await fetch("/api/analyze", { method: "POST", body: fd });
  if (!r.ok) { show("v-upload"); $("#err").textContent = (await r.json()).detail || "Upload failed."; return; }
  poll((await r.json()).job_id);
}

function setProgress(p, stage) {
  $("#pct").textContent = Math.round(p * 100);
  $("#bar").style.width = p * 100 + "%";
  const idx = STAGES.findIndex(s => s[0] === stage);
  document.querySelectorAll("#rail li").forEach((li, i) => {
    li.className = i < idx ? "done" : i === idx ? "now" : "";
  });
}

async function poll(id) {
  const s = await (await fetch(`/api/jobs/${id}`)).json();
  setProgress(s.progress, s.stage);
  $("#log").textContent = s.log.map(l => "› " + l).join("\n");
  if (s.status === "running") return setTimeout(() => poll(id), 1000);
  if (s.status === "error") { show("v-upload"); $("#err").textContent = s.error; return; }
  R = await (await fetch(`/api/jobs/${id}/result`)).json();
  render();
}

function render() {
  const F = R.review.findings, ok = F.filter(f => f.grounded);
  sevFilter = "all"; catFilter = "all"; showAll = false;
  $("#r-file").textContent = `${R.meta.filename} · ${R.meta.words.toLocaleString()} words · ${R.meta.model}`;
  $("#r-title").textContent = R.summary.title;
  $("#r-counts").replaceChildren(...SEV.map(s => h("div", { class: "pill" }, h("i", { style: `background:var(--${s === "critical" ? "crit" : s})` }), h("b", {}, ok.filter(f => f.severity === s).length), s)));
  const rec = R.review.recommendation;
  const st = $("#r-stamp"); st.textContent = rec; st.className = "stamp " + RECS[rec];
  renderVerdict(); renderFilters(); renderCards(); renderPaper(); renderSummary(); renderCites();
  tab("review");
  show("v-result");
}

function renderVerdict() {
  const v = R.review, el = $("#verdict");
  el.replaceChildren(
    h("h3", {}, "Overall assessment"),
    h("p", {}, v.overall || "No overall assessment was produced."),
    v.strengths.length && h("h3", {}, "Strengths"), v.strengths.length && h("ul", {}, v.strengths.map(s => h("li", {}, s))),
    v.priorities.length && h("h3", {}, "Fix these first"), v.priorities.length && h("ol", {}, v.priorities.map(s => h("li", {}, s)))
  );
}

function renderFilters() {
  const cats = [...new Set(R.review.findings.map(f => f.category))];
  const unv = R.review.findings.filter(f => !f.grounded).length;
  $("#filters").replaceChildren(
    ...["all", ...SEV].map(s => h("button", { class: "chip" + (sevFilter === s ? " on" : ""), onclick: () => { sevFilter = s; renderFilters(); renderCards(); } }, s)),
    h("select", { onchange: e => { catFilter = e.target.value; renderCards(); } }, ["all", ...cats].map(c => h("option", { value: c, selected: c === catFilter }, c))),
    unv > 0 && h("button", { class: "chip" + (showAll ? " on" : ""), title: "Findings whose quoted text could not be found in the paper", onclick: () => { showAll = !showAll; renderFilters(); renderCards(); } }, `unverified (${unv})`)
  );
}

function renderCards() {
  const list = R.review.findings.filter(f => (showAll || f.grounded) && (sevFilter === "all" || f.severity === sevFilter) && (catFilter === "all" || f.category === catFilter));
  $("#cards").replaceChildren(...(list.length ? list.map(card) : [h("div", { class: "empty" }, "No findings match. The reviewer found nothing it could anchor to the text.")]));
}

function card(f) {
  return h("article", { class: "card" + (f.grounded ? "" : " dim"), dataset: { id: f.id, sev: f.severity }, onclick: () => focusFinding(f.id, true) },
    h("header", {}, h("span", { class: "num" }, f.id), h("div", {}, h("h4", {}, f.title),
      h("div", { class: "meta" }, h("span", {}, f.severity), h("span", {}, f.category), f.section && h("span", {}, f.section), !f.grounded && h("span", { class: "warn" }, "quote not located – verify manually")))),
    h("div", { class: "body" }, f.quote && h("blockquote", {}, f.quote), h("p", {}, f.explanation), f.fix && h("div", { class: "fix" }, h("b", {}, "Suggested fix"), f.fix)));
}

function focusFinding(id, fromCard) {
  document.querySelectorAll(".card").forEach(c => c.classList.toggle("open", +c.dataset.id === id && (fromCard ? !c.classList.contains("open") : true)));
  const mk = $(`mark[data-id="${id}"]`);
  const paper = $("#paper"), panel = $(".panel");
  if (mk) { paper.scrollTo({ top: mk.offsetTop - paper.clientHeight / 2, behavior: "smooth" }); mk.classList.remove("pulse"); void mk.offsetWidth; mk.classList.add("pulse"); }
  const cd = $(`.card[data-id="${id}"]`);
  if (!fromCard && cd) panel.scrollTo({ top: cd.offsetTop - 12, behavior: "smooth" });
}

function renderPaper() {
  const T = R.text, rank = { critical: 0, major: 1, minor: 2 };
  const marks = [];
  for (const f of [...R.review.findings].filter(f => f.grounded && f.span).sort((a, b) => rank[a.severity] - rank[b.severity]))
    if (!marks.some(m => f.span[0] < m.e && f.span[1] > m.s)) marks.push({ s: f.span[0], e: f.span[1], f });
  const heads = R.meta.heads.filter(([s, e]) => !marks.some(m => s < m.e && e > m.s)).map(([s, e]) => ({ s, e }));
  const items = [...marks, ...heads].sort((a, b) => a.s - b.s);
  const out = []; let pos = 0;
  for (const it of items) {
    if (it.s < pos) continue;
    out.push(T.slice(pos, it.s));
    const txt = T.slice(it.s, it.e);
    out.push(it.f
      ? h("mark", { class: "hl", dataset: { id: it.f.id, sev: it.f.severity }, onclick: () => focusFinding(it.f.id, false) }, txt, h("sup", { class: "pin" }, it.f.id))
      : h("span", { class: "head" }, txt));
    pos = it.e;
  }
  out.push(T.slice(pos));
  $("#paper").replaceChildren(...out);
}

function renderSummary() {
  const s = R.summary, list = a => h("ul", {}, a.length ? a.map(x => h("li", {}, x)) : h("li", {}, "Not stated"));
  $("#t-summary").replaceChildren(
    h("p", { class: "tldr" }, s.tldr || "No summary was produced."),
    h("div", { class: "grid" },
      h("div", { class: "sec" }, h("h3", {}, "Research question"), h("p", {}, s.research_question || "Not stated")),
      h("div", { class: "sec" }, h("h3", {}, "Approach"), h("p", {}, s.approach || "Not stated")),
      h("div", { class: "sec" }, h("h3", {}, "Key findings"), list(s.key_findings)),
      h("div", { class: "sec" }, h("h3", {}, "Contributions"), list(s.contributions)),
      h("div", { class: "sec" }, h("h3", {}, "Limitations the authors state"), list(s.stated_limitations)),
      h("div", { class: "sec" }, h("h3", {}, "Keywords"), h("div", { class: "kw" }, s.keywords.map(k => h("span", {}, k))))
    ));
}

function renderCites() {
  const c = R.citations, st = c.stats, el = $("#t-cites");
  if (!c.found) { el.replaceChildren(h("div", { class: "empty" }, c.issues[0]?.text || "No references found.")); return; }
  const tile = (n, l, cls) => h("div", { class: "tile " + (cls || "") }, h("b", {}, n ?? "–"), h("span", {}, l));
  const hist = c.histogram, max = Math.max(1, ...hist.map(x => x[1]));
  const y0 = hist[0]?.[0], y1 = hist.at(-1)?.[0];
  const bars = [];
  if (hist.length) for (let y = y0; y <= y1; y++) { const n = (hist.find(x => x[0] === y) || [0, 0])[1]; bars.push(h("div", { style: `height:${Math.max(n ? 8 : 1, n / max * 100)}%`, dataset: { t: `${y}: ${n}` } })); }
  el.replaceChildren(
    h("div", { class: "tiles" },
      tile(st.references, "references"), tile(st.in_text, "in-text citations"),
      tile(st.dangling, "citations with no entry", st.dangling ? "bad" : "good"),
      tile(st.uncited, "never cited", st.uncited ? "bad" : "good"),
      st.online && tile(st.verified, "verified online", "good"),
      st.online && tile(st.mismatch, "mismatched", st.mismatch ? "bad" : ""),
      st.recent_share != null && tile(Math.round(st.recent_share * 100) + "%", "from the last 5 years")),
    hist.length > 1 && h("div", { class: "sec" }, h("h3", {}, `Publication years · ${c.style} style`), h("div", { class: "hist" }, bars), h("div", { class: "axis" }, h("span", {}, y0), h("span", {}, "median " + st.median_year), h("span", {}, y1))),
    c.issues.length > 0 && h("div", { class: "sec", style: "margin-top:14px" }, h("h3", {}, "Issues"), c.issues.slice(0, 40).map(i => h("div", { class: "issue" }, h("code", {}, i.type), h("span", {}, i.text)))),
    h("p", { class: "note" }, st.online ? "“Unverified” means no close match in Crossref. Preprints, books, theses and many conference papers are not indexed there, so check these by hand before calling them fabricated." : "Online verification was off, so only internal consistency was checked."),
    h("div", { class: "tablewrap" }, h("table", {},
      h("thead", {}, h("tr", {}, ["#", "Reference", "Year", "Cited", "Status"].map(x => h("th", {}, x)))),
      h("tbody", {}, c.references.map(r => h("tr", {},
        h("td", {}, r.n),
        h("td", { class: "raw" }, r.raw, r.flags.length > 0 && h("small", {}, r.flags.join(" · ")), r.match && r.status !== "verified" && h("small", {}, `closest match: ${r.match.title} (${r.match.year ?? "?"})`)),
        h("td", {}, r.year ?? "–"), h("td", {}, r.cites + "×"),
        h("td", {}, h("span", { class: "badge " + r.status }, r.status))))))));
}

function download(name, type, body) {
  const a = h("a", { href: URL.createObjectURL(new Blob([body], { type })), download: name });
  a.click(); URL.revokeObjectURL(a.href);
}
$("#x-json").addEventListener("click", () => { const { text, ...rest } = R; download("review.json", "application/json", JSON.stringify(rest, null, 2)); });
$("#x-md").addEventListener("click", () => {
  const s = R.summary, v = R.review, c = R.citations.stats;
  const L = a => (a.length ? a.map(x => `- ${x}`).join("\n") : "- Not stated");
  const md = [`# Review: ${s.title}`, `*${R.meta.filename} · ${R.meta.model}* · **Recommendation: ${v.recommendation}**`, "",
    "## Summary", s.tldr, "", `**Research question:** ${s.research_question}`, "", `**Approach:** ${s.approach}`, "", "### Key findings", L(s.key_findings), "",
    "## Overall assessment", v.overall, "", "### Fix these first", v.priorities.map((p, i) => `${i + 1}. ${p}`).join("\n"), "",
    "## Findings", ...v.findings.filter(f => f.grounded).map(f => `### ${f.id}. ${f.title}\n*${f.severity} · ${f.category}*\n\n> ${f.quote}\n\n${f.explanation}\n\n**Fix:** ${f.fix}\n`),
    "## Citations", `${c.references ?? 0} references, ${c.in_text ?? 0} in-text citations, ${c.dangling ?? 0} dangling, ${c.uncited ?? 0} uncited.`,
    ...R.citations.issues.map(i => `- ${i.text}`)].join("\n");
  download("review.md", "text/markdown", md);
});
