/* Shared helpers: API wrapper, escaping, toasts, nav. */
const SHMS = (() => {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";

  async function api(path, { method = "GET", body } = {}) {
    const opts = { method, headers: {}, credentials: "same-origin" };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    if (method !== "GET") opts.headers["X-CSRF-Token"] = csrf;
    let res;
    try {
      res = await fetch(path, opts);
    } catch {
      throw new Error("Cannot reach the server. Check the connection and try again.");
    }
    let data = null;
    try { data = await res.json(); } catch { /* not JSON */ }
    if (res.status === 401 && !path.endsWith("/login")) {
      location.href = "/login?next=" + encodeURIComponent(location.pathname);
      throw new Error("Please sign in again.");
    }
    if (!res.ok) throw new Error(data?.error || `Request failed (${res.status}).`);
    return data;
  }

  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const levelKey = (level) => (level ? String(level).toLowerCase() : "none");

  function toast(message, type = "info") {
    const box = document.getElementById("toasts");
    const el = document.createElement("div");
    el.className = "toast " + type;
    el.textContent = message;
    box.appendChild(el);
    setTimeout(() => el.remove(), 4200);
  }

  function fmtDate(iso) {
    if (!iso) return "-";
    const d = new Date(iso + "T00:00:00");
    return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  }

  const BREAKDOWN_LABELS = {
    diarrhea: ["Diarrhea cases", 4], fever: ["Fever cases", 2], rainfall: ["Rainfall", 2],
    water: ["Drinking water", 2], trend: ["Rising trend", 1],
  };

  function renderBreakdown(el, breakdown, includeTrend = true) {
    el.innerHTML = Object.entries(BREAKDOWN_LABELS)
      .filter(([k]) => includeTrend || k !== "trend")
      .map(([k, [label, max]]) => {
        const pts = breakdown[k] ?? 0;
        return `<li><span>${label}</span><span class="pts">${pts} of ${max}</span>` +
               `<span class="bar-bg"><i style="width:${(pts / max) * 100}%"></i></span></li>`;
      }).join("");
  }

  function debounce(fn, ms = 250) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
  }

  // nav
  const toggle = document.getElementById("navToggle");
  toggle?.addEventListener("click", () => {
    const open = document.getElementById("nav").classList.toggle("open");
    toggle.setAttribute("aria-expanded", open);
  });
  document.getElementById("logout")?.addEventListener("click", async () => {
    try { await api("/api/logout", { method: "POST" }); } finally { location.href = "/"; }
  });

  return { api, esc, levelKey, toast, fmtDate, renderBreakdown, debounce };
})();
