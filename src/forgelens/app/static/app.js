// ForgeLens web app: examine a statement, and browse the project's results.
// Plain ES module, no build step. Every string from the server or a file goes into the page
// through textContent or attributes, never as HTML.

const $ = (sel, root = document) => root.querySelector(sel);
const SVG = "http://www.w3.org/2000/svg";

function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  setAttrs(el, attrs);
  el.append(...kids.flat().filter((k) => k !== null && k !== undefined && k !== false));
  return el;
}
function s(tag, attrs = {}, ...kids) {
  const el = document.createElementNS(SVG, tag);
  setAttrs(el, attrs);
  el.append(...kids.flat().filter((k) => k !== null && k !== undefined && k !== false));
  return el;
}
function setAttrs(el, attrs) {
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.setAttribute("class", v);
    else if (k === "text") el.textContent = v;
    else if (k === "style") for (const [p, val] of Object.entries(v)) el.style.setProperty(p, val);
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
}

const pct = (v) => `${v}%`;
const fmt2 = (v) => {
  if (v === null || v === undefined) return "–";
  const x = Number(v);
  return x !== 0 && Math.abs(x) < 0.01 ? x.toPrecision(2) : x.toFixed(2);
};
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const list = (xs) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs.at(-1)}`);

const state = {
  live: false,
  caps: null,
  samples: [],
  results: null,
  result: null,
  page: 0,
  lamp: false,
  picked: null,
  sampleId: null,
};

// ------------------------------------------------------------------ icons

const ICON = {
  forged: '<path d="M8.2 2h7.6L21 7.2v7.6L15.8 20H8.2L3 14.8V7.2z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M12 7v5.5M12 15.6v.4" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>',
  suspicious: '<path d="M12 3.5L21.5 20h-19z" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/><path d="M12 9.5v4.5M12 16.8v.4" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>',
  clear: '<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><path d="M7.8 12.3l2.8 2.8 5.6-5.8" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>',
  unknown: '<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><path d="M9.6 9.6a2.5 2.5 0 1 1 3.4 2.3c-.7.3-1 .8-1 1.5v.4M12 16.6v.4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
  flagged: '<path d="M12 3.5L21.5 20h-19z" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linejoin="round"/><path d="M12 9.5v4.5M12 16.8v.4" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/>',
  abstained: '<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2.4"/><path d="M8 12h8" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/>',
  not_run: '<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2.4" stroke-dasharray="3 3"/>',
  prev: '<path d="M14.5 6l-6 6 6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
  next: '<path d="M9.5 6l6 6-6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
  lamp: '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.6.4 1 1.1 1 1.8V16h5v-.3c0-.7.4-1.4 1-1.8A6 6 0 0 0 12 3z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/>',
};
function icon(name, size = 24) {
  const el = s("svg", { width: size, height: size, viewBox: "0 0 24 24", "aria-hidden": "true", focusable: "false" });
  el.innerHTML = ICON[name]; // fixed markup from this file only
  return el;
}

const STATUS_LABEL = {
  flagged: "Found evidence",
  clear: "Nothing found",
  abstained: "Could not judge",
  not_run: "Not run here",
};
const STATUS_ORDER = { flagged: 0, clear: 1, abstained: 2, not_run: 3 };
const KIND_PLURAL = {
  digital: "bank PDFs",
  scan: "scans",
  screenshot: "screenshots",
  phone_jpeg: "phone copies",
};

// ------------------------------------------------------------------ start

async function init() {
  window.addEventListener("hashchange", () => route(true));
  route(false);
  try {
    const r = await fetch("api/status", { cache: "no-store" });
    if (!r.ok) throw new Error(String(r.status));
    state.caps = await r.json();
    state.live = true;
  } catch {
    state.live = false;
  }
  try {
    const r = await fetch("static/samples.json");
    if (r.ok) {
      const data = await r.json();
      state.samples = data.samples || [];
      if (!state.live) state.caps = data.capabilities || null;
    }
  } catch {
    state.samples = [];
  }
  renderIntake();
}

function route(moveFocus) {
  const view = location.hash === "#results" ? "results" : "examine";
  $("#view-examine").hidden = view !== "examine";
  $("#view-results").hidden = view !== "results";
  for (const a of document.querySelectorAll(".views a")) {
    if (a.dataset.view === view) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
  document.title = view === "results" ? "Project results, ForgeLens" : "ForgeLens";
  if (view === "results") loadResults(moveFocus);
  else if (moveFocus) focusHeading($("#examine-title"));
}

function focusHeading(el) {
  if (!el) return;
  el.setAttribute("tabindex", "-1");
  el.focus({ preventScroll: false });
}

// ------------------------------------------------------------------ intake

function renderIntake() {
  const caps = state.caps || {};
  const serverState = $("#server-state");
  serverState.replaceChildren();
  if (state.live) {
    serverState.append(
      "Connected: ",
      h("strong", {
        text: caps.fusion
          ? `combined score${caps.image ? ` with image model ${caps.image_model || ""}`.trimEnd() : ""}`
          : "rule-based checks only",
      }),
    );
  } else {
    serverState.append(h("strong", { text: "Preview" }), " with fictional samples");
  }

  const file = $("#file");
  const drop = $("#drop");
  const go = $("#go");
  if (!state.live) {
    file.disabled = true;
    drop.classList.add("is-disabled");
    $("#drop-title").textContent = "Uploading needs the ForgeLens server";
    $("#drop-hint").textContent = "Open a fictional sample below instead";
    $("#bank").disabled = true;
    $("#password").disabled = true;
    $("#privacy").hidden = true;
    $("#preview-note").hidden = false;
  } else {
    file.addEventListener("change", () => pickFile(file.files[0]));
    for (const ev of ["dragenter", "dragover"])
      drop.addEventListener(ev, (e) => {
        e.preventDefault();
        drop.classList.add("is-over");
      });
    for (const ev of ["dragleave", "drop"])
      drop.addEventListener(ev, () => drop.classList.remove("is-over"));
    drop.addEventListener("drop", (e) => {
      e.preventDefault();
      const f = e.dataTransfer?.files?.[0];
      if (f) {
        const dt = new DataTransfer();
        dt.items.add(f);
        file.files = dt.files;
        pickFile(f);
      }
    });
    $("#intake").addEventListener("submit", submit);
  }

  const banks = $("#banks");
  banks.replaceChildren(...(caps.banks || []).map((b) => h("option", { value: b })));

  const caplist = $("#capabilities");
  const row = (name, on, detail) =>
    h("li", {}, h("span", { text: name }), h("span", { class: on ? "on" : "off", text: detail }));
  caplist.replaceChildren(
    row("Arithmetic in the text", true, "Runs"),
    row("PDF structure", true, caps.bank_profiles ? "Runs, with bank profiles" : "Runs"),
    row("Bank layout", !!caps.template, caps.template ? `Runs, ${plural((caps.banks || []).length, "bank", "banks")}` : "No profiles loaded"),
    row("Arithmetic on the page image", !!caps.ocr, caps.ocr ? "Runs" : "Not installed here"),
    row("Image forensics", !!caps.image, caps.image ? `Runs, ${caps.image_model || "ADCD-Net"}` : "GPU server only"),
    row("Combined score", !!caps.fusion, caps.fusion ? "Runs" : "GPU server only"),
  );

  const ul = $("#samples");
  ul.replaceChildren(
    ...state.samples.map((smp) =>
      h(
        "li",
        {},
        h(
          "button",
          { type: "button", "data-id": smp.id, onclick: () => openSample(smp) },
          h("span", { class: "s-name", text: smp.title }),
          h("span", { class: "s-go", text: "Open" }),
          h("span", { class: "s-meta", text: smp.meta }),
        ),
      ),
    ),
  );
  if (!state.samples.length) ul.append(h("li", { class: "s-meta", text: "No samples are bundled with this copy." }));
}

function pickFile(f) {
  const title = $("#drop-title");
  const hint = $("#drop-hint");
  if (!f) {
    title.textContent = "Drop a statement here, or choose a file";
    hint.textContent = "PDF, PNG or JPEG, up to 40 MB";
    $("#go").disabled = true;
    return;
  }
  title.className = "drop-file";
  title.textContent = f.name;
  const mb = f.size / (1024 * 1024);
  hint.textContent = `${mb >= 1 ? mb.toFixed(1) + " MB" : Math.max(1, Math.round(f.size / 1024)) + " KB"}. Choose another file to replace it.`;
  $("#go").disabled = f.size > 40 * 1024 * 1024;
  if (f.size > 40 * 1024 * 1024) hint.textContent = "This file is over 40 MB. Choose a smaller copy.";
}

async function submit(e) {
  e.preventDefault();
  const f = $("#file").files[0];
  if (!f) return;
  const body = new FormData();
  body.append("file", f);
  body.append("bank", $("#bank").value.trim());
  body.append("password", $("#password").value);
  $("#password").value = "";
  state.sampleId = null;
  markSample(null);
  showWorking(f.name);
  $("#go").disabled = true;
  try {
    const r = await fetch("api/analyze", { method: "POST", body });
    const data = await r.json().catch(() => ({ error: "failed", message: "The server sent an answer ForgeLens could not read." }));
    if (data.error) showProblem(data);
    else showResult(data, null);
  } catch {
    showProblem({ error: "offline", message: "The ForgeLens server did not answer. Check that it is still running, then examine the file again." });
  } finally {
    $("#go").disabled = false;
  }
}

function openSample(smp) {
  state.sampleId = smp.id;
  markSample(smp.id);
  showResult(smp.result, smp.truth);
  if (window.matchMedia("(max-width: 960px)").matches)
    $("#light-table").scrollIntoView({ block: "start" });
}

function markSample(id) {
  for (const b of document.querySelectorAll(".sample-list button"))
    if (b.dataset.id === id) b.setAttribute("aria-current", "true");
    else b.removeAttribute("aria-current");
}

// ------------------------------------------------------------------ light table states

function showWorking(name) {
  $("#light-table").replaceChildren(
    h(
      "div",
      { class: "working", role: "status" },
      h(
        "div",
        {},
        h("p", { text: `Examining ${name}` }),
        h("p", { class: "sub", text: "Long statements and the image model can take a minute." }),
        h("div", { class: "progress", "aria-hidden": "true" }),
      ),
    ),
  );
}

function showProblem(p) {
  const title = {
    password: "This PDF needs its password",
    unreadable: "This file could not be read",
    type: "This kind of file cannot be examined",
    size: "This file is too large",
    offline: "The server did not answer",
  }[p.error] || "The examination did not finish";
  $("#light-table").replaceChildren(
    h("div", { class: "problem", role: "alert" }, h("h2", { text: title }), h("p", { text: p.message || "" })),
  );
  if (p.error === "password") $("#password").focus();
}

// ------------------------------------------------------------------ result

function showResult(r, truth) {
  state.result = r;
  state.picked = null;
  const evidencePages = new Set();
  for (const sig of r.signals) for (const f of sig.findings) if (f.page !== null && f.page !== undefined) evidencePages.add(f.page);
  r.pages.forEach((p, i) => p.boxes.length && evidencePages.add(i));
  state.evidencePages = evidencePages;
  state.page = evidencePages.size ? Math.min(...evidencePages) : 0;

  // The reveal marks a result arriving on an empty table or after a wait; swapping one result
  // for another is instant, so flicking through samples never replays it.
  const arriving = !$("#light-table .verdict");
  const verdict = renderVerdict(r, truth);
  if (arriving) verdict.classList.add("reveal");
  const exam = h(
    "div",
    { class: "examination" },
    h("div", { class: arriving ? "viewer reveal" : "viewer", style: { "--d": "60ms" } }, renderViewer(r)),
    h("div", { class: arriving ? "evidence reveal" : "evidence", style: { "--d": "100ms" } }, renderEvidence(r)),
  );
  $("#light-table").replaceChildren(verdict, exam);
  drawPage();
}

function renderVerdict(r, truth) {
  const v = r.verdict;
  const level = v.level || "unknown";
  const headline = v.headline || {
    forged: "Likely edited",
    suspicious: "Worth a closer look",
    clear: "No sign of editing found",
    unknown: "Not enough to go on",
  }[level];
  const pages = plural(r.pages.length, "page", "pages");


  let why;
  if (v.basis === "fusion") {
    const kinds = KIND_PLURAL[r.kind] || "statements";
    why = `Combined score ${fmt2(v.fused)}. Above ${fmt2(v.thresholds["0.01"])} a statement is called likely edited, a line 1 in 100 genuine ${kinds} cross; above ${fmt2(v.thresholds["0.05"])} it is worth a closer look (5 in 100).`;
    if (v.flagged_by.length) why += ` Evidence from ${list(v.flagged_by.map(lowerFirst))}.`;
  } else if (level === "unknown") {
    why = "None of the checks that ran here could read this file well enough to judge it. A copy without a text layer needs the checks that read the page image, which run on the GPU server.";
  } else if (v.flagged_by.length) {
    why = `${list(v.flagged_by)} found signs of editing. The combined score, which weighs the checks against each other and sets the false-alarm line, runs on the GPU server.`;
  } else {
    why = "None of the checks that ran found signs of editing. The combined score and the image model run on the GPU server.";
  }

  const el = h(
    "div",
    { class: "verdict", "data-level": level },
    h("div", { class: "mark" }, icon(level, 24)),
    h("h2", { text: headline }),
    h("span", { class: "took", text: r.seconds !== undefined ? `Examined in ${r.seconds} s` : "" }),
    h("p", { class: "file", text: `${r.file}. ${r.kind_label}, ${pages}${r.bank ? `, compared with ${r.bank}` : ""}.` }),
    h("p", { class: "why", text: why }),
  );
  if (v.basis === "fusion") el.append(renderGauge(v));
  if (truth)
    el.append(h("p", { class: "truth" }, h("strong", { text: "What was done to this sample: " }), truth));
  return el;
}

function renderGauge(v) {
  const W = 600, x0 = 4, x1 = 596, y = 22;
  const X = (t) => x0 + (x1 - x0) * Math.max(0, Math.min(1, t));
  const t5 = v.thresholds["0.05"], t1 = v.thresholds["0.01"];
  const svg = s(
    "svg",
    { viewBox: `0 0 ${W} 64`, role: "img", "aria-label": `Combined score ${fmt2(v.fused)} on a scale of 0 to 1; lines at ${fmt2(t5)} and ${fmt2(t1)}.` },
    s("rect", { x: x0, y: y - 4, width: X(t5) - x0, height: 8, rx: 4, fill: "var(--clear-tint)" }),
    s("rect", { x: X(t5), y: y - 4, width: Math.max(0, X(t1) - X(t5)), height: 8, fill: "var(--suspect-tint)" }),
    s("rect", { x: X(t1), y: y - 4, width: x1 - X(t1), height: 8, rx: 4, fill: "var(--forged-tint)" }),
    s("line", { x1: X(t5), x2: X(t5), y1: y - 9, y2: y + 9, stroke: "var(--suspect)", "stroke-width": 2 }),
    s("line", { x1: X(t1), x2: X(t1), y1: y - 9, y2: y + 9, stroke: "var(--forged)", "stroke-width": 2 }),
    s("text", { x: X(t5), y: y + 26, "text-anchor": X(t5) > 520 ? "end" : "middle", text: "5 in 100 line" }),
    s("text", { x: X(t1), y: y + 40, "text-anchor": X(t1) > 520 ? "end" : "middle", text: "1 in 100 line" }),
    s("circle", { cx: X(v.fused), cy: y, r: 7, fill: "var(--ink)", stroke: "var(--sheet)", "stroke-width": 2 }),
    s("text", { class: "score-label", x: X(v.fused), y: y - 13, "text-anchor": X(v.fused) > 540 ? "end" : X(v.fused) < 60 ? "start" : "middle", text: fmt2(v.fused) }),
  );
  return h("div", { class: "gauge" }, svg);
}

// viewer ---------------------------------------------------------------------

function renderViewer(r) {
  const n = r.pages.length;
  const hasHeat = r.pages.some((p) => p.heat);
  const lampBtn = h(
    "button",
    {
      class: "btn btn-quiet",
      type: "button",
      id: "lamp",
      "aria-pressed": String(state.lamp),
      title: hasHeat ? "Darken the page so edited pixels and marked places glow" : "Darken the page so marked places glow",
      onclick: () => {
        state.lamp = !state.lamp;
        lampBtn.setAttribute("aria-pressed", String(state.lamp));
        $("#page")?.classList.toggle("lamp-on", state.lamp);
        drawNote();
      },
    },
    icon("lamp", 18),
    "Lamp",
  );
  const bar = h(
    "div",
    { class: "viewer-bar" },
    h("button", { class: "btn btn-quiet btn-icon", type: "button", id: "prev", "aria-label": "Previous page", onclick: () => goPage(state.page - 1) }, icon("prev", 18)),
    h("span", { class: "pageno", id: "pageno", "aria-live": "polite" }),
    h("button", { class: "btn btn-quiet btn-icon", type: "button", id: "next", "aria-label": "Next page", onclick: () => goPage(state.page + 1) }, icon("next", 18)),
    h("span", { class: "spacer" }),
    lampBtn,
  );
  const thumbs = h(
    "ol",
    { class: "thumbs", "aria-label": "Pages" },
    r.pages.map((p, i) =>
      h(
        "li",
        {},
        h(
          "button",
          { type: "button", "data-i": i, "aria-label": `Page ${i + 1}${state.evidencePages.has(i) ? ", has evidence" : ""}`, onclick: () => goPage(i) },
          h("img", { src: p.image, alt: "", loading: "lazy", decoding: "async" }),
          h("span", { class: "n", text: String(i + 1) }),
          state.evidencePages.has(i) ? h("span", { class: "dot" }) : null,
        ),
      ),
    ),
  );
  const page = h("figure", { class: `page${state.lamp ? " lamp-on" : ""}`, id: "page", style: { margin: "0 auto" } });
  const wrap = h(
    "div",
    {
      class: "viewer-body",
      onkeydown: (e) => {
        if (e.target.closest("input")) return;
        if (e.key === "ArrowRight") { goPage(state.page + 1); e.preventDefault(); }
        if (e.key === "ArrowLeft") { goPage(state.page - 1); e.preventDefault(); }
      },
    },
    thumbs,
    h("div", {}, page, h("p", { class: "page-note", id: "page-note" })),
  );
  return [bar, wrap].concat(n ? [] : [h("p", { text: "This file has no pages to show." })]);
}

function goPage(i) {
  const n = state.result.pages.length;
  if (i < 0 || i >= n || i === state.page) return;
  state.page = i;
  if (state.picked && state.picked.page !== i) state.picked = null;
  drawPage();
  syncPicked();
}

function drawPage() {
  const r = state.result;
  const p = r.pages[state.page];
  const fig = $("#page");
  if (!p || !fig) return;
  const W = p.width_pt, H = p.height_pt, pad = 2;
  const kids = [h("img", { class: "scan", src: p.image, alt: `Page ${state.page + 1} of ${r.file}`, width: 880, height: Math.round((880 * H) / W) })];
  kids.push(h("div", { class: "dark", "aria-hidden": "true" }));
  if (p.heat) kids.push(h("img", { class: "heat", src: p.heat, alt: "", "aria-hidden": "true" }));
  p.boxes.forEach((b, j) => {
    const [x0, y0, x1, y1] = b.bbox;
    const picked = state.picked && state.picked.signal === b.signal;
    kids.push(
      h("div", {
        class: `box${picked ? " is-picked" : ""}`,
        "data-signal": b.signal,
        title: b.label,
        style: {
          left: `${((x0 - pad) / W) * 100}%`,
          top: `${((y0 - pad) / H) * 100}%`,
          width: `${((x1 - x0 + 2 * pad) / W) * 100}%`,
          height: `${((y1 - y0 + 2 * pad) / H) * 100}%`,
        },
      }),
    );
  });
  fig.replaceChildren(...kids);
  fig.classList.toggle("lamp-on", state.lamp);

  $("#pageno").textContent = `Page ${state.page + 1} of ${r.pages.length}`;
  $("#prev").disabled = state.page === 0;
  $("#next").disabled = state.page === r.pages.length - 1;
  for (const b of document.querySelectorAll(".thumbs button"))
    if (Number(b.dataset.i) === state.page) b.setAttribute("aria-current", "true");
    else b.removeAttribute("aria-current");

  drawNote();
}

function drawNote() {
  const r = state.result;
  const p = r.pages[state.page];
  const onPage = r.signals.flatMap((sig) => sig.findings.filter((f) => f.page === state.page));
  const image = r.signals.find((x) => x.id === "image");
  let note;
  if (p.boxes.length) note = `${plural(p.boxes.length, "place", "places")} on this page marked by the checks.${state.lamp ? "" : " Turn on the lamp to make them stand out."}`;
  else if (onPage.length) note = `${plural(onPage.length, "finding", "findings")} on this page, without an exact position.`;
  else note = "Nothing located on this page.";
  if (image && image.status === "not_run") note += " The image model's heat map appears when it runs on the GPU server.";
  $("#page-note").textContent = note;
}

// evidence -------------------------------------------------------------------

function renderEvidence(r) {
  const sigs = [...r.signals].sort((a, b) => {
    const ca = a.counted === false ? 1 : 0, cb = b.counted === false ? 1 : 0;
    return STATUS_ORDER[a.status] + ca * 0.5 - (STATUS_ORDER[b.status] + cb * 0.5);
  });
  return [h("h2", { text: "Evidence" }), ...sigs.map(renderSignal)];
}

function renderSignal(sig) {
  const block = h(
    "section",
    { class: "signal", "aria-label": sig.name },
    h(
      "div",
      { class: "signal-head" },
      h("h3", { text: sig.name }),
      h("span", { class: "score", text: sig.score === null ? "" : `score ${fmt2(sig.score)}` }),
      h("span", { class: "status", "data-s": sig.status }, icon(sig.status, 14), STATUS_LABEL[sig.status]),
    ),
  );
  if (sig.status === "abstained" || sig.status === "not_run") {
    block.append(h("p", { class: "why-not", text: sig.reason ? capital(sig.reason) + "." : sig.what }));
  } else {
    block.append(h("p", { class: "what", text: sig.what }));
    if (sig.reason) block.append(h("p", { class: "why-not", text: capital(sig.reason) + "." }));
  }
  if (sig.findings.length) {
    block.append(
      h(
        "ul",
        { class: "findings" },
        sig.findings.map((f, i) => {
          const hasPage = f.page !== null && f.page !== undefined;
          const inner = [
            h("span", { class: "t", text: f.title }),
            h("span", { class: "m", text: f.message }),
            hasPage ? h("span", { class: "pg", text: `Page ${f.page + 1}` }) : null,
          ];
          if (!hasPage) return h("li", {}, h("div", { class: "finding" }, inner));
          return h(
            "li",
            {},
            h(
              "button",
              {
                class: "finding",
                type: "button",
                "aria-pressed": "false",
                "data-key": `${sig.id}:${i}`,
                onclick: () => pick(sig.id, i, f.page),
              },
              inner,
            ),
          );
        }),
      ),
    );
  }
  if (sig.counted === false && sig.note) block.append(h("p", { class: "note", text: sig.note }));
  return block;
}

function pick(signal, index, page) {
  const key = `${signal}:${index}`;
  const same = state.picked && state.picked.key === key;
  state.picked = same ? null : { signal, key, page };
  if (page !== state.page) {
    state.page = page;
    drawPage();
  } else {
    for (const b of document.querySelectorAll("#page .box"))
      b.classList.toggle("is-picked", !!state.picked && b.dataset.signal === signal);
  }
  syncPicked();
  if (!same && window.matchMedia("(max-width: 1180px)").matches) $("#page").scrollIntoView({ block: "nearest" });
}

function syncPicked() {
  for (const b of document.querySelectorAll("button.finding"))
    b.setAttribute("aria-pressed", String(!!state.picked && b.dataset.key === state.picked.key));
  for (const b of document.querySelectorAll("#page .box"))
    b.classList.toggle("is-picked", !!state.picked && b.dataset.signal === state.picked.signal);
}

const capital = (t) => t.charAt(0).toUpperCase() + t.slice(1);
const lowerFirst = (t) => (/^[A-Z]{2}/.test(t) ? t : t.charAt(0).toLowerCase() + t.slice(1));

// ------------------------------------------------------------------ results view

async function loadResults(moveFocus) {
  const view = $("#view-results");
  if (!state.results) {
    try {
      const r = await fetch("static/results.json");
      state.results = await r.json();
    } catch {
      view.replaceChildren(h("div", { class: "problem" }, h("h2", { text: "The results could not be loaded" }), h("p", { text: "Reload the page to try again." })));
      return;
    }
    renderResults(state.results);
  }
  if (moveFocus) focusHeading($("#results-title"));
}

function renderResults(R) {
  const H = R.headline;
  const real = H.real.runs;
  const intro = h(
    "div",
    { class: "results-intro" },
    h(
      "div",
      {},
      h("h1", { id: "results-title", text: `ForgeLens catches ${H.test_set.caught_1} in 100 forged statements while flagging 1 in 100 genuine ones` }),
      h("p", { class: "lead", text: "Five checks examine every statement: the arithmetic in its text and on its page image, how the PDF file was built, the bank's usual layout, and an image-forensics network fine-tuned from ADCD-Net. A gradient-boosting model weighs them into one score." }),
      h("p", { class: "lead", text: `Every figure comes from statements the models never saw in training: ${R.data.test_genuine} genuine and ${R.data.test_forged.toLocaleString("en-IN")} forged statements from ten fictional banks, their phone copies, and ${R.data.real_statements} genuine statements from real Indian banks.` }),
    ),
    h(
      "section",
      { class: "ledger", "aria-labelledby": "ledger-title" },
      h("div", { class: "ledger-head" }, h("h2", { id: "ledger-title", text: "Summary of results" }), h("span", { text: `as of ${new Date(R.as_of).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}` })),
      h(
        "dl",
        {},
        ledgerRow("Forgeries caught, held-out test set", "at 1 false alarm per 100 genuine statements", pct(H.test_set.caught_1)),
        ledgerRow("Caught among forgeries that leave a trace", `${H.traceable.no_trace_share}% leave none: re-typed with balances that agree, then turned into an image`, pct(H.traceable.caught_1)),
        ledgerRow("Caught with phone screenshots and WhatsApp copies", "threshold set for each kind of copy", pct(H.with_phone.caught_1)),
        ledgerRow(`Genuine real statements flagged`, `${real.at(-1).read} statements from ${H.real.sources_count} banks, every one genuine`, `${Math.round(real.at(-1).rate)}%`, `${Math.round(real[0].rate)}% in the first run`),
      ),
    ),
  );

  const view = $("#view-results");
  view.replaceChildren(
    intro,
    sectionMatrix(R.signal_matrix),
    sectionAblations(R.ablations),
    sectionCopies(R.copies),
    sectionReal(R.headline.real, R.real_signals),
    sectionModels(R.models),
    sectionReproduction(R.reproduction),
  );
}

function ledgerRow(title, sub, fig, was) {
  return h(
    "div",
    { class: "row" },
    h("dt", { text: title }),
    h("dd", { class: "fig" }, fig, was ? h("span", { class: "was", text: was }) : null),
    h("dd", { class: "sub", text: sub }),
  );
}

function section(id, title, note, ...body) {
  return h("section", { class: "section", "aria-labelledby": id }, h("h2", { id, text: title }), note ? h("p", { class: "note", text: note }) : null, ...body);
}
const reading = (t) => h("p", { class: "reading", text: t });
function source(path) {
  return h("p", { class: "source" }, "Source: ", h("code", { text: path }));
}

// sequential single hue, light to dark (dataviz reference ramp)
const RAMP = [
  [10, "#cde2fb", "ink"], [25, "#b7d3f6", "ink"], [40, "#9ec5f4", "ink"], [55, "#86b6ef", "ink"],
  [70, "#6da7ec", "ink"], [85, "#5598e7", "ink"], [95, "#256abf", "white"], [101, "#184f95", "white"],
];
function rampFor(v) {
  for (const [lim, bg, txt] of RAMP) if (v <= lim) return { bg, txt: txt === "white" ? "#ffffff" : "var(--ink)" };
  return { bg: "#184f95", txt: "#ffffff" };
}

function sectionMatrix(M) {
  const last = M.columns.length - 1;
  const table = h(
    "table",
    { class: "data matrix" },
    h("caption", { class: "visually-hidden", text: M.note }),
    h("thead", {}, h("tr", {}, h("th", { scope: "col", text: "Forgery" }), M.columns.map((c, i) => h("th", { scope: "col", class: i === last ? "ours" : null, text: c })))),
    h(
      "tbody",
      {},
      M.rows.map((r) =>
        h(
          "tr",
          {},
          h("th", { scope: "row" }, r.label, h("span", { class: "sub", text: `${capital(r.copy)}, ${r.n} statements` })),
          r.values.map((v, i) => {
            const c = rampFor(v);
            const cls = [i === last ? "ours" : "", v === 0 ? "zero" : ""].join(" ").trim() || null;
            return h(
              "td",
              { class: cls },
              h("span", { style: v === 0 ? {} : { background: c.bg, color: c.txt }, text: pct(v) }),
            );
          }),
        ),
      ),
    ),
  );
  return section(
    "s-matrix",
    "Each forgery is caught by the check that can see it",
    `${M.note} “Rasterised” means the statement was turned into an image, which removes every trace inside the PDF.`,
    h("div", { class: "tbl-wrap" }, table),
    h("div", { class: "scale", "aria-hidden": "true" }, "0%", h("span", { class: "ramp" }), "100% caught"),
    reading("The image model catches pasted and AI-retouched figures, the PDF checks catch edits made in a PDF editor, and ForgeLens keeps both under one threshold. The weak spot is a statement re-typed with balances that agree and then turned into an image: no check sees much of it."),
    source(M.source),
  );
}

// tooltip ------------------------------------------------------------------

function tipOn(target, title, lines) {
  const tip = $("#tip");
  const show = (x, y) => {
    tip.replaceChildren(h("strong", { text: title }), ...lines.flatMap((l, i) => (i ? [h("br"), l] : [l])));
    tip.hidden = false;
    const r = tip.getBoundingClientRect();
    const left = Math.min(window.innerWidth - r.width - 8, x + 14);
    const top = y + 14 + r.height > window.innerHeight ? y - r.height - 10 : y + 14;
    tip.style.left = `${Math.max(8, left)}px`;
    tip.style.top = `${Math.max(8, top)}px`;
  };
  const hide = () => { tip.hidden = true; };
  target.addEventListener("pointermove", (e) => show(e.clientX, e.clientY));
  target.addEventListener("pointerleave", hide);
  target.addEventListener("focus", () => {
    const b = target.getBoundingClientRect();
    show(b.left + b.width / 2, b.top + b.height / 2);
  });
  target.addEventListener("blur", hide);
}

function axis(svg, X, y0, y1, ticks, fmt) {
  for (const t of ticks) {
    svg.append(s("line", { class: "grid", x1: X(t), x2: X(t), y1: y0, y2: y1 }));
    svg.append(s("text", { class: "axis", x: X(t), y: y1 + 16, "text-anchor": "middle", text: fmt(t) }));
  }
}

function numbersTable(caption, head, rows) {
  return h(
    "details",
    { class: "numbers" },
    h("summary", { text: "Show the numbers" }),
    h(
      "div",
      { class: "tbl-wrap" },
      h(
        "table",
        { class: "data" },
        h("caption", { class: "visually-hidden", text: caption }),
        h("thead", {}, h("tr", {}, head.map((t, i) => h("th", { scope: "col", class: i ? "num" : null, text: t })))),
        h("tbody", {}, rows.map((r) => h("tr", {}, r.map((c, i) => (i ? h("td", { class: "num", text: c }) : h("th", { scope: "row", text: c })))))),
      ),
    ),
  );
}

// ablations: horizontal bars ------------------------------------------------

function sectionAblations(A) {
  const W = 760, L = 250, R = 56, rowH = 34, top = 6;
  const all = A.rows.find((r) => r.all).value;
  const X = (v) => L + ((W - L - R) * v) / 100;
  const Hgt = top + A.rows.length * rowH + 24;
  const svg = s("svg", { viewBox: `0 0 ${W} ${Hgt}`, role: "img", "aria-label": `${A.title}. ${A.rows.map((r) => `${r.label} ${r.value}%`).join("; ")}.` });
  axis(svg, X, top, top + A.rows.length * rowH, [0, 25, 50, 75, 100], pct);
  A.rows.forEach((r, i) => {
    const y = top + i * rowH;
    const g = s("g", {});
    g.append(s("text", { class: "lbl", x: L - 12, y: y + rowH / 2 + 4, "text-anchor": "end", text: r.label, "font-weight": r.all ? 600 : null }));
    const w = Math.max(0, X(r.value) - L);
    // 4px rounded data end, square at the baseline
    g.append(s("path", { d: `M${L},${y + 8}h${Math.max(0, w - 4)}a4,4 0 0 1 4,4v${rowH - 24}a4,4 0 0 1 -4,4h${-Math.max(0, w - 4)}z`, fill: "var(--series-1)" }));
    g.append(s("text", { class: "val", x: X(r.value) + 8, y: y + rowH / 2 + 4, text: pct(r.value) }));
    const hit = s("rect", { class: "hit", x: 0, y, width: W, height: rowH, tabindex: 0, "aria-label": `${r.label}: ${r.value}% caught` });
    const diff = all - r.value;
    tipOn(hit, r.label, [`${r.value}% of forgeries caught at 1% false alarms`, r.all ? "The full system" : diff > 0 ? `${diff} points fewer than with every check` : "The same as with every check"]);
    svg.append(g, hit);
  });
  svg.append(s("line", { x1: X(all), x2: X(all), y1: top, y2: top + A.rows.length * rowH, stroke: "var(--ink)", "stroke-width": 1.5, "stroke-dasharray": "4 4" }));
  return section(
    "s-ablations",
    "Three checks carry the result",
    `${A.note} Without the image model ForgeLens loses 19 points, without the bank layout 9, without arithmetic on the image 8.`,
    h("div", { class: "chart" }, svg),
    numbersTable(A.title, ["Run", "Caught at 1%"], A.rows.map((r) => [r.label, pct(r.value)])),
    reading("Leaving out the PDF-structure or text-arithmetic check changes nothing here, because on these ten banks the layout check catches the same PDF-editor edits. Real statements come from banks without a layout profile, and there PDF structure is what catches them."),
    source(A.source),
  );
}

// dumbbell: two values per row ------------------------------------------------

function dumbbell({ rows, groups, aKey, bKey, aName, bName, domain, fmt, label, rightText, ariaTitle }) {
  const W = 760, L = 200, R = 64, rowH = 30, gH = 30;
  const X = (v) => L + ((W - L - R) * (v - domain[0])) / (domain[1] - domain[0]);
  let y = 4;
  const marks = [];
  let lastGroup = null;
  for (const r of rows) {
    if (groups && r[groups] !== lastGroup) {
      marks.push({ type: "group", y, text: r[groups] });
      y += gH;
      lastGroup = r[groups];
    }
    marks.push({ type: "row", y, r });
    y += rowH;
  }
  const plotBottom = y;
  const svg = s("svg", { viewBox: `0 0 ${W} ${plotBottom + 26}`, role: "img", "aria-label": ariaTitle });
  const ticks = [];
  const step = (domain[1] - domain[0]) / 4;
  for (let t = domain[0]; t <= domain[1] + 1e-9; t += step) ticks.push(+t.toFixed(4));
  axis(svg, X, 0, plotBottom, ticks, fmt);
  for (const m of marks) {
    if (m.type === "group") {
      svg.append(s("text", { class: "grp", x: 0, y: m.y + gH - 9, text: m.text }));
      continue;
    }
    const { r } = m;
    const cy = m.y + rowH / 2;
    const a = r[aKey], b = r[bKey];
    svg.append(
      s("text", { class: "lbl", x: groups ? 14 : 0, y: cy + 4, text: label(r) }),
      s("line", { x1: X(Math.min(a, b)), x2: X(Math.max(a, b)), y1: cy, y2: cy, stroke: "var(--rule-strong)", "stroke-width": 2 }),
      s("circle", { cx: X(a), cy, r: 5, fill: "var(--series-2)", stroke: "var(--sheet)", "stroke-width": 2 }),
      s("circle", { cx: X(b), cy, r: 5, fill: "var(--series-1)", stroke: "var(--sheet)", "stroke-width": 2 }),
      s("text", { class: "val", x: W, y: cy + 4, "text-anchor": "end", text: rightText(r) }),
    );
    const hit = s("rect", { class: "hit", x: 0, y: m.y, width: W, height: rowH, tabindex: 0, "aria-label": `${groups ? r[groups] + ", " : ""}${label(r)}: ${aName} ${fmt(a)}, ${bName} ${fmt(b)}` });
    tipOn(hit, `${groups ? r[groups] + ", " : ""}${label(r)}`, [`${bName}: ${fmt(b)}`, `${aName}: ${fmt(a)}`]);
    svg.append(hit);
  }
  return svg;
}

function legend(items) {
  return h("ul", { class: "legend" }, items.map(([name, color]) => h("li", {}, h("span", { class: "key", style: { "--k": color } }), name)));
}

function sectionCopies(C) {
  const aName = "One threshold for every copy", bName = "Threshold per kind of copy (in use)";
  const svg = dumbbell({
    rows: C.rows, groups: "forgery", aKey: "one", bKey: "per_kind", aName, bName,
    domain: [0, 100], fmt: pct, label: (r) => r.copy, rightText: (r) => pct(r.per_kind),
    ariaTitle: `${C.title}: share caught per forgery and kind of copy, with one threshold and with a threshold per kind.`,
  });
  return section(
    "s-copies",
    "Screenshots hold up; WhatsApp costs about a quarter of image forgeries",
    C.note,
    legend([[bName, "var(--series-1)"], [aName, "var(--series-2)"]]),
    h("div", { class: "chart" }, svg),
    numbersTable(C.title, ["Forgery and copy", "Statements", "One threshold", "Per kind"], C.rows.map((r) => [`${r.forgery}, ${r.copy}`, String(r.n), pct(r.one), pct(r.per_kind)])),
    reading(`Over all ${(1996).toLocaleString("en-IN")} forgeries, ${C.total.per_kind}% are caught with a threshold per kind of copy, against ${C.total.one}% with one. Per kind, every kind of copy gets the same 1 in 100 false-alarm rate. That gains most on PDF edits in screenshots and rasterised copies, which arithmetic on the image catches once the threshold is not spent on WhatsApp noise, and costs WhatsApp copies a few points.`),
    source(C.source),
  );
}

// real statements: rates with confidence intervals --------------------------

function sectionReal(real, sig) {
  const W = 760, L = 250, R = 20, rowH = 46, top = 4;
  const X = (v) => L + ((W - L - R) * v) / 50;
  const runs = real.runs;
  const svg = s("svg", { viewBox: `0 0 ${W} ${top + runs.length * rowH + 26}`, role: "img", "aria-label": `Genuine real statements flagged: ${runs.map((r) => `${r.label}, ${r.rate}% (${r.flagged} of ${r.read}), 95% interval ${r.ci[0]} to ${r.ci[1]}%`).join("; ")}.` });
  axis(svg, X, top, top + runs.length * rowH, [0, 10, 20, 30, 40, 50], pct);
  runs.forEach((r, i) => {
    const cy = top + i * rowH + rowH / 2;
    svg.append(
      s("text", { class: "lbl", x: L - 12, y: cy, "text-anchor": "end", text: r.label }),
      s("text", { class: "axis", x: L - 12, y: cy + 16, "text-anchor": "end", text: r.date }),
      s("line", { x1: X(r.ci[0]), x2: X(r.ci[1]), y1: cy, y2: cy, stroke: "var(--series-1)", "stroke-width": 2 }),
      s("line", { x1: X(r.ci[0]), x2: X(r.ci[0]), y1: cy - 6, y2: cy + 6, stroke: "var(--series-1)", "stroke-width": 2 }),
      s("line", { x1: X(r.ci[1]), x2: X(r.ci[1]), y1: cy - 6, y2: cy + 6, stroke: "var(--series-1)", "stroke-width": 2 }),
      s("circle", { cx: X(r.rate), cy, r: 6, fill: "var(--series-1)", stroke: "var(--sheet)", "stroke-width": 2 }),
      s("text", { class: "val", x: X(r.rate), y: cy - 12, "text-anchor": "middle", text: `${r.rate}%` }),
    );
    const hit = s("rect", { class: "hit", x: 0, y: top + i * rowH, width: W, height: rowH, tabindex: 0, "aria-label": `${r.label}: ${r.rate}%` });
    tipOn(hit, `${r.label}, ${r.date}`, [`${r.flagged} of ${r.read} genuine statements flagged (${r.rate}%)`, `95% interval ${r.ci[0]}–${r.ci[1]}%`]);
    svg.append(hit);
  });
  const t = h(
    "table",
    { class: "data" },
    h("caption", { class: "visually-hidden", text: "Genuine real statements flagged by each check, first run and after the rule fixes" }),
    h("thead", {}, h("tr", {}, h("th", { scope: "col", text: "Check" }), h("th", { scope: "col", class: "num", text: "First run" }), h("th", { scope: "col", class: "num", text: "Rules fixed" }))),
    h(
      "tbody",
      {},
      sig.rows.map((r) =>
        h(
          "tr",
          { class: r.signal === "ForgeLens" ? "current" : null },
          h("th", { scope: "row", text: r.signal }),
          h("td", { class: "num", text: `${r.before[0]} of ${r.before[1]}` }),
          h("td", { class: "num", text: `${r.after[0]} of ${r.after[1]}` }),
        ),
      ),
    ),
  );
  return section(
    "s-real",
    `Real statements: false alarms down from ${Math.round(runs[0].rate)}% to ${Math.round(runs.at(-1).rate)}%`,
    `${real.statements} genuine statements from friends and family at ${real.sources_count} banks, examined on the GPU server and deleted by the run. Every flag is a false alarm. Lines show 95% confidence intervals.`,
    h("div", { class: "chart" }, svg),
    h("div", { class: "tbl-wrap" }, t),
    reading("Real bank software builds PDFs in ways the synthetic generator never did: extra weights of one font, standard fonts left unembedded, a new font subset for every page. The rules now allow for what genuine bank software does. The three statements still flagged are two PNB statements made by the same software and one SBI statement printed from Safari; profiles of each bank's genuine statements, now built, are expected to clear them, and that run is next. The text and image arithmetic checks still misread some real layouts, which is why the combined score does not lean on them."),
    source(real.source),
  );
}

// image models ---------------------------------------------------------------

function sectionModels(M) {
  const cell = (v, f) => (v === null || v === undefined ? "–" : f(v));
  const t = h(
    "table",
    { class: "data" },
    h("caption", { class: "visually-hidden", text: M.note }),
    h(
      "thead",
      {},
      h(
        "tr",
        {},
        ["Model", "Trained on", "Caught, AI-inpainted", "Caught, spliced", "Localisation F1", "AIForge-Doc F1", "AIForge-Doc false alarms"].map((c, i) =>
          h("th", { scope: "col", class: i > 1 ? "num" : null, text: c }),
        ),
      ),
    ),
    h(
      "tbody",
      {},
      M.rows.map((r) =>
        h(
          "tr",
          { class: r.current ? "current" : null },
          h("th", { scope: "row" }, r.model, r.current ? h("span", { class: "tag", text: "In use" }) : null, r.note ? h("span", { class: "sub", text: r.note }) : null),
          h("td", { text: r.trained }),
          h("td", { class: "num", text: cell(r.inpaint, pct) }),
          h("td", { class: "num", text: cell(r.splice, pct) }),
          h("td", { class: "num", text: cell(r.f1, fmt2) }),
          h("td", { class: "num", text: cell(r.aiforge, (v) => v.toFixed(3)) }),
          h("td", { class: "num", text: cell(r.aiforge_fa, (v) => `${v}%`) }),
        ),
      ),
    ),
  );
  return section(
    "s-models",
    "From at chance to 99–100% on banks it never saw",
    M.note,
    h("div", { class: "tbl-wrap" }, t),
    reading("The released ADCD-Net, trained on DocTamper, catches none of these forgeries. Fine-tuned on statements from 100 generated banks, ft4 catches 99–100% on ten banks it never saw. ft6, trained further on phone copies, is the model in use. AIForge-Doc, edits by commercial AI tools on receipts and forms, remains the open problem."),
    source(M.source),
  );
}

// reproduction -----------------------------------------------------------------

function sectionReproduction(Rp) {
  const aName = "Published, released ADCD-Net", bName = "ForgeLens image model (ft4)";
  const svg = dumbbell({
    rows: Rp.rows, aKey: "published", bKey: "ours", aName, bName, domain: [0, 1], fmt: (v) => v.toFixed(2),
    label: (r) => r.set,
    rightText: (r) => { const d = r.ours - r.published; return `${d >= 0 ? "+" : "−"}${Math.abs(d).toFixed(3)}`; },
    ariaTitle: "Per-image F1 on the base paper's evaluation sets, published against ForgeLens's image model.",
  });
  return section(
    "s-repro",
    "The base paper, reproduced and kept",
    `${Rp.note} The right-hand column is the difference.`,
    legend([[bName, "var(--series-1)"], [aName, "var(--series-2)"]]),
    h("div", { class: "chart" }, svg),
    numbersTable(Rp.title, ["Set", "Published", "ForgeLens (ft4)"], Rp.rows.map((r) => [r.set, r.published.toFixed(3), r.ours.toFixed(3)])),
    reading("Fine-tuned for bank statements, the image model keeps 95% of the published DocTamper score (0.731 against 0.771 on average) and stays close across the cross-domain sets (0.438 against 0.450), ahead on tampered receipts (T-SROIE), the set most like a statement."),
    source(Rp.source),
  );
}

init();
