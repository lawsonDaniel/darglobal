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
  const KEY = "dg_session", SEEN = "dg_nudge_seen";
  let sid = null;
  try { sid = sessionStorage.getItem(KEY); } catch (e) { /* storage may be blocked */ }

  // ---------- open / close ----------
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
  launcher.addEventListener("click", () => setOpen(!panel.classList.contains("open")));
  $("close").addEventListener("click", () => { setOpen(false); launcher.focus(); });
  document.querySelectorAll("[data-open]").forEach(b => b.addEventListener("click", () => setOpen(true)));
  nudge.addEventListener("click", e => { if (e.target.id === "nudge-x") hideNudge(); else setOpen(true); });
  document.addEventListener("keydown", e => { if (e.key === "Escape" && panel.classList.contains("open")) { setOpen(false); launcher.focus(); } });

  let seen = false;
  try { seen = localStorage.getItem(SEEN) === "1"; } catch (e) {}
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

  // ---------- rendering ----------
  const esc = s => s.replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
  const safeUrl = u => /^https?:\/\/[^\s"'<>]+$/.test(u) ? u : null;
  const link = (u, t) => { const s = safeUrl(u); return s ? `<a href="${s}" target="_blank" rel="noopener noreferrer">${t}</a>` : t; };

  // Escape everything first, then add a few safe formats. URLs only become links if they are http(s).
  function render(text) {
    let h = esc(text);
    h = h.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_, t, u) => link(u.replace(/&amp;/g, "&"), t));
    h = h.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, (_, p, u) => {
      const trail = (u.match(/[.,;:!?]+$/) || [""])[0];
      const clean = u.slice(0, u.length - trail.length);
      return p + link(clean.replace(/&amp;/g, "&"), clean) + trail;
    });
    h = h.replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>");
    h = h.replace(/^#{1,4}\s+(.+)$/gm, "<b>$1</b>");
    h = h.replace(/^\s*[-*]\s+/gm, "• ");
    h = h.replace(/_Note: ([^_]+)_/g, "<i>Note: $1</i>");
    return h;
  }

  function add(role, html, extra) {
    const row = document.createElement("div");
    row.className = "row " + role;
    if (role === "bot") {
      const a = document.createElement("span");
      a.className = "mini"; a.textContent = "DG";
      row.appendChild(a);
    }
    const d = document.createElement("div");
    d.className = "msg " + role;
    d.dir = "auto";
    d.innerHTML = html;
    if (extra) d.appendChild(extra);
    row.appendChild(d);
    inner.appendChild(row);
    log.scrollTop = log.scrollHeight;
    return row;
  }

  function footerFor(j) {
    const box = document.createElement("div");
    if (j.sources && j.sources.length) {
      const s = document.createElement("div");
      s.className = "sources";
      s.innerHTML = "Sources: " + j.sources.map(u => link(u, esc(u.replace(/^https?:\/\//, "").slice(0, 48)))).join("");
      box.appendChild(s);
    }
    if (j.checks && j.checks.revised) {
      const meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent = "Figures re-checked against the data";
      box.appendChild(meta);
    }
    return box.childNodes.length ? box : null;
  }

  // ---------- composer ----------
  function grow() { q.style.height = "auto"; q.style.height = Math.min(q.scrollHeight, 120) + "px"; }
  q.addEventListener("input", grow);

  async function ask() {
    const text = q.value.trim();
    if (!text || send.disabled) return;
    q.value = ""; grow();
    chips.hidden = true;
    add("user", esc(text));
    send.disabled = true;
    const wait = add("bot", '<span class="typing" aria-label="Typing"><i></i><i></i><i></i></span>');
    try {
      const r = await fetch("/api/chat", {method: "POST", headers: {"Content-Type": "application/json"},
                                          body: JSON.stringify({message: text, session_id: sid})});
      const j = await r.json().catch(() => ({}));
      wait.remove();
      if (j.session_id) { sid = j.session_id; try { sessionStorage.setItem(KEY, sid); } catch (e) {} }
      if (!r.ok) { add("bot", esc(j.error || "Something went wrong.")); return; }
      add("bot", render(j.reply || ""), footerFor(j));
    } catch (e) {
      wait.remove();
      add("bot", "Network error, please try again.");
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
