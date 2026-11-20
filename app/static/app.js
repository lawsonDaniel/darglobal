"use strict";
(() => {
  const examples = [
    "Which DarGlobal projects are in Oman?",
    "DarGlobal projects with golf access, completing by 2028",
    "Villas in Riyadh under 2 million SAR with at least 5 bedrooms",
    "Compare median villa prices across Saudi cities",
    "How can I contact DarGlobal?",
    "What is DarGlobal's latest news?",
    "فلل للبيع في الخبر بأقل من مليون ونصف",
  ];
  const log = document.getElementById("log"), inner = document.getElementById("inner");
  const q = document.getElementById("q"), send = document.getElementById("send");
  const KEY = "dg_session";
  let sid = null;
  try { sid = sessionStorage.getItem(KEY); } catch (e) { /* storage may be blocked */ }

  for (const e of examples) {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = e;
    b.addEventListener("click", () => { q.value = e; ask(); });
    document.getElementById("chips").appendChild(b);
  }
  fetch("/api/health").then(r => r.json()).then(h => {
    document.getElementById("stats").textContent = `${h.projects} DarGlobal projects · ${h.villas} Wasalt villa listings`;
  }).catch(() => {});

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
    const d = document.createElement("div");
    d.className = "msg " + role;
    d.dir = "auto";
    d.innerHTML = html;
    if (extra) d.appendChild(extra);
    inner.appendChild(d);
    log.scrollTop = log.scrollHeight;
    return d;
  }

  function footerFor(j) {
    const box = document.createElement("div");
    if (j.sources && j.sources.length) {
      const s = document.createElement("div");
      s.className = "sources";
      s.innerHTML = "Sources: " + j.sources.map(u => link(u, esc(u.replace(/^https?:\/\//, "").slice(0, 60)))).join("");
      box.appendChild(s);
    }
    const meta = document.createElement("div");
    meta.className = "meta";
    const bits = [j.model, j.tools_used && j.tools_used.length ? "tools: " + [...new Set(j.tools_used)].join(", ") : null,
                  j.checks && j.checks.revised ? "figures re-checked" : null];
    meta.textContent = bits.filter(Boolean).join(" · ");
    box.appendChild(meta);
    return box;
  }

  async function ask() {
    const text = q.value.trim();
    if (!text || send.disabled) return;
    q.value = "";
    add("user", esc(text));
    send.disabled = true;
    const wait = add("bot", '<span class="dots">Looking it up</span>');
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

  document.getElementById("f").addEventListener("submit", e => { e.preventDefault(); ask(); });
  q.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } });
  document.getElementById("new").addEventListener("click", async () => {
    if (sid) { fetch("/api/reset", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({session_id: sid})}).catch(() => {}); }
    sid = null;
    try { sessionStorage.removeItem(KEY); } catch (e) {}
    inner.querySelectorAll(".msg").forEach(m => m.remove());
  });
})();
