(function () {
  "use strict";
  const { api, h, number } = window.NT;
  const $ = (id) => document.getElementById(id);

  const METRICS = [
    { key: "ndcg", label: "nDCG@k", higher: true },
    { key: "precision", label: "Precision@k", higher: true },
    { key: "hit_rate", label: "Hit rate@k", higher: true },
    { key: "coverage", label: "Coverage", higher: true, plain: true },
    { key: "diversity", label: "Diversity", higher: true },
    { key: "novelty", label: "Novelty", higher: true, digits: 2 },
    { key: "latency_ms", label: "ms per list", higher: false, plain: true, digits: 1 },
  ];

  function bars(container, entries, color) {
    const max = Math.max(1, ...entries.map((e) => e[1]));
    container.replaceChildren(
      ...entries.map(([label, value]) =>
        h("div", { class: "bar-row" },
          h("span", null, label),
          h("span", { class: "track" }, h("i", { style: "width:" + (100 * value / max) + "%;--c:" + color })),
          h("span", { class: "n" }, value)))
    );
  }

  function renderStats(s) {
    const pct = s.tracks ? Math.round((100 * s.missing_tempo) / s.tracks) : 0;
    const items = [
      [number(s.tracks), "tracks"],
      [number(s.artists), "artists"],
      [number(s.genres), "genre tags"],
      [pct + "%", "without a tempo"],
    ];
    $("stats").replaceChildren(...items.map(([n, l]) => h("div", { class: "stat" }, h("b", null, n), h("span", null, l))));
    bars($("decades"), Object.entries(s.decades), "var(--decade)");
    bars($("moods"), Object.entries(s.moods).sort((a, b) => b[1] - a[1]), "var(--mood)");
  }

  function cell(row, metric, best) {
    const v = row[metric.key];
    if (v === null || v === undefined) return h("td", null, h("span", { class: "muted" }, "n/a"));
    const digits = metric.digits || 3;
    const mean = typeof v === "number" ? v : v.mean;
    const td = h("td", { class: mean === best[metric.key] ? "best" : "" }, mean.toFixed(digits));
    if (typeof v === "object" && v.ci) td.append(h("small", null, "[" + v.ci[0].toFixed(digits) + ", " + v.ci[1].toFixed(digits) + "]"));
    return td;
  }

  function renderTable(report) {
    const rows = report.strategies;
    $("table-wrap").hidden = !rows.length;
    if (!rows.length) return;
    const best = {};
    METRICS.forEach((m) => {
      const values = rows.filter((r) => r.name !== "Random")
        .map((r) => (typeof r[m.key] === "object" && r[m.key] ? r[m.key].mean : r[m.key])).filter((v) => typeof v === "number");
      if (values.length) best[m.key] = m.higher ? Math.max(...values) : Math.min(...values);
    });
    const head = h("thead", null, h("tr", null, h("th", null, "Strategy"), METRICS.map((m) => h("th", null, m.label))));
    const body = h("tbody", null, rows.map((r, i) =>
      h("tr", { class: i === 0 ? "primary" : "" },
        h("td", null, r.name, h("small", null, r.n_scored + " of " + r.n_seeds + " seeds scored")),
        METRICS.map((m) => cell(r, m, best)))));
    $("compare").replaceChildren(head, body);
  }

  function renderGroundTruth(gt) {
    $("gt").replaceChildren(
      h("div", { class: "notice" },
        gt.available
          ? "Reference data: " + number(gt.pairs) + " similar-track pairs from " + gt.source + " covering " + number(gt.seeds_with_reference) + " seed tracks."
          : "No reference data yet, so accuracy columns show n/a. Import Last.fm similar tracks to fill them in (see the README)."));
  }

  async function run() {
    $("e-status").textContent = "Running evaluation. Larger samples take a while.";
    $("run").disabled = true;
    try {
      const report = await api.get("evaluation/", { k: $("e-k").value, sample: $("e-sample").value });
      renderGroundTruth(report.ground_truth);
      renderTable(report);
      $("e-notes").replaceChildren(...report.notes.filter((n) => !n.startsWith("No reference data")).map((n) => h("div", { class: "notice" }, n)));
      $("e-status").textContent = report.sample
        ? "Evaluated " + report.sample + " seed tracks with k = " + report.k + " on " + number(report.catalogue_size) + " tracks."
        : "Nothing to evaluate yet.";
    } catch (err) {
      $("e-status").textContent = "Couldn\u2019t run the evaluation. " + err.message;
    } finally {
      $("run").disabled = false;
    }
  }

  $("run").addEventListener("click", run);
  api.get("stats/").then(renderStats).catch(() => {});
  run();
})();
