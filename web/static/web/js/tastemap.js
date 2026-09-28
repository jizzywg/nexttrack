(function () {
  "use strict";
  const NT = window.NT;
  const SVGNS = "http://www.w3.org/2000/svg";
  const FAMILIES = {
    "rock": ["Rock", "#f25f5c"], "pop": ["Pop", "#ff8fd0"], "electronic and dance": ["Electronic and dance", "#4ea8ff"],
    "r&b and soul": ["R&B and soul", "#b18cff"], "hip hop": ["Hip hop", "#ffab4c"], "jazz and blues": ["Jazz and blues", "#2fd6c9"],
    "folk and country": ["Folk and country", "#9ad65a"], "latin": ["Latin", "#ffe066"], "other": ["Other", "#9a96c2"],
  };
  const PAD = 28;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const $ = (id) => document.getElementById(id);

  let data = null, loading = null, built = false, visible = false;
  let byId = new Map(), dots = new Map();
  let W = 0, H = 0, TOP = 60, BOTTOM = 60;
  let view = { x0: 0, y0: 0, s: 1 }, tween = 0;
  let focus = { mode: "blend", seeds: [], path: [], recs: [] };
  let family = null, hover = null;
  const api = { onPick: null };

  function s(tag, attrs) {
    const el = document.createElementNS(SVGNS, tag);
    Object.entries(attrs || {}).forEach(([k, v]) => el.setAttribute(k, v));
    return el;
  }
  const pos = (id) => {
    const t = byId.get(id);
    return [PAD + (t.x - view.x0) / view.s * (W - 2 * PAD), TOP + (t.y - view.y0) / view.s * Math.max(80, H - TOP - BOTTOM)];
  };
  const placed = (ids) => ids.filter((id) => byId.has(id));

  function load() {
    if (!loading) {
      loading = NT.api.get("map/").then((d) => { data = d; byId = new Map(d.tracks.map((t) => [t.id, t])); }).catch((err) => { loading = null; throw err; });
    }
    return loading;
  }

  function measure() {
    const box = $("taste-map").getBoundingClientRect();
    W = box.width; H = box.height;
    const legend = $("tm-legend"), hint = document.querySelector(".tm-hint"), noteEl = $("tm-note");
    BOTTOM = legend.offsetHeight ? legend.offsetHeight + 24 : 28;
    TOP = (hint ? hint.offsetHeight + 22 : 28) + (noteEl.hidden ? 0 : noteEl.offsetHeight + 8);
    $("tm-svg").setAttribute("viewBox", "0 0 " + W + " " + H);
  }

  function build() {
    built = true;
    const small = data.tracks.length > 400;
    const group = $("tm-dots");
    data.tracks.forEach((t) => {
      const g = s("g", { class: "tm-dot", "data-id": t.id });
      g.append(s("circle", { class: "tm-hit", r: 11 }), s("circle", { class: "tm-core", r: small ? 4.5 : 6, fill: (FAMILIES[t.family] || FAMILIES.other)[1] }));
      group.append(g);
      dots.set(t.id, g);
    });
    const counts = {};
    data.tracks.forEach((t) => { counts[t.family] = (counts[t.family] || 0) + 1; });
    $("tm-legend").replaceChildren(...data.families.filter((f) => counts[f]).map((f) => {
      const b = NT.h("button", { type: "button", "aria-pressed": "false" }, NT.h("i", { style: "background:" + FAMILIES[f][1] }), FAMILIES[f][0] + " " + counts[f]);
      b.addEventListener("click", () => {
        family = family === f ? null : f;
        $("tm-legend").querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", "false"));
        if (family) b.setAttribute("aria-pressed", "true");
        draw();
      });
      return b;
    }));
    const svg = $("tm-svg");
    svg.addEventListener("pointermove", onMove);
    svg.addEventListener("pointerleave", () => { $("tm-tip").hidden = true; setHover(null); });
    svg.addEventListener("click", (e) => {
      const g = e.target.closest && e.target.closest(".tm-dot");
      if (g && api.onPick) api.onPick(Number(g.dataset.id));
    });
    new ResizeObserver(() => { if (visible) { measure(); placeDots(); draw(); } }).observe($("taste-map"));
  }

  function setHover(id) {
    if (hover !== null && dots.has(hover)) dots.get(hover).classList.remove("is-hover");
    hover = id;
    if (id !== null) dots.get(id).classList.add("is-hover");
  }

  function onMove(e) {
    const g = e.target.closest && e.target.closest(".tm-dot");
    const id = g ? Number(g.dataset.id) : null;
    if (id !== hover) setHover(id);
    const tip = $("tm-tip");
    if (id === null) { tip.hidden = true; return; }
    const t = byId.get(id);
    tip.replaceChildren(NT.h("b", null, t.title), NT.h("span", null, t.artist), NT.h("span", { class: "tm-fam" }, (FAMILIES[t.family] || FAMILIES.other)[0]));
    tip.hidden = false;
    const box = $("taste-map").getBoundingClientRect();
    let x = e.clientX - box.left + 14, y = e.clientY - box.top + 14;
    if (x > box.width - 230) x -= 250;
    if (y > box.height - 80) y -= 90;
    tip.style.left = x + "px"; tip.style.top = y + "px";
  }

  function placeDots() {
    dots.forEach((g, id) => { const [x, y] = pos(id); g.style.transform = "translate(" + x + "px," + y + "px)"; });
  }

  function rawFocusIds() {
    if (focus.mode === "bridge") return focus.route || [];
    const anchors = focus.mode === "radio" ? focus.path.slice(-3) : focus.seeds;
    return anchors.concat(focus.recs.map((r) => r.id));
  }
  function focusIds() { return placed(rawFocusIds()); }

  function targetView() {
    const ids = focusIds();
    if (ids.length < 2) return { x0: 0, y0: 0, s: 1 };
    const xs = ids.map((id) => byId.get(id).x), ys = ids.map((id) => byId.get(id).y);
    const minX = Math.min(...xs), maxX = Math.max(...xs), minY = Math.min(...ys), maxY = Math.max(...ys);
    const size = Math.min(1, Math.max(0.3, Math.max(maxX - minX, maxY - minY) * 1.3 + 0.06));
    return { x0: (minX + maxX) / 2 - size / 2, y0: (minY + maxY) / 2 - size / 2, s: size };
  }

  function clearOverlays() { ["tm-trail", "tm-links", "tm-labels"].forEach((id) => $(id).replaceChildren()); }

  function curve(a, b) {
    const [x1, y1] = pos(a), [x2, y2] = pos(b);
    const mx = (x1 + x2) / 2, my = (y1 + y2) / 2, dx = x2 - x1, dy = y2 - y1;
    return "M" + x1 + " " + y1 + " Q" + (mx - dy * 0.18) + " " + (my + dx * 0.18) + " " + x2 + " " + y2;
  }
  let taken = [];
  const overlaps = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
  function label(id, rank, awayFrom) {
    const [x, y] = pos(id);
    const raw = byId.get(id).title;
    const title = raw.length > 28 ? raw.slice(0, 27) + "\u2026" : raw;
    const text = (rank ? rank + "  " : "") + title;
    const w = text.length * 6.6 + 4, h = 15;
    const preferLeft = awayFrom !== undefined && awayFrom !== null && byId.has(awayFrom) && pos(awayFrom)[0] > x;
    const right = { ax: x + 12, ay: y + 4, anchor: "start", box: { x: x + 10, y: y - 9, w, h } };
    const left = { ax: x - 12, ay: y + 4, anchor: "end", box: { x: x - 10 - w, y: y - 9, w, h } };
    const above = { ax: x, ay: y - 14, anchor: "middle", box: { x: x - w / 2, y: y - 27, w, h } };
    const below = { ax: x, ay: y + 22, anchor: "middle", box: { x: x - w / 2, y: y + 9, w, h } };
    const spot = (preferLeft ? [left, right, above, below] : [right, left, above, below]).find((c) =>
      c.box.x >= 4 && c.box.x + c.box.w <= W - 4 && c.box.y >= TOP - 16 && c.box.y + c.box.h <= H - BOTTOM + 12 &&
      !taken.some((b) => overlaps(b, c.box)));
    if (!spot) { if (rank) numberMarker(id, rank); return; }
    taken.push(spot.box);
    const t = s("text", { class: "tm-lbl", x: spot.ax, y: spot.ay, "text-anchor": spot.anchor });
    if (rank) { const n = s("tspan", { class: "tm-n" }); n.textContent = rank + "  "; t.append(n); }
    t.append(document.createTextNode(title));
    $("tm-labels").append(t);
  }
  function numberMarker(id, n) {
    const [x, y] = pos(id);
    const t = s("text", { class: "tm-num", x, y }); t.textContent = n;
    $("tm-labels").append(t);
  }

  function draw() {
    clearOverlays();
    taken = [];
    dots.forEach((g) => g.classList.remove("is-anchor", "is-rec", "is-played", "is-route", "dim", "fam-dim"));
    if (focus.mode === "bridge") { drawRoute(); return; }
    const narrow = W < 520;
    const lit = new Set();
    const radio = focus.mode === "radio";
    const path = placed(focus.path);
    const anchors = radio ? path.slice(-1) : placed(focus.seeds);
    if (radio && path.length > 1) {
      $("tm-trail").append(s("path", { class: "tm-trail", d: "M" + path.map((id) => pos(id).join(" ")).join(" L") }));
      path.slice(0, -1).forEach((id) => { dots.get(id).classList.add("is-played"); lit.add(id); });
    }
    anchors.forEach((id) => { dots.get(id).classList.add("is-anchor"); lit.add(id); label(id, null, focus.recs.length ? focus.recs[0].id : null); });
    focus.recs.forEach((r, k) => {
      if (!byId.has(r.id)) return;
      const from = radio ? path[path.length - 1] : (byId.has(r.because) ? r.because : anchors[0]);
      if (from !== undefined && byId.has(from)) {
        $("tm-links").append(s("path", { class: "tm-link", d: curve(from, r.id), pathLength: 1, style: "animation-delay:" + (k * 0.05).toFixed(2) + "s" }));
      }
      dots.get(r.id).classList.add("is-rec"); lit.add(r.id);
      if (narrow) numberMarker(r.id, k + 1); else label(r.id, k + 1, from);
    });
    if (lit.size) dots.forEach((g, id) => { if (!lit.has(id)) g.classList.add("dim"); });
    if (family) dots.forEach((g, id) => { if (byId.get(id).family !== family && !lit.has(id)) g.classList.add("fam-dim"); });
    if (hover !== null) dots.get(hover).classList.add("is-hover");
  }

  function drawRoute() {
    const route = placed(focus.route || []);
    if (!route.length) return;
    if (route.length > 1) {
      $("tm-links").append(s("path", {
        class: "tm-route", d: "M" + route.map((id) => pos(id).join(" ")).join(" L"), pathLength: 1,
      }));
    }
    route.forEach((id, k) => {
      dots.get(id).classList.add("is-route");
      if (k === 0 || k === route.length - 1) label(id, null, route[k === 0 ? 1 : k - 1]);
      numberMarker(id, k + 1);
    });
    const lit = new Set(route);
    dots.forEach((g, id) => { if (!lit.has(id)) g.classList.add("dim"); });
    if (hover !== null) dots.get(hover).classList.add("is-hover");
  }

  function moveCamera() {
    const to = targetView(), from = Object.assign({}, view);
    cancelAnimationFrame(tween);
    if (reduceMotion || Math.abs(to.x0 - from.x0) + Math.abs(to.y0 - from.y0) + Math.abs(to.s - from.s) < 0.005) {
      view = to; placeDots(); draw(); return;
    }
    clearOverlays();
    const t0 = performance.now(), duration = 650;
    const step = (now) => {
      const k = Math.min(1, (now - t0) / duration), e = 1 - Math.pow(1 - k, 3);
      view = { x0: from.x0 + (to.x0 - from.x0) * e, y0: from.y0 + (to.y0 - from.y0) * e, s: from.s + (to.s - from.s) * e };
      placeDots();
      if (k < 1) tween = requestAnimationFrame(step); else draw();
    };
    tween = requestAnimationFrame(step);
  }

  function intro() {
    const svg = $("tm-svg");
    svg.classList.add("tm-intro");
    dots.forEach((g) => { g.style.transform = "translate(" + W / 2 + "px," + H / 2 + "px)"; });
    requestAnimationFrame(() => requestAnimationFrame(() => {
      svg.classList.add("tm-animating");
      svg.classList.remove("tm-intro");
      view = targetView();
      dots.forEach((g, id) => {
        const [x, y] = pos(id);
        g.style.setProperty("--d", (Math.hypot(x - W / 2, y - H / 2) / Math.hypot(W / 2, H / 2) * 0.45).toFixed(3) + "s");
        g.style.transform = "translate(" + x + "px," + y + "px)";
      });
      setTimeout(() => { svg.classList.remove("tm-animating"); draw(); }, reduceMotion ? 0 : 1500);
    }));
  }

  function note() {
    const hint = document.querySelector(".tm-hint");
    if (hint) hint.textContent = focus.mode === "bridge"
      ? "Each dot is a song. The line traces your bridge from the start song to the end song."
      : "Each dot is a song, placed by how NextTrack scores it: the closer two dots, the more alike. " +
        (focus.mode === "radio" ? "Select a dot to play it next." : "Select a dot to add it to your tracks.");
    const el = $("tm-note");
    if (!data.tracks.length) { el.textContent = "The map hasn't been built yet. Run: python manage.py build_taste_map"; el.hidden = false; return; }
    const raw = rawFocusIds();
    const missing = raw.length && focusIds().length < raw.length;
    el.textContent = (data.unplaced ? data.unplaced + (data.unplaced === 1 ? " song was" : " songs were") + " added after the map was built and " + (data.unplaced === 1 ? "isn't" : "aren't") + " on it yet." : "") +
      (missing ? (data.unplaced ? " " : "") + "Some of your songs aren't on the map yet." : "");
    el.hidden = !el.textContent;
  }

  api.show = async function (next) {
    if (next) focus = next;
    $("taste-map").hidden = false;
    visible = true;
    try {
      await load();
    } catch (err) {
      $("tm-note").textContent = "Couldn\u2019t load the map. " + err.message; $("tm-note").hidden = false;
      return;
    }
    if (!visible) return;
    note();
    measure();
    if (!W || !H) {
      const ro = new ResizeObserver((entries) => {
        if (entries[0].contentRect.width > 0 && entries[0].contentRect.height > 0) { ro.disconnect(); if (visible) api.show(); }
      });
      ro.observe($("taste-map"));
      return;
    }
    if (!built) { build(); measure(); intro(); } else moveCamera();
  };
  api.update = function (next) {
    focus = next;
    if (!visible || !built) return;
    note();
    measure();
    moveCamera();
  };
  api.hide = function () { visible = false; cancelAnimationFrame(tween); $("taste-map").hidden = true; };
  api.refresh = function () { loading = null; data = null; };

  NT.tasteMap = api;
})();
