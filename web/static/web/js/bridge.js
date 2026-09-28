(function () {
  "use strict";
  const { api, h, sleeve } = window.NT;
  const $ = (id) => document.getElementById(id);
  const state = { from: null, to: null, length: 7, route: [], path: [] };
  let wired = false;

  function fold(text) {
    return text.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  }

  function attachSearch(root, onPick) {
    const input = root.querySelector("input");
    const list = root.querySelector("ul");
    let ticket = 0;
    input.addEventListener("input", async () => {
      const q = input.value.trim();
      if (!q) { list.replaceChildren(); list.hidden = true; return; }
      const mine = ++ticket;
      try {
        const data = await api.get("tracks/", { q, page_size: 6 });
        if (mine !== ticket) return;
        list.replaceChildren(...(data.results.length
          ? data.results.map((t) => h("li", null, h("button", { type: "button", onclick: () => { input.value = ""; list.hidden = true; onPick(t); } },
              sleeve(t, 32), h("span", null, h("div", { class: "pick-title" }, t.title), h("div", { class: "pick-artist" }, t.artist)))))
          : [h("li", null, h("span", { style: "padding:7px 8px;color:var(--dust);display:block" }, "No matches."))]));
        list.hidden = false;
      } catch (err) { }
    });
    input.addEventListener("keydown", (e) => { if (e.key === "Escape") { list.hidden = true; } });
    document.addEventListener("click", (e) => { if (!root.contains(e.target)) list.hidden = true; });
  }

  function renderSlot(key) {
    const chosen = $("bridge-" + key + "-chosen");
    const search = $("bridge-" + key + "-search");
    const track = state[key];
    if (!track) { chosen.hidden = true; search.hidden = false; return; }
    chosen.hidden = false; search.hidden = true;
    chosen.replaceChildren(
      sleeve(track, 34),
      h("div", null, h("p", { class: "pick-title" }, track.title), h("p", { class: "pick-artist" }, track.artist)),
      h("button", { type: "button", class: "icon-btn", "aria-label": "Change the " + key + " song", onclick: () => { state[key] = null; result(null); renderSlot(key); syncBuildButton(); } }, "\u00d7"));
  }

  function syncBuildButton() {
    $("bridge-build").disabled = !(state.from && state.to && state.from.id !== state.to.id);
  }

  function pickViaMap(track) {
    if (!state.from || state.to) { state.from = track; state.to = null; }
    else if (track.id !== state.from.id) { state.to = track; }
    renderSlot("from");
    renderSlot("to");
    syncBuildButton();
    result(null);
  }

  function fallbackReasons(hop) {
    return hop.reasons && hop.reasons.length ? hop.reasons.join(". ") + "." : "Loosely similar overall.";
  }

  function hopRow(hop, index) {
    const t = hop.track;
    const isFirst = index === 0;
    const listenLink = h("a", Object.assign({ class: "icon-btn" }, window.NT.listenAttrs(t)), window.NT.icon("play"));
    return h("li", { class: "rec", "data-id": t.id, style: "--i:" + index },
      h("span", { class: "rec-rank" }, isFirst ? "Start" : String(index)),
      sleeve(t, 64, { artist: true }),
      h("div", { class: "rec-main" },
        h("div", { class: "rec-title" }, t.title),
        h("div", { class: "rec-artist" }, t.artist),
        isFirst ? null : window.NT.anatomy({ score: hop.score, contributions: hop.contributions }, index),
        isFirst ? null : h("p", { class: "rec-why" }, fallbackReasons(hop))),
      h("div", { class: "rec-side" },
        isFirst ? null : h("div", { class: "score" }, String(Math.round(hop.score * 100)), h("small", null, "%")),
        h("div", { class: "actions" }, listenLink)));
  }

  function result(data) {
    if (!data) {
      $("bridge-hops").replaceChildren();
      state.route = [];
      state.path = [];
      if (!document.getElementById("bridge-panel").hidden) window.NT.tasteMap.update({ mode: "bridge", route: [] });
      window.NT.refreshPlaybackButtons();
      return;
    }
    $("bridge-hops").replaceChildren(...data.path.map((hop, i) => hopRow(hop, i)));
    state.route = data.path.map((hop) => hop.track.id);
    state.path = data.path.map((hop) => hop.track);
    window.NT.tasteMap.update({ mode: "bridge", route: state.route });
    window.NT.refreshPlaybackButtons();
  }

  function playableTracks() {
    return state.path.filter((t) => t.youtube_id);
  }

  async function build() {
    if (!state.from || !state.to) return;
    const status = $("bridge-status");
    const btn = $("bridge-build");
    btn.disabled = true;
    status.textContent = "Building\u2026";
    try {
      const raw = window.NT.rawWeights();
      const data = await api.post("bridge/", {
        from_id: state.from.id, to_id: state.to.id, length: state.length,
        weights: Object.fromEntries(Object.entries(raw).map(([key, value]) => [key, value / 100])),
      });
      status.textContent = data.path.length + (data.path.length === 1 ? " song." : " songs.");
      result(data);
    } catch (err) {
      status.textContent = "Couldn\u2019t build a bridge. " + err.message;
      result(null);
    } finally {
      syncBuildButton();
    }
  }

  function wire() {
    if (wired) return;
    wired = true;
    attachSearch($("bridge-from-search"), (t) => { state.from = t; renderSlot("from"); syncBuildButton(); result(null); });
    attachSearch($("bridge-to-search"), (t) => { state.to = t; renderSlot("to"); syncBuildButton(); result(null); });
    $("bridge-length").addEventListener("change", (e) => { state.length = Number(e.target.value); if (state.from && state.to) build(); });
    $("bridge-build").addEventListener("click", build);
  }

  window.NT.bridge = {
    activate() {
      wire();
      window.NT.tasteMap.show({ mode: "bridge", route: state.route });
    },
    pickViaMap,
    playableTracks,
  };
})();
