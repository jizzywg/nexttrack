(function () {
  "use strict";
  const { api, h } = NT;
  const $ = (id) => document.getElementById(id);
  const discoverUrl = document.body.dataset.discover || "/discover/";
  const compact = new Intl.NumberFormat("en-GB", { notation: "compact", maximumFractionDigits: 1 });

  const WALL_COLUMNS = 9;
  const TILES_PER_COLUMN = 6;

  function uniqueByArtist(tracks) {
    const seen = new Set();
    return tracks.filter((t) => (seen.has(t.artist) ? false : (seen.add(t.artist), true)));
  }

  function buildWall(tracks) {
    const wall = $("lp-wall");
    const photos = uniqueByArtist(tracks.filter((t) => t.artist_image));
    const pool = photos.length >= 8 ? photos : tracks;
    if (!pool.length) return;
    const columns = [];
    for (let c = 0; c < WALL_COLUMNS; c++) {
      const items = [];
      for (let r = 0; r < TILES_PER_COLUMN; r++) items.push(pool[(c * TILES_PER_COLUMN + r) % pool.length]);
      const col = h("div", { class: "lp-col" });
      items.concat(items).forEach((t) => col.append(h("div", { class: "lp-tile" }, NT.sleeve(t))));
      columns.push(col);
    }
    wall.replaceChildren(...columns);
    requestAnimationFrame(() => wall.classList.add("ready"));
  }

  function fallbackWall() {
    const genres = ["pop", "hip hop", "jazz", "rock", "disco", "soul", "electronic", "folk", "r&b", "metal"];
    const moods = ["euphoric", "energetic", "chill", "dark", "melancholic"];
    buildWall(genres.flatMap((g, i) => moods.map((m, j) => ({ title: g + i + j, artist: m + j, genres: [{ name: g }], mood: m }))));
  }

  let candidates = [];
  let current = -1;
  let ticket = 0;

  const isComplete = (t) => t.artist_image && t.tempo && t.mood && t.year && t.genres && t.genres.length;

  function facts(t) {
    return [
      t.year,
      t.tempo ? Math.round(t.tempo) + " BPM" : null,
      t.mood,
      t.genres && t.genres[0] ? t.genres[0].name : null,
    ].filter(Boolean).map(String);
  }

  function renderSeed(t) {
    $("lp-seed").replaceChildren(
      NT.sleeve(t, 0, { artist: true }),
      h("p", { class: "lp-seed-label" }, "Starting from"),
      h("p", { class: "lp-seed-title" }, t.title),
      h("p", { class: "lp-seed-artist" }, t.artist),
      h("p", { class: "lp-facts" }, facts(t).map((f) => h("span", null, f))));
  }

  function barLabel(r) {
    return "Score built from " + NT.FEATURES
      .map((f) => f.label.toLowerCase() + " " + Math.round((r.contributions[f.key] || 0) * 100) + " points")
      .join(", ");
  }

  function renderMatch(r) {
    const t = r.track;
    const segments = NT.FEATURES.map((f) => {
      const v = r.contributions[f.key] || 0;
      return v > 0 ? h("span", { style: "width:" + (v * 100).toFixed(1) + "%;background:" + f.color }) : null;
    });
    return h("li", { class: "lp-match" },
      NT.sleeve(t, 64, { artist: true }),
      h("div", { class: "lp-match-main" },
        h("p", { class: "lp-match-title" }, t.title),
        h("p", { class: "lp-match-artist" }, t.artist),
        h("div", { class: "lp-bar", role: "img", "aria-label": barLabel(r) }, segments),
        h("p", { class: "lp-reason" }, r.reasons && r.reasons.length ? r.reasons.join(". ") + "." : "Loosely similar overall.")),
      h("p", { class: "lp-score" }, String(r.match), h("span", null, "%")));
  }

  function demoMessage(text) {
    $("lp-matches").replaceChildren(h("li", { class: "lp-note" }, text));
    $("lp-another").hidden = true;
  }

  async function showMatch() {
    if (!candidates.length) return;
    let i = Math.floor(Math.random() * candidates.length);
    if (candidates.length > 1 && i === current) i = (i + 1) % candidates.length;
    current = i;
    const seed = candidates[i];
    const mine = ++ticket;
    const list = $("lp-matches");
    renderSeed(seed);
    $("lp-open").href = discoverUrl + "?seeds=" + seed.id;
    list.classList.add("is-loading");
    list.setAttribute("aria-busy", "true");
    try {
      const data = await api.post("recommendations/", { seeds: [seed.id], k: 3, max_per_artist: 1 });
      if (mine !== ticket) return;
      list.replaceChildren(...data.results.map(renderMatch));
    } catch (err) {
      if (mine !== ticket) return;
      list.replaceChildren(h("li", { class: "lp-note" }, "Couldn\u2019t score a match. " + err.message));
    } finally {
      if (mine === ticket) {
        list.classList.remove("is-loading");
        list.removeAttribute("aria-busy");
      }
    }
  }

  function renderChart(tracks) {
    const top = uniqueByArtist(tracks.filter((t) => t.listeners > 0)).slice(0, 10);
    if (top.length < 3) {
      $("lp-chart-section").hidden = true;
      return;
    }
    $("lp-chart").replaceChildren(...top.map((t, i) =>
      h("li", null,
        h("a", { class: "lp-chart-row", href: discoverUrl + "?seeds=" + t.id, "aria-label": "Number " + (i + 1) + ": " + t.title + " by " + t.artist + ". Find songs like it." },
          h("span", { class: "lp-rank" }, String(i + 1)),
          NT.sleeve(t, 56),
          h("span", { class: "lp-chart-main" },
            h("span", { class: "lp-chart-title" }, t.title),
            h("span", { class: "lp-chart-artist" }, t.artist)),
          h("span", { class: "lp-listeners" }, compact.format(t.listeners) + " listeners")))));
  }

  async function init() {
    $("lp-another").addEventListener("click", showMatch);

    api.get("stats/").then((s) => {
      if (s && s.tracks) {
        $("lp-count").textContent = "Recommending from " + s.tracks.toLocaleString("en-GB") +
          " songs by " + s.artists.toLocaleString("en-GB") + " artists.";
      }
    }).catch(() => {});

    try {
      const [random, popular] = await Promise.all([
        api.get("tracks/", { ordering: "random", page_size: 100 }),
        api.get("tracks/", { ordering: "-listeners", page_size: 40 }),
      ]);
      if (!random.results.length) {
        fallbackWall();
        demoMessage("The catalogue is empty. Run python manage.py seed_demo, then reload.");
        $("lp-chart-section").hidden = true;
        return;
      }
      buildWall(random.results);
      candidates = random.results.filter(isComplete);
      if (!candidates.length) candidates = random.results.filter((t) => t.genres && t.genres.length);
      if (!candidates.length) candidates = random.results;
      showMatch();
      renderChart(popular.results);
    } catch (err) {
      fallbackWall();
      demoMessage("Couldn\u2019t reach the catalogue. " + err.message);
      $("lp-chart-section").hidden = true;
    }
  }

  init();
})();
