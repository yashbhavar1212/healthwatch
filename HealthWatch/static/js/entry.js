(() => {
  const { api, toast, debounce, levelKey, renderBreakdown, esc, fmtDate } = SHMS;
  const $ = (id) => document.getElementById(id);
  const form = $("entryForm");
  const isAdmin = document.body.dataset.role === "admin";
  let villages = [];

  $("reportDate").value = new Date().toLocaleDateString("en-CA");
  $("reportDate").max = $("reportDate").value;

  async function loadVillages(selectId) {
    const keep = selectId || $("village").value;
    villages = await api("/api/villages");
    const has = villages.length > 0;
    $("entryFields").disabled = !has;
    $("noVillage").hidden = has;
    $("village").innerHTML = (has ? '<option value="">Choose a village</option>' : '<option value="">No villages yet</option>') +
      villages.map((v) => `<option value="${v.id}">${esc(v.name)}</option>`).join("");
    if (keep && villages.some((v) => String(v.id) === String(keep))) $("village").value = keep;
    $("villageCount").textContent = has ? `(${villages.length})` : "";
    $("villageBody").innerHTML = has ? villages.map(villageRow).join("")
      : '<tr><td colspan="3" class="empty" style="padding:18px 16px">No villages added yet. Use the form above to add the first one.</td></tr>';
    showVillageInfo();
  }

  function villageRow(v) {
    const sub = [v.district, v.population ? v.population.toLocaleString("en-IN") + " people" : ""].filter(Boolean).join(", ");
    return `<tr>
      <td><strong>${esc(v.name)}</strong>${sub ? `<small>${esc(sub)}</small>` : ""}</td>
      <td class="num">${v.reports}${v.last_report ? `<small>last ${fmtDate(v.last_report)}</small>` : ""}</td>
      <td><div class="row-actions">
        <button class="btn btn-ghost btn-small" type="button" data-report="${v.id}">Report</button>
        ${isAdmin ? `<button class="btn btn-danger" type="button" data-del="${v.id}" data-name="${esc(v.name)}" data-count="${v.reports}">Delete</button>` : ""}
      </div></td></tr>`;
  }

  function showVillageInfo() {
    const v = villages.find((x) => String(x.id) === $("village").value);
    $("villageInfo").textContent = v
      ? [v.district || "District not set", v.population ? "population " + v.population.toLocaleString("en-IN") : ""].filter(Boolean).join(", ")
      : "";
  }

  const values = () => ({
    village_id: $("village").value,
    diarrhea: $("diarrhea").value,
    fever: $("fever").value,
    rainfall: document.querySelector('input[name="rain"]:checked').value,
    water_quality: document.querySelector('input[name="water"]:checked').value,
    report_date: $("reportDate").value,
    notes: $("notes").value,
  });

  const preview = debounce(async () => {
    const v = values();
    const box = $("preview");
    if (v.diarrhea === "" || v.fever === "") {
      box.dataset.level = "none";
      $("pvLevel").textContent = "Waiting for numbers";
      $("pvScore").textContent = "";
      return;
    }
    try {
      const r = await api("/api/assess", { method: "POST", body: v });
      box.dataset.level = levelKey(r.level);
      $("pvLevel").textContent = r.level;
      $("pvScore").textContent = `Score ${r.score} of ${r.max_score}`;
    } catch (e) {
      $("pvLevel").textContent = "Check the numbers";
      $("pvScore").textContent = e.message;
    }
  }, 300);

  form.addEventListener("input", preview);
  form.addEventListener("change", () => { preview(); showVillageInfo(); });

  // step 1: add a village
  $("villageForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = $("villageError");
    err.hidden = true;
    $("villageBtn").disabled = true;
    try {
      const r = await api("/api/villages", { method: "POST", body: {
        name: $("vName").value, district: $("vDistrict").value, population: $("vPop").value || 0,
      } });
      toast(`${r.name} added. You can report cases for it now.`, "success");
      e.target.reset();
      await loadVillages(String(r.id));
    } catch (ex) {
      err.textContent = ex.message;
      err.hidden = false;
    } finally { $("villageBtn").disabled = false; }
  });

  // village list actions
  $("villageBody").addEventListener("click", async (e) => {
    const rep = e.target.closest("[data-report]");
    if (rep) {
      $("village").value = rep.dataset.report;
      showVillageInfo();
      form.scrollIntoView({ behavior: "smooth", block: "start" });
      $("diarrhea").focus({ preventScroll: true });
      return;
    }
    const del = e.target.closest("[data-del]");
    if (!del) return;
    const n = +del.dataset.count;
    const msg = `Delete ${del.dataset.name}?` + (n ? ` Its ${n} report${n === 1 ? "" : "s"} will be deleted too.` : "") + " This cannot be undone.";
    if (!confirm(msg)) return;
    try {
      const r = await api("/api/villages/" + del.dataset.del, { method: "DELETE" });
      toast(`${r.name} deleted`, "success");
      $("result").hidden = true;
      await loadVillages();
    } catch (ex) { toast(ex.message, "error"); }
  });

  // step 2: save a report
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = $("entryError");
    err.hidden = true;
    const v = values();
    if (!v.village_id) return fail("Choose a village.");
    if (v.diarrhea === "" || v.fever === "") return fail("Enter both diarrhea and fever counts. Use 0 if there are none.");
    $("entryBtn").disabled = true;
    try {
      const res = await api("/api/records", { method: "POST", body: v });
      const a = res.assessment;
      const box = $("result");
      box.hidden = false;
      box.dataset.level = levelKey(a.level);
      $("rsBadge").dataset.level = levelKey(a.level);
      $("rsBadge").textContent = `${a.level} risk`;
      $("rsText").textContent = `${res.village}: score ${a.score} of ${a.max_score}.` +
        (a.rising ? " Cases are rising since the last report." : "");
      renderBreakdown($("rsBreakdown"), a.breakdown);
      $("rsBreakdown").style.setProperty("--lv", `var(--${levelKey(a.level)})`);
      $("rsAdvice").textContent = a.advice;
      $("rsAdvice").style.setProperty("--lv", `var(--${levelKey(a.level)})`);
      toast(`Report saved for ${res.village}`, "success");
      $("diarrhea").value = "";
      $("fever").value = "";
      $("notes").value = "";
      preview();
      loadVillages().catch(() => {});
      box.scrollIntoView({ behavior: "smooth", block: "nearest" });
    } catch (ex) {
      fail(ex.message);
    } finally {
      $("entryBtn").disabled = false;
    }
    function fail(msg) { err.textContent = msg; err.hidden = false; }
  });

  loadVillages().catch((ex) => toast(ex.message, "error"));
})();
