(function () {
  "use strict";
  const { api, h, sleeve, icon, debounce, FEATURES, trackFacts, number } = window.NT;
  const $ = (id) => document.getElementById(id);

  const MAX_SEEDS = 5;
  const MAX_HISTORY = 50;
  const SHOWN_STEPS = 6;
  const PRESETS = {
    balanced: { genre: 45, mood: 25, tempo: 15, decade: 15 },
    genre: { genre: 80, mood: 10, tempo: 5, decade: 5 },
    feel: { genre: 20, mood: 45, tempo: 30, decade: 5 },
    era: { genre: 30, mood: 15, tempo: 10, decade: 45 },
  };

  const state = { mode: "blend", view: "list", seeds: [], history: [], skipped: new Set(), liked: new Set(), request: 0, agg: "mean", recs: [] };

  let queue = [];
  let queuePos = -1;
  let autoAdvancing = false;

  function queueSource() {
    if (state.view === "bridge") return window.NT.bridge && window.NT.bridge.playableTracks ? window.NT.bridge.playableTracks() : [];
    return state.recs.map((r) => r.track).filter((t) => t.youtube_id);
  }

  function playQueueAt(i, auto) {
    if (i < 0 || i >= queue.length) { stopQueue(); return; }
    queuePos = i;
    autoAdvancing = auto;
    const track = queue[i];
    window.NT.player.open(track.youtube_id, track.title, track.artist,
      auto ? () => playQueueAt(queuePos + 1, true) : null,
      { hasPrev: queuePos > 0, hasNext: queuePos < queue.length - 1, prev: () => playQueueAt(queuePos - 1, autoAdvancing), next: () => playQueueAt(queuePos + 1, autoAdvancing) });
    refreshPlaybackButtons();
  }

  function stopQueue() {
    const wasActive = queuePos >= 0;
    queue = [];
    queuePos = -1;
    autoAdvancing = false;
    if (wasActive) window.NT.player.close();
    refreshPlaybackButtons();
  }

  function togglePlayAll() {
    if (autoAdvancing) { stopQueue(); return; }
    queue = queueSource();
    if (!queue.length) return;
    playQueueAt(0, true);
  }

  function stepQueue(dir) {
    if (queuePos < 0) {
      queue = queueSource();
      if (!queue.length) return;
      playQueueAt(dir > 0 ? 0 : queue.length - 1, false);
    } else {
      playQueueAt(queuePos + dir, autoAdvancing);
    }
  }

  function refreshPlaybackButtons() {
    const count = queueSource().length;
    const playAll = $("play-all");
    if (playAll) {
      playAll.hidden = count === 0 && !autoAdvancing;
      playAll.textContent = autoAdvancing ? "Stop playing" : "Play all";
      playAll.setAttribute("aria-pressed", String(autoAdvancing));
      playAll.title = autoAdvancing ? "Stop playing through the list" : count + (count === 1 ? " song has" : " songs have") + " a video to play";
    }
    const prevBtn = $("queue-prev"), nextBtn2 = $("queue-next");
    if (prevBtn && nextBtn2) {
      const active = queuePos >= 0;
      prevBtn.hidden = nextBtn2.hidden = count === 0 && !active;
      prevBtn.disabled = active ? queuePos <= 0 : count === 0;
      nextBtn2.disabled = active ? queuePos >= queue.length - 1 : count === 0;
    }
  }
  window.NT.refreshPlaybackButtons = refreshPlaybackButtons;

  function mapFocus() {
    return {
      mode: state.mode,
      seeds: state.seeds.map((s) => s.id),
      path: state.history.map((s) => s.id),
      recs: state.recs.map((r) => ({ id: r.track.id, because: r.because ? r.because.id : null })),
    };
  }

  function setView(view) {
    state.view = view;
    stopQueue();
    try { localStorage.setItem("nexttrack:view", view); } catch (e) { }
    $("view-list").setAttribute("aria-pressed", String(view === "list"));
    $("view-map").setAttribute("aria-pressed", String(view === "map"));
    $("view-bridge").setAttribute("aria-pressed", String(view === "bridge"));
    $("recs").hidden = view !== "list";
    $("score-legend").hidden = view !== "list";
    $("bridge-panel").hidden = view !== "bridge";
    if (view === "bridge") {
      $("hero").hidden = true;
      $("results-wrap").hidden = false;
      window.NT.bridge.activate();
    } else if (view === "map") {
      window.NT.tasteMap.show(mapFocus());
    } else {
      window.NT.tasteMap.hide();
      if (!hasInput()) showHero();
    }
  }

  async function pickFromMap(id) {
    try {
      const track = await api.get("tracks/" + id + "/");
      if (state.view === "bridge") window.NT.bridge.pickViaMap(track);
      else if (inRadio()) playNext(track, true);
      else addSeed(track);
    } catch (err) {
      setStatus("Couldn\u2019t add that song. " + err.message);
    }
  }

  const inRadio = () => state.mode === "radio";
  const hasInput = () => (inRadio() ? state.history.length > 0 : state.seeds.length > 0);
  function seedIds() { return (inRadio() ? state.history.slice(-3) : state.seeds).map((s) => s.id); }

  function listNames(names) {
    return names.length > 2 ? names.slice(0, -1).join(", ") + " and " + names.slice(-1) : names.join(" and ");
  }

  function playNext(track, startPlayer) {
    const last = state.history[state.history.length - 1];
    if (!last || last.id !== track.id) state.history.push(track);
    if (state.history.length > MAX_HISTORY) state.history = state.history.slice(-MAX_HISTORY);
    if (startPlayer && track.youtube_id) window.NT.player.open(track.youtube_id, track.title, track.artist);
    afterSeedChange();
  }

  function removeStep(index) {
    state.history.splice(index, 1);
    afterSeedChange();
  }

  function setMode(mode) {
    if (mode === state.mode) return;
    if (mode === "radio") state.history = state.seeds.slice();
    else state.seeds = state.history.slice(-MAX_SEEDS);
    state.mode = mode;
    stopQueue();
    paintMode();
    afterSeedChange();
  }

  function paintMode() {
    $("mode-blend").setAttribute("aria-pressed", String(!inRadio()));
    $("mode-radio").setAttribute("aria-pressed", String(inRadio()));
    $("seeds-h").textContent = inRadio() ? "Your path" : "Your tracks";
    $("seeds-lede").textContent = inRadio()
      ? "Play a song, then keep choosing what plays next. Each choice reshapes the queue, and the songs you played most recently count most."
      : "Pick up to five songs you like. NextTrack works out what fits next.";
    $("seed-empty").textContent = inRadio()
      ? "Nothing played yet. Search above, or start from a suggestion."
      : "Nothing picked yet. Search above, or start from a suggestion.";
  }

  function addSeed(track) {
    if (inRadio()) { playNext(track, false); return; }
    if (state.seeds.some((s) => s.id === track.id)) return;
    if (state.seeds.length >= MAX_SEEDS) {
      setStatus("You can pick up to " + MAX_SEEDS + " tracks. Remove one to add another.");
      return;
    }
    state.seeds.push(track);
    afterSeedChange();
  }

  function removeSeed(id) {
    state.seeds = state.seeds.filter((s) => s.id !== id);
    afterSeedChange();
  }

  function afterSeedChange() {
    renderSeeds();
    syncUrl();
    if (hasInput()) fetchRecs(); else showHero();
  }

  function syncUrl() {
    const ids = (inRadio() ? state.history : state.seeds).map((s) => s.id);
    const url = ids.length ? (inRadio() ? "?radio=" : "?seeds=") + ids.join(",") : location.pathname;
    history.replaceState(null, "", url);
    try {
      if (ids.length) localStorage.setItem("nexttrack:queue", JSON.stringify({ mode: state.mode, ids }));
      else localStorage.removeItem("nexttrack:queue");
    } catch (e) { }
  }

  function renderPath() {
    const steps = state.history;
    const offset = Math.max(0, steps.length - SHOWN_STEPS);
    $("seed-tray").replaceChildren(
      ...(offset ? [h("li", { class: "path-more" }, offset + " earlier " + (offset === 1 ? "song" : "songs"))] : []),
      ...steps.slice(offset).map((t, k) => {
        const index = offset + k;
        const now = index === steps.length - 1;
        return h("li", { class: "seed path-step" + (now ? " is-now" : "") },
          h("span", { class: "path-num", "aria-hidden": "true" }, String(index + 1)),
          sleeve(t, 44, { artist: true }),
          h("div", { class: "pick-text" },
            h("span", { class: "sr" }, (now ? "Currently at, song " : "Song ") + (index + 1) + ": "),
            h("span", { class: "pick-title" }, t.title),
            h("span", { class: "pick-artist" }, now ? "Current" : t.artist)),
          h("a", Object.assign({ class: "icon-btn" }, window.NT.listenAttrs(t)), icon("play")),
          h("button", { type: "button", class: "icon-btn", "aria-label": "Remove song " + (index + 1) + ", " + t.title + ", from your path", onclick: () => removeStep(index) }, icon("remove")));
      })
    );
    $("seed-counter").textContent = steps.length + " played";
    $("seed-empty").hidden = steps.length > 0;
    document.querySelector(".desk").classList.toggle("has-seeds", steps.length > 0);
  }

  function clearPicks() {
    if (inRadio()) state.history = []; else state.seeds = [];
    state.skipped = new Set();
    state.liked = new Set();
    stopQueue();
    afterSeedChange();
  }

  function renderSeeds() {
    $("clear-picks").hidden = !hasInput();
    if (inRadio()) { renderPath(); return; }
    const tray = $("seed-tray");
    tray.replaceChildren(
      ...state.seeds.map((t) =>
        h("li", { class: "seed" },
          sleeve(t, 44, { artist: true }),
          h("div", { class: "pick-text" },
            h("span", { class: "pick-title" }, t.title),
            h("span", { class: "pick-artist" }, t.artist)),
          h("a", Object.assign({ class: "icon-btn" }, window.NT.listenAttrs(t)), icon("play")),
          h("button", { type: "button", class: "icon-btn", "aria-label": "Remove " + t.title, onclick: () => removeSeed(t.id) }, icon("remove")))
      )
    );
    $("seed-counter").textContent = state.seeds.length + " of " + MAX_SEEDS;
    $("seed-empty").hidden = state.seeds.length > 0;
    document.querySelector(".desk").classList.toggle("has-seeds", state.seeds.length > 0);
  }

  function pickButton(track, onPick) {
    return h("li", null,
      h("button", { type: "button", class: "pick", onclick: () => onPick(track) },
        sleeve(track, 36),
        h("span", { class: "pick-text" },
          h("span", { class: "pick-title" }, track.title),
          h("span", { class: "pick-artist" }, track.artist + (track.year ? " (" + track.year + ")" : "")))));
  }

  const runSearch = debounce(async function () {
    const q = $("seed-search").value.trim();
    const box = $("search-results");
    if (q.length < 2) { box.hidden = true; return; }
    try {
      const data = await api.get("tracks/", { q, page_size: 8 });
      if (q !== $("seed-search").value.trim()) return;
      box.replaceChildren(
        ...(data.results.length
          ? data.results.map((t) => pickButton(t, (track) => {
              addSeed(track);
              $("seed-search").value = "";
              box.hidden = true;
            }))
          : [h("li", { class: "no-results" }, "No matches for \u201c" + q + "\u201d. Try a shorter name.")])
      );
      box.hidden = false;
    } catch (err) {
      box.replaceChildren(h("li", { class: "no-results" }, "Search failed: " + err.message));
      box.hidden = false;
    }
  }, 200);

  async function loadSuggestions() {
    const list = $("suggestions");
    try {
      const data = await api.get("tracks/", { ordering: "random", page_size: 5 });
      list.replaceChildren(...data.results.map((t) => pickButton(t, addSeed)));
    } catch (err) {
      list.replaceChildren(h("li", { class: "no-results" }, "Couldn\u2019t load suggestions. Is the catalogue empty? Run: python manage.py seed_demo"));
    }
  }

  function rawWeights() {
    const w = {};
    FEATURES.forEach((f) => { w[f.key] = Number($("w-" + f.key).value); });
    return w;
  }

  function paintSliders() {
    const w = rawWeights();
    const total = Object.values(w).reduce((a, b) => a + b, 0);
    FEATURES.forEach((f) => {
      const input = $("w-" + f.key);
      input.style.setProperty("--fill", input.value + "%");
      $("o-" + f.key).textContent = (total ? Math.round((100 * w[f.key]) / total) : 0) + "%";
    });
    const v = $("o-variety");
    v.style.setProperty("--fill", v.value + "%");
    $("variety-out").textContent = v.value + "%";
  }

  function markPreset() {
    const w = rawWeights();
    document.querySelectorAll("[data-preset]").forEach((b) => {
      const p = PRESETS[b.dataset.preset];
      b.setAttribute("aria-pressed", FEATURES.every((f) => p[f.key] === w[f.key]) ? "true" : "false");
    });
  }

  function onMixChange() {
    paintSliders();
    markPreset();
    if (hasInput()) queueFetch();
  }

  function setAgg(mode) {
    state.agg = mode;
    $("agg-mean").setAttribute("aria-pressed", mode === "mean");
    $("agg-max").setAttribute("aria-pressed", mode === "max");
    if (hasInput()) queueFetch();
  }

  const queueFetch = debounce(() => fetchRecs(), 250);

  function setStatus(text) { $("status").textContent = text || ""; }

  function showHero() {
    $("hero").hidden = false;
    $("results-wrap").hidden = true;
  }

  async function fetchRecs() {
    if (!hasInput()) { if (state.view !== "bridge") showHero(); return; }
    const raw = rawWeights();
    const total = Object.values(raw).reduce((a, b) => a + b, 0);
    $("hero").hidden = true;
    $("results-wrap").hidden = false;
    if (total <= 0) {
      setStatus("");
      showNotice("Turn at least one of genre, mood, tempo or decade above zero to compare tracks.", false);
      return;
    }
    const ticket = ++state.request;
    setStatus("Updating\u2026");
    const list = $("recs");
    if (!list.children.length) list.replaceChildren(...Array.from({ length: 5 }, (_, i) => skeletonRow(i)));
    const body = {
      seeds: inRadio() ? [] : seedIds(),
      history: inRadio() ? state.history.map((s) => s.id) : undefined,
      k: Number($("o-k").value),
      weights: Object.fromEntries(FEATURES.map((f) => [f.key, raw[f.key] / 100])),
      aggregate: state.agg,
      diversity: Number($("o-variety").value) / 100,
      max_per_artist: Number($("o-artist").value),
      exclude: Array.from(state.skipped),
      personalise: $("o-personalise").checked,
    };
    try {
      const data = await api.post("recommendations/", body);
      if (ticket !== state.request) return;
      hideNotice();
      renderRecs(data);
      setStatus(number(data.count) + (data.count === 1 ? " track" : " tracks"));
    } catch (err) {
      if (ticket !== state.request) return;
      setStatus("");
      showNotice("Couldn\u2019t load recommendations. " + err.message, true);
    }
  }

  function showNotice(text, isError) {
    const box = $("notice");
    box.hidden = false;
    box.className = "notice" + (isError ? " error" : "");
    box.textContent = text;
  }
  function hideNotice() { $("notice").hidden = true; }

  function anatomy(result, index) {
    const fill = h("span", { class: "anatomy-fill", style: "--score:" + result.score + ";--i:" + index });
    FEATURES.forEach((f) => {
      const value = result.contributions[f.key] || 0;
      if (value > 0) fill.append(h("span", { style: "flex:" + value + ";--c:" + f.color }));
    });
    const label = FEATURES.map((f) => f.label + " " + Math.round((result.contributions[f.key] || 0) * 100)).join(", ");
    return h("span", { class: "anatomy", role: "img", "aria-label": "Score made up of " + label + " points out of 100" }, fill);
  }

  function skeletonRow(i) {
    return h("li", { class: "rec skeleton", style: "--i:" + i, "aria-hidden": "true" },
      h("span", { class: "rec-rank" }),
      h("span", { class: "sleeve" }),
      h("div", { class: "rec-main" },
        h("div", { class: "skel-line", style: "width:52%;height:18px;" }),
        h("div", { class: "skel-line", style: "width:30%;height:14px;" }),
        h("div", { class: "skel-line", style: "width:65%;height:8px;" })),
      h("div", { class: "rec-side" }));
  }

  function renderRecs(data) {
    stopQueue();
    state.recs = data.results;
    refreshPlaybackButtons();
    if (state.view === "map") window.NT.tasteMap.update(mapFocus());
    const liked = data.liked_used.length ? ", plus " + data.liked_used.length + " you liked" : "";
    if (data.history_used && data.history_used.length) {
      const [latest, ...earlier] = data.history_used.map((x) => x.track.title);
      $("results-sub").textContent = "Following " + latest + (earlier.length ? ", with " + listNames(earlier) + " counting less" : "") + liked + ".";
    } else {
      $("results-sub").textContent = "Because you picked " + listNames(data.seeds.map((s) => s.title)) + liked + ".";
    }

    const list = $("recs");
    if (!data.results.length) {
      list.replaceChildren(h("li", { class: "notice" }, "Nothing left to suggest with these settings. Raise the songs-per-artist limit or clear some skips."));
      return;
    }
    list.replaceChildren(...data.results.map((r, i) => recRow(r, i, data)));
  }

  function recRow(r, index, data) {
    const t = r.track;
    const multi = data.seeds.length + (data.history_used || []).length + data.liked_used.length > 1;
    const facts = trackFacts(t).map((f) => h("span", null, f));
    const why = h("p", { class: "rec-why" },
      r.reasons.length ? r.reasons.join(". ") + "." : "Loosely similar overall.",
      multi && r.because ? h("span", { class: "because" }, " Closest to " + r.because.title + ".") : null);

    const listenLink = h("a", Object.assign({ class: "icon-btn" }, window.NT.listenAttrs(t)), icon("play"));
    const likeBtn = h("button", { type: "button", class: "icon-btn", "aria-label": "Like " + t.title, "aria-pressed": String(state.liked.has(t.id)), title: "Like" }, icon("like"));
    const skipBtn = h("button", { type: "button", class: "icon-btn", "aria-label": "Skip " + t.title, title: "Skip" }, icon("skip"));
    const addBtn = inRadio() ? null : h("button", { type: "button", class: "icon-btn", "aria-label": "Use " + t.title + " as a seed", title: "Add to your tracks" }, icon("add"));
    const nextBtn = inRadio() ? h("button", { type: "button", class: "btn btn-small play-next", "aria-label": "Play " + t.title + " next" }, "Play next") : null;

    const li = h("li", { class: "rec", "data-id": t.id, style: "--i:" + index },
      h("span", { class: "rec-rank" }, r.rank),
      sleeve(t, 64, { artist: true }),
      h("div", { class: "rec-main" },
        h("div", { class: "rec-title" }, t.title),
        h("div", { class: "rec-artist" }, t.artist),
        h("div", { class: "facts" }, facts),
        anatomy(r, index),
        why,
        nextBtn),
      h("div", { class: "rec-side" },
        h("div", { class: "score" }, r.match, h("small", null, "%")),
        h("div", { class: "actions" }, listenLink, likeBtn, skipBtn, addBtn)));

    likeBtn.addEventListener("click", () => toggleLike(t, likeBtn));
    skipBtn.addEventListener("click", () => skip(t, li));
    if (addBtn) addBtn.addEventListener("click", () => addSeed(t));
    if (nextBtn) nextBtn.addEventListener("click", () => playNext(t, true));
    return li;
  }

  async function sendFeedback(track, value) {
    try {
      await api.post("feedback/", { track: track.id, value, seeds: seedIds() });
      return true;
    } catch (err) {
      setStatus("Couldn\u2019t save that. " + err.message);
      return false;
    }
  }

  async function toggleLike(track, button) {
    const liked = !state.liked.has(track.id);
    if (!(await sendFeedback(track, liked ? 1 : 0))) return;
    if (liked) state.liked.add(track.id); else state.liked.delete(track.id);
    button.setAttribute("aria-pressed", liked);
    if ($("o-personalise").checked) queueFetch();
  }

  async function skip(track, row) {
    state.skipped.add(track.id);
    row.classList.add("leaving");
    sendFeedback(track, -1);
    setTimeout(() => fetchRecs(), 280);
  }

  function init() {
    FEATURES.forEach((f) => $("w-" + f.key).addEventListener("input", onMixChange));
    $("o-variety").addEventListener("input", onMixChange);
    ["o-artist", "o-k", "o-personalise"].forEach((id) => $(id).addEventListener("change", () => hasInput() && fetchRecs()));
    $("mode-blend").addEventListener("click", () => setMode("blend"));
    $("play-all").addEventListener("click", togglePlayAll);
    $("queue-prev").addEventListener("click", () => stepQueue(-1));
    $("queue-next").addEventListener("click", () => stepQueue(1));
    $("clear-picks").addEventListener("click", clearPicks);
    $("view-list").addEventListener("click", () => setView("list"));
    $("view-map").addEventListener("click", () => setView("map"));
    $("view-bridge").addEventListener("click", () => setView("bridge"));
    window.NT.tasteMap.onPick = pickFromMap;
    window.NT.rawWeights = rawWeights;
    window.NT.anatomy = anatomy;
    let savedView = "list";
    try {
      const stored = localStorage.getItem("nexttrack:view");
      savedView = stored === "map" || stored === "bridge" ? stored : "list";
    } catch (e) { }
    if (savedView !== "list") setView(savedView);
    $("mode-radio").addEventListener("click", () => setMode("radio"));
    $("agg-mean").addEventListener("click", () => setAgg("mean"));
    $("agg-max").addEventListener("click", () => setAgg("max"));
    document.querySelectorAll("[data-preset]").forEach((b) =>
      b.addEventListener("click", () => {
        const p = PRESETS[b.dataset.preset];
        FEATURES.forEach((f) => { $("w-" + f.key).value = p[f.key]; });
        onMixChange();
      })
    );
    $("shuffle").addEventListener("click", loadSuggestions);

    const search = $("seed-search");
    search.addEventListener("input", runSearch);
    search.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { $("search-results").hidden = true; }
      if (e.key === "Enter") {
        e.preventDefault();
        const first = $("search-results").querySelector("button.pick");
        if (first) first.click();
      }
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".search")) $("search-results").hidden = true;
    });

    const mix = $("mix");
    const syncMix = () => { mix.open = window.matchMedia("(min-width: 1181px)").matches ? true : mix.open; };
    if (!window.matchMedia("(min-width: 1181px)").matches) mix.open = false;
    window.matchMedia("(min-width: 1181px)").addEventListener("change", syncMix);

    paintSliders();
    renderSeeds();
    loadSuggestions();
    loadFromUrl();
  }

  async function loadFromUrl() {
    const params = new URLSearchParams(location.search);
    const parse = (value) => (value || "").split(",").map(Number).filter((n) => Number.isInteger(n) && n > 0);
    let radio = parse(params.get("radio")).slice(-MAX_HISTORY);
    let ids = radio.length ? radio : parse(params.get("seeds")).slice(0, MAX_SEEDS);
    if (!ids.length) {
      try {
        const saved = JSON.parse(localStorage.getItem("nexttrack:queue") || "null");
        if (saved && Array.isArray(saved.ids) && saved.ids.length) {
          if (saved.mode === "radio") radio = saved.ids.slice(-MAX_HISTORY);
          ids = saved.mode === "radio" ? radio : saved.ids.slice(0, MAX_SEEDS);
        }
      } catch (e) { }
    }
    if (!ids.length) return;
    const found = (await Promise.all(ids.map((id) => api.get("tracks/" + id + "/").catch(() => null)))).filter(Boolean);
    if (radio.length) { state.mode = "radio"; state.history = found; paintMode(); } else { state.seeds = found; }
    afterSeedChange();
  }

  init();
})();
