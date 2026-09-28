(function () {
  "use strict";
  const { api, h, sleeve, debounce, trackFacts, number, listenAttrs } = window.NT;
  const $ = (id) => document.getElementById(id);
  const PAGE_SIZE = 30;
  const state = { page: 1, total: 0, loaded: 0, ticket: 0 };

  function selectGenre(name) {
    $("f-genre").value = name;
    $("library-message").textContent = "";
    load(true);
    $("f-genre").focus();
  }

  function addToDiscover(track) {
    let saved;
    try { saved = JSON.parse(localStorage.getItem("nexttrack:queue") || "null"); } catch (e) { saved = null; }
    const mode = saved && saved.mode === "radio" ? "radio" : "blend";
    const ids = saved && Array.isArray(saved.ids)
      ? saved.ids.filter((id) => Number.isInteger(id) && id > 0).slice(mode === "radio" ? -50 : 0, mode === "radio" ? undefined : 5)
      : [];
    if (mode === "blend" && !ids.includes(track.id) && ids.length >= 5) {
      $("library-message").textContent = "Blend is full. Remove a song in Discover before adding " + track.title + ".";
      return;
    }
    if (mode === "radio") {
      if (ids[ids.length - 1] !== track.id) ids.push(track.id);
      if (ids.length > 50) ids.shift();
    } else if (!ids.includes(track.id)) ids.push(track.id);
    const params = new URLSearchParams({ [mode === "radio" ? "radio" : "seeds"]: ids.join(",") });
    location.assign((document.body.dataset.discover || "/discover/") + "?" + params);
  }

  function params() {
    return {
      q: $("f-q").value.trim(),
      genre: $("f-genre").value,
      mood: $("f-mood").value,
      decade: $("f-decade").value,
      ordering: $("f-order").value,
      page: state.page,
      page_size: PAGE_SIZE,
    };
  }

  function row(t, n) {
    const chips = (t.genres || []).slice(0, 3).map((g) =>
      h("button", { type: "button", class: "chip chip-filter", "aria-label": "Filter Library by " + g.name, onclick: () => selectGenre(g.name) }, g.name));
    return h("li", { class: "row" },
      h("span", { class: "row-rank" }, String(n)),
      sleeve(t, 52, { artist: true }),
      h("div", null,
        h("div", { class: "row-title" }, t.title),
        h("div", { class: "muted" }, t.artist)),
      h("div", null,
        h("div", { class: "row-meta" }, trackFacts(t).map((f) => h("span", null, f))),
        h("div", { class: "chips", style: "margin-top:6px" }, chips)),
      h("div", { class: "row-actions" },
        h("a", Object.assign({ class: "btn btn-small" }, listenAttrs(t)), "Listen"),
        h("button", { type: "button", class: "btn btn-small", "aria-label": "Add " + t.title + " to your Discover selection", title: "Add to Blend or Radio", onclick: () => addToDiscover(t) }, "Add"),
        h("a", { class: "btn btn-small", href: (document.body.dataset.discover || "/discover/") + "?seeds=" + t.id, "aria-label": "Find tracks similar to " + t.title }, "Find similar")));
  }

  function filtersActive() {
    return Boolean($("f-q").value.trim() || $("f-genre").value || $("f-mood").value || $("f-decade").value || $("f-order").value !== "artist");
  }

  function clearFilters() {
    $("f-q").value = "";
    $("f-genre").value = "";
    $("f-mood").value = "";
    $("f-decade").value = "";
    $("f-order").value = "artist";
    load(true);
  }

  async function load(reset) {
    $("clear-filters").hidden = !filtersActive();
    if (reset) { state.page = 1; state.loaded = 0; }
    const ticket = ++state.ticket;
    try {
      const data = await api.get("tracks/", params());
      if (ticket !== state.ticket) return;
      const list = $("rows");
      if (reset) list.replaceChildren();
      list.append(...data.results.map((t, i) => row(t, state.loaded + i + 1)));
      state.total = data.count;
      state.loaded += data.results.length;
      $("count").textContent = data.count
        ? number(data.count) + (data.count === 1 ? " track" : " tracks")
        : "No tracks match. Clear a filter to see more.";
      $("more").hidden = state.loaded >= state.total;
    } catch (err) {
      $("count").textContent = "Couldn\u2019t load tracks. " + err.message;
    }
  }

  async function fillFilters() {
    const [genres, moods, stats] = await Promise.all([
      api.get("genres/").catch(() => ({ results: [] })),
      api.get("moods/").catch(() => ({ results: [] })),
      api.get("stats/").catch(() => ({ decades: {} })),
    ]);
    genres.results.forEach((g) => $("f-genre").append(h("option", { value: g.name }, g.name + " (" + g.tracks + ")")));
    moods.results.filter((m) => m.tracks > 0).forEach((m) => $("f-mood").append(h("option", { value: m.name }, m.name + " (" + m.tracks + ")")));
    Object.keys(stats.decades || {}).forEach((d) => $("f-decade").append(h("option", { value: d }, d)));
  }

  const reload = debounce(() => load(true), 200);
  ["f-genre", "f-mood", "f-decade", "f-order"].forEach((id) => $(id).addEventListener("change", () => load(true)));
  $("f-q").addEventListener("input", reload);
  $("more").addEventListener("click", () => { state.page += 1; load(false); });
  $("clear-filters").addEventListener("click", clearFilters);

  fillFilters().then(() => load(true));
})();
