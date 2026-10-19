(() => {
  const { api, esc, levelKey, toast, fmtDate } = SHMS;
  const $ = (id) => document.getElementById(id);
  const COLORS = { low: "#2f9e6e", moderate: "#e0a526", high: "#e2692b", critical: "#c8302f", none: "#9aaeb2" };
  const charts = {};
  // show the "no data" message instead of an empty chart
  function emptyState(canvasId, msgId, isEmpty) {
    $(msgId).hidden = !isEmpty;
    $(canvasId).style.visibility = isEmpty ? "hidden" : "visible";
  }

  Chart.defaults.font.family = '"Public Sans", system-ui, sans-serif';
  Chart.defaults.color = "#4c6870";

  async function load() {
    try {
      const [s, alerts] = await Promise.all([api("/api/summary"), api("/api/alerts")]);
      renderTiles(s);
      renderLine(s.series);
      renderDoughnut(s.distribution);
      renderBar(s.villages);
      renderStatus(s.villages);
      renderAlerts(alerts);
      $("stamp").textContent = `Updated ${s.generated_at}.`;
    } catch (e) { toast(e.message, "error"); }
  }

  function renderTiles(s) {
    const st = s.stats;
    $("v-alert").textContent = st.on_alert;
    $("t-alert").dataset.level = st.on_alert ? "critical" : "low";
    $("s-alert").textContent = !st.villages ? "No villages added yet" : st.on_alert ? "Needs action" : "All villages under control";
    $("v-cases").textContent = st.cases_this_week;
    if (st.cases_last_week > 0) {
      const pct = Math.round(((st.cases_this_week - st.cases_last_week) / st.cases_last_week) * 100);
      $("s-cases").textContent = pct === 0 ? "Same as the week before" : `${Math.abs(pct)}% ${pct > 0 ? "more" : "fewer"} than the week before`;
    } else {
      $("s-cases").textContent = "No data for the week before";
    }
    $("v-report").textContent = `${st.reporting} of ${st.villages}`;
    $("s-report").textContent = !st.villages ? "Add villages on the Report cases page" : st.reporting < st.villages ? `${st.villages - st.reporting} yet to report` : "Every village has reported";
    $("v-open").textContent = st.open_alerts;
  }

  function renderLine(series) {
    emptyState("lineChart", "e-line", !(series.diarrhea.some((n) => n) || series.fever.some((n) => n)));
    charts.line?.destroy();
    charts.line = new Chart($("lineChart"), {
      type: "line",
      data: {
        labels: series.labels.map((d) => d.slice(5)),
        datasets: [
          { label: "Diarrhea", data: series.diarrhea, borderColor: "#0f6e7a", backgroundColor: "rgba(15,110,122,.12)", fill: true, tension: .3, pointRadius: 0, borderWidth: 2.5 },
          { label: "Fever", data: series.fever, borderColor: "#e2692b", tension: .3, pointRadius: 0, borderWidth: 2 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
        scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } }, y: { beginAtZero: true, grid: { color: "#e6eeec" } } },
        plugins: { legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } } },
      },
    });
  }

  function renderDoughnut(dist) {
    emptyState("doughnut", "e-dough", !Object.values(dist).some((n) => n));
    charts.doughnut?.destroy();
    const labels = Object.keys(dist);
    charts.doughnut = new Chart($("doughnut"), {
      type: "doughnut",
      data: { labels, datasets: [{ data: labels.map((l) => dist[l]), backgroundColor: labels.map((l) => COLORS[levelKey(l)]), borderColor: "#fff", borderWidth: 3 }] },
      options: { responsive: true, maintainAspectRatio: false, cutout: "62%", plugins: { legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } } } },
    });
  }

  function renderBar(villages) {
    const rows = villages.filter((v) => v.latest).sort((a, b) => b.latest.score - a.latest.score);
    emptyState("barChart", "e-bar", rows.length === 0);
    charts.bar?.destroy();
    charts.bar = new Chart($("barChart"), {
      type: "bar",
      data: {
        labels: rows.map((v) => v.name),
        datasets: [{ data: rows.map((v) => v.latest.score), backgroundColor: rows.map((v) => COLORS[levelKey(v.latest.risk)]), borderRadius: 6 }],
      },
      options: {
        indexAxis: "y", responsive: true, maintainAspectRatio: false,
        scales: { x: { min: 0, max: 11, grid: { color: "#e6eeec" }, title: { display: true, text: "Risk score (0 to 11)" } }, y: { grid: { display: false } } },
        plugins: { legend: { display: false } },
      },
    });
  }

  function renderStatus(villages) {
    const rows = [...villages].sort((a, b) => (b.latest?.score ?? -1) - (a.latest?.score ?? -1));
    if (!rows.length) {
      $("status").innerHTML = '<tr><td colspan="4" class="empty" style="padding:22px 16px">No villages yet. Add one on the <a href="/entry">Report cases</a> page.</td></tr>';
      return;
    }
    $("status").innerHTML = rows.map((v) => {
      const l = v.latest;
      const trend = v.trend === "up" ? '<span class="trend up">Rising</span>'
        : v.trend === "down" ? '<span class="trend down">Falling</span>'
        : v.trend === "flat" ? '<span class="trend flat">Steady</span>' : "-";
      return `<tr><td><strong>${esc(v.name)}</strong><small>${l ? fmtDate(l.date) : "No reports"}</small></td>` +
        `<td class="num">${l ? l.diarrhea : "-"}</td><td>${trend}</td>` +
        `<td>${l ? `<span class="badge" data-level="${levelKey(l.risk)}">${esc(l.risk)}</span>` : '<span class="badge">No data</span>'}</td></tr>`;
    }).join("");
  }

  function renderAlerts(list) {
    const ul = $("alerts");
    if (!list.length) { ul.innerHTML = '<li class="empty">No open alerts. New High and Critical reports will appear here.</li>'; return; }
    ul.innerHTML = list.map((a) => `
      <li data-level="${levelKey(a.level)}">
        <div class="meta"><span class="badge" data-level="${levelKey(a.level)}">${esc(a.level)}</span><time>${esc(a.created_at.slice(0, 16))}</time></div>
        <p>${esc(a.message)}</p>
        <button class="btn btn-ghost btn-small" data-ack="${a.id}">Acknowledge</button>
      </li>`).join("");
  }

  $("alerts").addEventListener("click", async (e) => {
    const b = e.target.closest("[data-ack]");
    if (!b) return;
    b.disabled = true;
    try { await api(`/api/alerts/${b.dataset.ack}/ack`, { method: "POST" }); toast("Alert acknowledged", "success"); load(); }
    catch (ex) { toast(ex.message, "error"); b.disabled = false; }
  });
  $("refresh").addEventListener("click", load);
  load();
  setInterval(load, 60000);
})();
