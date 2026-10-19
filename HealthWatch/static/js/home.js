(() => {
  const { api, renderBreakdown, debounce, levelKey, fmtDate } = SHMS;
  const box = document.getElementById("assessor");
  const $ = (id) => document.getElementById(id);

  const read = () => ({
    diarrhea: +$("a-diarrhea").value,
    fever: +$("a-fever").value,
    rainfall: document.querySelector('input[name="a-rain"]:checked').value,
    water_quality: document.querySelector('input[name="a-water"]:checked').value,
  });

  async function update() {
    $("o-diarrhea").textContent = $("a-diarrhea").value;
    $("o-fever").textContent = $("a-fever").value;
    try {
      const r = await api("/api/assess", { method: "POST", body: read() });
      box.dataset.level = levelKey(r.level);
      $("gaugeArc").style.strokeDashoffset = 100 - (r.score / r.max_score) * 100;
      $("gScore").textContent = r.score;
      $("gLevel").textContent = r.level;
      renderBreakdown($("breakdown"), r.breakdown, false);
      $("breakdown").style.setProperty("--lv", `var(--${levelKey(r.level)})`);
      $("advice").textContent = r.advice;
    } catch (e) {
      $("advice").textContent = e.message;
    }
  }
  const slow = debounce(update, 120);
  box.addEventListener("input", slow);
  box.addEventListener("change", slow);
  update();

  api("/api/public/overview").then((o) => {
    $("ov-villages").textContent = o.villages;
    $("ov-alert").textContent = o.on_alert;
    $("ov-reports").textContent = o.reports_7d;
    $("ov-last").textContent = o.last_report ? fmtDate(o.last_report) : "none yet";
  }).catch(() => {});
})();
