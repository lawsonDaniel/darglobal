"use strict";
(() => {
  const examples = [
    "Which DarGlobal projects are in Oman?",
    "Villas in Riyadh under 2M SAR with 5+ bedrooms",
    "Compare median villa prices across cities",
    "How can I contact DarGlobal?",
    "فلل للبيع في الخبر بأقل من مليون ونصف",
  ];
  const $ = id => document.getElementById(id);
  const panel = $("panel"), launcher = $("launcher"), nudge = $("nudge");
  const log = $("log"), inner = $("inner"), chips = $("chips");
  const q = $("q"), send = $("send");
  const KEY = "dg_session", SEEN = "dg_nudge_seen", WIDE = "dg_wide";
  let sid = null;
  try { sid = sessionStorage.getItem(KEY); } catch (e) { /* storage may be blocked */ }
  const remember = id => { sid = id; try { sessionStorage.setItem(KEY, id); } catch (e) {} };

  // ---------- open / close / expand ----------
  function setOpen(open) {
    panel.classList.toggle("open", open);
    panel.setAttribute("aria-hidden", String(!open));
    launcher.setAttribute("aria-expanded", String(open));
    launcher.setAttribute("aria-label", open ? "Close chat" : "Open chat");
    document.body.classList.toggle("chat-open", open);
    if (open) { hideNudge(); setTimeout(() => q.focus(), 150); }
  }
  function hideNudge() {
    nudge.hidden = true;
    try { localStorage.setItem(SEEN, "1"); } catch (e) {}
  }
  function setWide(wide) {
    panel.classList.toggle("wide", wide);
    $("expand").setAttribute("aria-label", wide ? "Shrink chat" : "Expand chat");
    $("expand").title = wide ? "Shrink" : "Expand";
    try { localStorage.setItem(WIDE, wide ? "1" : "0"); } catch (e) {}
  }
  launcher.addEventListener("click", () => setOpen(!panel.classList.contains("open")));
  $("close").addEventListener("click", () => { setOpen(false); launcher.focus(); });
  $("expand").addEventListener("click", () => setWide(!panel.classList.contains("wide")));
  document.querySelectorAll("[data-open]").forEach(b => b.addEventListener("click", () => setOpen(true)));
  nudge.addEventListener("click", e => { if (e.target.id === "nudge-x") hideNudge(); else setOpen(true); });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && panel.classList.contains("open")) { setOpen(false); launcher.focus(); } });

  let seen = false;
  try { seen = localStorage.getItem(SEEN) === "1"; if (localStorage.getItem(WIDE) === "1") setWide(true); } catch (e) {}
  if (!seen) setTimeout(() => { if (!panel.classList.contains("open")) nudge.hidden = false; }, 2500);

  // ---------- quick replies ----------
  for (const e of examples) {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = e; b.dir = "auto";
    b.addEventListener("click", () => { q.value = e; ask(); });
    chips.appendChild(b);
  }
  fetch("/api/health").then(r => r.json()).then(h => {
    $("stats").textContent = `${h.projects} DarGlobal projects · ${h.villas} Wasalt villa listings`;
  }).catch(() => {});

  // ---------- Markdown (escape first, then a safe subset: headings, lists, tables, quotes, code) ----------
  const esc = s => s.replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const safeUrl = u => /^https?:\/\/[^\s"'<>]+$/.test(u) ? u : null;
  const link = (u, t) => { const s = safeUrl(u); return s ? `<a href="${s}" target="_blank" rel="noopener noreferrer">${t}</a>` : t; };

  function inline(raw) {
    const keep = [];
    const hold = html => { keep.push(html); return `\u0000${keep.length - 1}\u0000`; };
    let h = esc(raw);
    h = h.replace(/`([^`\n]+)`/g, (_, c) => hold(`<code>${c}</code>`));
    h = h.replace(/\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g, (_, t, u) => hold(link(u.replace(/&amp;/g, "&"), t)));
    h = h.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, (_, p, u) => {
      const trail = (u.match(/[.,;:!?]+$/) || [""])[0];
      const clean = u.slice(0, u.length - trail.length);
      const label = clean.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "");
      return p + hold(link(clean.replace(/&amp;/g, "&"), label.length > 42 ? label.slice(0, 40) + "…" : label)) + trail;
    });
    h = h.replace(/\*\*(?=\S)([^*\n]*?\S)\*\*/g, "<strong>$1</strong>");
    h = h.replace(/__(?=\S)([^_\n]*?\S)__/g, "<strong>$1</strong>");
    h = h.replace(/(^|[^*\w])\*(?=\S)([^*\n]*?\S)\*(?!\*)/g, "$1<em>$2</em>");
    h = h.replace(/(^|[^\w])_(?=\S)([^_\n]*?\S)_(?!\w)/g, "$1<em>$2</em>");
    h = h.replace(/~~(?=\S)([^~\n]*?\S)~~/g, "<del>$1</del>");
    return h.replace(/\u0000(\d+)\u0000/g, (_, i) => keep[+i]);
  }

  const cells = line => {
    let s = line.trim();
    if (s.startsWith("|")) s = s.slice(1);
    if (s.endsWith("|") && !s.endsWith("\\|")) s = s.slice(0, -1);
    return s.split(/(?<!\\)\|/).map(c => c.trim().replace(/\\\|/g, "|"));
  };
  const SEP = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;
  const UL = /^(\s*)[-*•+]\s+(.*)$/, OL = /^(\s*)(\d+)[.)]\s+(.*)$/;

  function table(head, align, rows) {
    const cell = (tag, c, i) => `<${tag}${align[i] ? ` class="${align[i]}"` : ""} dir="auto">${inline(c)}</${tag}>`;
    const width = Math.max(head.length, ...rows.map(r => r.length));
    const pad = r => r.concat(Array(Math.max(0, width - r.length)).fill(""));
    return `<div class="tbl"><table><thead><tr>${pad(head).map((c, i) => cell("th", c, i)).join("")}</tr></thead><tbody>` +
      rows.map(r => `<tr>${pad(r).map((c, i) => cell("td", c, i)).join("")}</tr>`).join("") + "</tbody></table></div>";
  }

  function md(text) {
    const lines = text.replace(/\r/g, "").split("\n");
    const out = [];
    let para = [], i = 0;
    const flush = () => { if (para.length) { out.push(`<p dir="auto">${para.map(inline).join("<br>")}</p>`); para = []; } };
    while (i < lines.length) {
      const l = lines[i];
      if (!l.trim()) { flush(); i++; continue; }
      if (l.includes("|") && i + 1 < lines.length && SEP.test(lines[i + 1])) {        // table
        flush();
        const head = cells(l);
        const align = cells(lines[i + 1]).map(c => c.endsWith(":") ? (c.startsWith(":") ? "c" : "r") : "");
        const rows = [];
        i += 2;
        while (i < lines.length && lines[i].includes("|") && lines[i].trim()) rows.push(cells(lines[i++]));
        out.push(table(head, align, rows));
        continue;
      }
      let m;
      if ((m = l.match(/^\s*(#{1,6})\s+(.*?)\s*#*\s*$/))) {                             // heading
        flush();
        const tag = m[1].length <= 2 ? "h3" : "h4";
        out.push(`<${tag} dir="auto">${inline(m[2])}</${tag}>`);
        i++; continue;
      }
      if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(l)) { flush(); out.push("<hr>"); i++; continue; }   // rule
      if (/^\s*>/.test(l)) {                                                            // quote
        flush();
        const body = [];
        while (i < lines.length && /^\s*>/.test(lines[i])) body.push(lines[i++].replace(/^\s*>\s?/, ""));
        out.push(`<blockquote>${md(body.join("\n"))}</blockquote>`);
        continue;
      }
      if (UL.test(l) || OL.test(l)) {                                                   // list (one nesting level)
        flush();
        const ordered = OL.test(l) && !UL.test(l);
        const start = ordered ? +l.match(OL)[2] : 1;
        const items = [];
        const base = (l.match(/^\s*/) || [""])[0].length;
        while (i < lines.length && lines[i].trim()) {
          const s = lines[i], ind = (s.match(/^\s*/) || [""])[0].length;
          const mu = s.match(UL), mo = s.match(OL);
          if ((mu || mo) && ind <= base + 1 && (ordered ? !mo || mu : !mu)) break;  // list type changed
          if ((mu || mo) && ind <= base + 1) items.push({text: mu ? mu[2] : mo[3], sub: []});
          else if ((mu || mo) && items.length) items[items.length - 1].sub.push(mu ? mu[2] : mo[3]);
          else if (items.length && ind > base) items[items.length - 1].text += "\n" + s.trim();
          else break;
          i++;
        }
        const li = it => `<li dir="auto">${it.text.split("\n").map(inline).join("<br>")}` +
          (it.sub.length ? `<ul>${it.sub.map(s => `<li dir="auto">${inline(s)}</li>`).join("")}</ul>` : "") + "</li>";
        out.push(ordered ? `<ol${start !== 1 ? ` start="${start}"` : ""}>${items.map(li).join("")}</ol>` : `<ul>${items.map(li).join("")}</ul>`);
        continue;
      }
      para.push(l.trim());
      i++;
    }
    flush();
    return out.join("");
  }

  // ---------- messages ----------
  const nearBottom = () => log.scrollHeight - log.scrollTop - log.clientHeight < 80;
  const toBottom = () => { log.scrollTop = log.scrollHeight; };

  function row(role) {
    const r = document.createElement("div");
    r.className = "row " + role;
    if (role === "bot") {
      const a = document.createElement("span");
      a.className = "mini"; a.textContent = "DG";
      r.appendChild(a);
    }
    const d = document.createElement("div");
    d.className = "msg " + role;
    d.dir = "auto";
    r.appendChild(d);
    inner.appendChild(r);
    toBottom();
    return d;
  }
  function addUser(text) { row("user").textContent = text; }
  function addBot(html) { const d = row("bot"); d.innerHTML = html; return d; }

  function typing(d, note) {
    d.classList.add("pending");
    d.innerHTML = '<span class="typing" aria-hidden="true"><i></i><i></i><i></i></span>' +
      (note ? `<span class="status">${esc(note)}…</span>` : "");
  }

  function footerFor(j) {
    const box = document.createElement("div");
    box.className = "foot";
    if (j.sources && j.sources.length) {
      const det = document.createElement("details");
      det.className = "sources";
      const label = j.sources.length === 1 ? "1 source" : `${j.sources.length} sources`;
      det.innerHTML = `<summary>${label}</summary><div>` + j.sources.map(u => {
        const short = u.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "");
        const a = link(u, esc(short));
        return a.replace("<a ", `<a title="${esc(u)}" `);
      }).join("") + "</div>";
      box.appendChild(det);
    }
    if (j.checks && j.checks.revised) {
      const meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent = "Figures re-checked against the data";
      box.appendChild(meta);
    }
    return box.childNodes.length ? box : null;
  }

  function showFinal(d, j) {
    d.classList.remove("pending", "streaming");
    d.innerHTML = md(j.reply || "");
    const f = footerFor(j);
    if (f) d.appendChild(f);
  }

  // ---------- streaming ----------
  async function readStream(r, d) {
    const reader = r.body.getReader(), dec = new TextDecoder();
    let buf = "", done = false, note = "Thinking";
    const handle = (event, data) => {
      const stick = nearBottom();
      if (event === "start") { if (data.session_id) remember(data.session_id); }
      else if (event === "status") {
        note = data.text;
        if (d.classList.contains("pending")) typing(d, note);
      } else if (event === "draft") {
        if (!data.text) { typing(d, note); }
        else {
          d.classList.remove("pending"); d.classList.add("streaming");
          d.innerHTML = md(data.text);
        }
      } else if (event === "done") { done = true; if (data.session_id) remember(data.session_id); showFinal(d, data); }
      else if (event === "error") { done = true; d.classList.remove("pending", "streaming"); d.textContent = data.error || "Something went wrong."; }
      if (stick) toBottom();
    };
    for (;;) {
      const {value, done: end} = await reader.read();
      if (value) buf += dec.decode(value, {stream: true});
      let k;
      while ((k = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, k); buf = buf.slice(k + 2);
        let event = "message", data = "";
        for (const line of block.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) data += line.slice(5).trim();
        }
        try { handle(event, JSON.parse(data || "{}")); } catch (e) { /* ignore a malformed event */ }
      }
      if (end) break;
    }
    if (!done) throw new Error("stream ended early");
  }

  // ---------- composer ----------
  function grow() { q.style.height = "auto"; q.style.height = Math.min(q.scrollHeight, 120) + "px"; }
  q.addEventListener("input", grow);

  async function ask() {
    const text = q.value.trim();
    if (!text || send.disabled) return;
    q.value = ""; grow();
    chips.hidden = true;
    addUser(text);
    send.disabled = true;
    const d = row("bot");
    typing(d, "Thinking");
    try {
      const r = await fetch("/api/chat/stream", {method: "POST", headers: {"Content-Type": "application/json", "Accept": "text/event-stream"},
                                                 body: JSON.stringify({message: text, session_id: sid})});
      if ((r.headers.get("content-type") || "").includes("text/event-stream") && r.body) {
        await readStream(r, d);
      } else {
        const j = await r.json().catch(() => ({}));
        if (j.session_id) remember(j.session_id);
        if (r.ok) showFinal(d, j);
        else { d.classList.remove("pending"); d.textContent = j.error || "Something went wrong."; }
      }
    } catch (e) {
      d.classList.remove("pending", "streaming");
      d.textContent = "Network error, please try again.";
    } finally {
      send.disabled = false;
      q.focus();
    }
  }

  $("f").addEventListener("submit", e => { e.preventDefault(); ask(); });
  q.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } });
  $("new").addEventListener("click", () => {
    if (sid) { fetch("/api/reset", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({session_id: sid})}).catch(() => {}); }
    sid = null;
    try { sessionStorage.removeItem(KEY); } catch (e) {}
    inner.querySelectorAll(".row:not(.welcome)").forEach(m => m.remove());
    chips.hidden = false;
    q.focus();
  });
})();
