(() => {
  const { api, esc, levelKey, fmtDate, toast } = SHMS;
  const $ = (id) => document.getElementById(id);
  const isAdmin = document.body.dataset.role === "admin";
  let page = 1;

  function query(extra = {}) {
    const p = new URLSearchParams();
    const map = { q: "f-q", risk: "f-risk", from: "f-from", to: "f-to" };
    for (const [k, id] of Object.entries(map)) if ($(id).value) p.set(k, $(id).value);
    for (const [k, v] of Object.entries(extra)) p.set(k, v);
    return p.toString();
  }

  async function load() {
    try {
      const d = await api("/api/records?" + query({ page, per_page: 15 }));
      $("recCount").textContent = d.total === 1 ? "1 record matches" : `${d.total} records match`;
      $("exportBtn").href = "/api/export.csv?" + query();
      $("recBody").innerHTML = d.records.length ? d.records.map(row).join("")
        : `<tr><td colspan="${isAdmin ? 10 : 9}" class="empty" style="padding:28px 16px">No records found. Try clearing the filters.</td></tr>`;
      $("pager").innerHTML = `<span>Page ${d.page} of ${d.pages}</span><div>` +
        `<button class="btn btn-ghost btn-small" data-go="${d.page - 1}" ${d.page <= 1 ? "disabled" : ""}>Previous</button>` +
        `<button class="btn btn-ghost btn-small" data-go="${d.page + 1}" ${d.page >= d.pages ? "disabled" : ""}>Next</button></div>`;
    } catch (e) { toast(e.message, "error"); }
  }

  function row(r) {
    return `<tr>
      <td>${fmtDate(r.report_date)}</td>
      <td><strong>${esc(r.village)}</strong>${r.notes ? `<small>${esc(r.notes)}</small>` : ""}</td>
      <td class="num">${r.diarrhea}</td><td class="num">${r.fever}</td>
      <td>${esc(r.rainfall)}</td><td>${esc(r.water_quality)}</td>
      <td class="num">${r.score}</td>
      <td><span class="badge" data-level="${levelKey(r.risk)}">${esc(r.risk)}</span></td>
      <td>${esc(r.reporter || "-")}</td>
      ${isAdmin ? `<td><button class="btn btn-danger" data-del="${r.id}" aria-label="Delete record ${r.id}">Delete</button></td>` : ""}
    </tr>`;
  }

  $("filters").addEventListener("submit", (e) => { e.preventDefault(); page = 1; load(); });
  $("clearFilters").addEventListener("click", () => { $("filters").reset(); page = 1; load(); });
  $("pager").addEventListener("click", (e) => {
    const go = e.target.closest("[data-go]");
    if (go) { page = +go.dataset.go; load(); }
  });
  $("recBody").addEventListener("click", async (e) => {
    const del = e.target.closest("[data-del]");
    if (!del || !confirm("Delete this record? This cannot be undone.")) return;
    try {
      await api("/api/records/" + del.dataset.del, { method: "DELETE" });
      toast("Record deleted", "success");
      load();
    } catch (ex) { toast(ex.message, "error"); }
  });
  load();
})();
