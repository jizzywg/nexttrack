(function () {
  "use strict";
  const NT = (window.NT = window.NT || {});

  NT.FEATURES = [
    { key: "genre", label: "Genre", color: "var(--genre)" },
    { key: "mood", label: "Mood", color: "var(--mood)" },
    { key: "tempo", label: "Tempo", color: "var(--tempo)" },
    { key: "decade", label: "Decade", color: "var(--decade)" },
  ];

  const root = (document.body.dataset.api || "/api/").replace(/\/?$/, "/");

  function cookie(name) {
    const match = document.cookie.split("; ").find((c) => c.startsWith(name + "="));
    return match ? decodeURIComponent(match.split("=")[1]) : "";
  }

  function query(params) {
    const sp = new URLSearchParams();
    Object.entries(params || {}).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") sp.append(k, v);
    });
    const s = sp.toString();
    return s ? "?" + s : "";
  }

  async function request(method, path, opts) {
    opts = opts || {};
    const headers = { Accept: "application/json" };
    if (opts.body !== undefined) headers["Content-Type"] = "application/json";
    if (method !== "GET") {
      const token = cookie("csrftoken");
      if (token) headers["X-CSRFToken"] = token;
    }
    const url = root + String(path).replace(/^\//, "") + query(opts.params);
    const res = await fetch(url, {
      method,
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
      credentials: "same-origin",
    });
    const text = await res.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (e) { data = text; }
    if (!res.ok) {
      const err = new Error(NT.errorMessage(data) || "Request failed (" + res.status + ")");
      err.status = res.status;
      err.data = data;
      throw err;
    }
    return data;
  }

  NT.api = {
    root,
    get: (path, params) => request("GET", path, { params }),
    post: (path, body) => request("POST", path, { body }),
  };

  NT.errorMessage = function (data) {
    if (!data) return "";
    if (typeof data === "string") return data.slice(0, 200);
    if (data.detail) return String(data.detail);
    const first = Object.entries(data)[0];
    if (!first) return "";
    const [field, msgs] = first;
    return field + ": " + (Array.isArray(msgs) ? msgs.join(" ") : String(msgs));
  };

  NT.h = function h(tag, attrs, ...children) {
    const el = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (v === false || v === null || v === undefined) return;
      if (k === "class") el.className = v;
      else if (k === "style") el.setAttribute("style", v);
      else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    });
    children.flat().forEach((c) => {
      if (c === null || c === undefined || c === false) return;
      el.append(c.nodeType ? c : document.createTextNode(String(c)));
    });
    return el;
  };

  NT.debounce = function (fn, ms) {
    let t;
    return function (...args) {
      clearTimeout(t);
      t = setTimeout(() => fn.apply(this, args), ms);
    };
  };

  function hash(str) {
    let h = 2166136261;
    for (let i = 0; i < str.length; i++) {
      h ^= str.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }
  function rng(seed) {
    return function () {
      seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
      let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  const AROUSAL = { euphoric: 0.8, energetic: 0.9, happy: 0.3, romantic: -0.2, chill: -0.7, melancholic: -0.4, dark: 0.3, aggressive: 0.9 };

  NT.sleeve = function (track, size, options) {
    const clickable = Boolean(options && options.artist && track.artist_id);
    const el = document.createElement(clickable ? "button" : "span");
    el.className = clickable ? "sleeve sleeve-btn" : "sleeve";
    if (clickable) {
      el.type = "button";
      el.setAttribute("aria-label", "About " + track.artist);
      el.title = "About " + track.artist;
      el.addEventListener("click", () => NT.artistCard.open(track, el));
    } else {
      el.setAttribute("aria-hidden", "true");
    }
    if (size) { el.style.width = size + "px"; el.style.height = size + "px"; }

    const generated = () => { el.innerHTML = NT.generatedSleeveSvg(track); };

    if (track.artist_image) {
      const img = document.createElement("img");
      img.src = track.artist_image;
      img.alt = "";
      img.loading = "lazy";
      img.onerror = generated;
      el.append(img);
      const tint = document.createElement("span");
      tint.className = "sleeve-tint";
      el.append(tint);
    } else {
      generated();
    }
    return el;
  };

  NT.generatedSleeveSvg = function (track) {
    const genres = track.genres || [];
    const g1 = genres[0] ? genres[0].name : "unknown";
    const g2 = genres[1] ? genres[1].name : g1;
    const rand = rng(hash(track.title + "|" + track.artist));
    const hue = hash(g1) % 360;
    const hue2 = (hash(g2) + 40) % 360;
    const arousal = AROUSAL[track.mood] !== undefined ? AROUSAL[track.mood] : 0;
    const sat = 42 + Math.round((arousal + 1) * 16);
    const light = 20 + Math.round(rand() * 8);
    const cx = (18 + rand() * 28).toFixed(1);
    const cy = (18 + rand() * 28).toFixed(1);
    const bg = "hsl(" + hue + " " + sat + "% " + light + "%)";
    const groove = "hsl(" + hue + " " + sat + "% " + (light + 9) + "%)";
    const svg =
      '<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" focusable="false">' +
      '<rect width="64" height="64" fill="' + bg + '"/>' +
      '<circle cx="' + cx + '" cy="' + cy + '" r="30" fill="hsl(' + hue + ' ' + sat + '% 8%)"/>' +
      '<circle cx="' + cx + '" cy="' + cy + '" r="25" fill="none" stroke="' + groove + '" stroke-width=".8"/>' +
      '<circle cx="' + cx + '" cy="' + cy + '" r="21" fill="none" stroke="' + groove + '" stroke-width=".8"/>' +
      '<circle cx="' + cx + '" cy="' + cy + '" r="17" fill="none" stroke="' + groove + '" stroke-width=".8"/>' +
      '<circle cx="' + cx + '" cy="' + cy + '" r="9.5" fill="hsl(' + hue2 + ' 72% 62%)"/>' +
      '<circle cx="' + cx + '" cy="' + cy + '" r="1.8" fill="' + bg + '"/>' +
      '<path d="M0 44 L64 20 L64 27 L0 51 Z" fill="hsl(' + hue2 + ' 80% 75% / .12)"/>' +
      "</svg>";
    return svg;
  };

  const ICONS = {
    like: '<path d="M7 11v9H4v-9h3zm2 9V10.5l4.2-6.2c.9-.4 2 .2 2 1.2V9h4.3c1.1 0 1.9 1 1.7 2.1l-1.3 7.5c-.2.9-1 1.4-1.8 1.4H9z"/>',
    skip: '<path d="M6.4 5 5 6.4 10.6 12 5 17.6 6.4 19l5.6-5.6 5.6 5.6 1.4-1.4-5.6-5.6L19 6.4 17.6 5 12 10.6z"/>',
    add: '<path d="M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6z"/>',
    remove: '<path d="M6.4 5 5 6.4 10.6 12 5 17.6 6.4 19l5.6-5.6 5.6 5.6 1.4-1.4-5.6-5.6L19 6.4 17.6 5 12 10.6z"/>',
    play: '<path d="M8 5.5v13l11-6.5z"/>',
    next: '<path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/>',
    prev: '<path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/>',
  };
  NT.icon = function (name) {
    const span = document.createElement("span");
    span.style.display = "contents";
    span.innerHTML = '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false">' + ICONS[name] + "</svg>";
    return span;
  };

  NT.artistCard = (function () {
    const cache = new Map();
    let dialog = null;
    let opener = null;
    let ticket = 0;

    function shortBio(text) {
      const first = (text || "").split(/\n+/).map((p) => p.trim()).find(Boolean) || "";
      if (first.length <= 420) return first;
      const cut = first.slice(0, 420);
      const end = cut.lastIndexOf(". ");
      return end > 150 ? cut.slice(0, end + 1) : cut.trimEnd() + "\u2026";
    }

    function build() {
      dialog = NT.h("dialog", { class: "artist-card", "aria-labelledby": "artist-card-name" },
        NT.h("div", { class: "artist-card-inner" },
          NT.h("button", { type: "button", class: "icon-btn artist-card-close", "aria-label": "Close", onclick: () => dialog.close() }, "\u00d7"),
          NT.h("div", { class: "artist-card-art" }),
          NT.h("div", { class: "artist-card-body" },
            NT.h("h2", { id: "artist-card-name" }),
            NT.h("p", { class: "artist-card-meta" }),
            NT.h("p", { class: "artist-card-bio", "aria-live": "polite" }),
            NT.h("p", { class: "artist-card-credit" }, "Biography from TheAudioDB"))));
      dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });
      dialog.addEventListener("close", () => { if (opener && opener.isConnected) opener.focus(); });
      document.body.append(dialog);
    }

    function show(artist) {
      const meta = dialog.querySelector(".artist-card-meta");
      const bio = dialog.querySelector(".artist-card-bio");
      const text = shortBio(artist.bio);
      meta.textContent = artist.tracks === 1 ? "1 song in the catalogue" : artist.tracks + " songs in the catalogue";
      bio.textContent = text || "No biography is available for this artist yet.";
      bio.classList.toggle("is-empty", !text);
      dialog.querySelector(".artist-card-credit").hidden = !text;
    }

    async function open(track, from) {
      if (!dialog) build();
      opener = from || null;
      const mine = ++ticket;
      dialog.querySelector(".artist-card-art").replaceChildren(NT.sleeve(track));
      dialog.querySelector("#artist-card-name").textContent = track.artist;
      dialog.querySelector(".artist-card-meta").textContent = "";
      const bio = dialog.querySelector(".artist-card-bio");
      bio.textContent = "Loading\u2026";
      bio.classList.add("is-empty");
      dialog.querySelector(".artist-card-credit").hidden = true;
      if (!dialog.open) dialog.showModal();
      try {
        if (!cache.has(track.artist_id)) cache.set(track.artist_id, await NT.api.get("artists/" + track.artist_id + "/"));
        if (mine === ticket) show(cache.get(track.artist_id));
      } catch (err) {
        if (mine === ticket) bio.textContent = "Couldn\u2019t load this artist\u2019s details. " + err.message;
      }
    }

    return { open, close: () => dialog && dialog.close() };
  })();

  NT.listenUrl = function (t) {
    if (t.youtube_id) return "https://www.youtube.com/watch?v=" + encodeURIComponent(t.youtube_id);
    const q = [t.title, t.artist].filter(Boolean).join(" ");
    return "https://www.youtube.com/results?search_query=" + encodeURIComponent(q);
  };

  NT.listenAttrs = function (t) {
    const embedded = Boolean(t.youtube_id);
    return {
      href: NT.listenUrl(t),
      target: "_blank",
      rel: "noopener noreferrer",
      "data-yt": t.youtube_id || null,
      "data-title": t.title,
      "data-artist": t.artist,
      "aria-label": embedded
        ? "Play " + t.title + " by " + t.artist
        : "Search YouTube for " + t.title + " by " + t.artist + " (opens in a new tab)",
      title: embedded ? "Play" : "Find on YouTube (new tab)",
    };
  };

  NT.player = (function () {
    let dock = null;
    let endedCallback = null;

    function build() {
      dock = NT.h("aside", { class: "player", "aria-label": "Now playing", hidden: true },
        NT.h("div", { class: "player-frame" }),
        NT.h("div", { class: "player-bar" },
          NT.h("div", { class: "player-meta" },
            NT.h("p", { class: "player-title" }),
            NT.h("p", { class: "player-artist" })),
          NT.h("a", { class: "player-link", target: "_blank", rel: "noopener noreferrer", onclick: pause }, "Open on YouTube"),
          NT.h("div", { class: "player-nav", hidden: true },
            NT.h("button", { type: "button", class: "icon-btn player-prev", "aria-label": "Previous track", title: "Previous", onclick: () => nav && nav.prev && nav.prev() }, NT.icon("prev")),
            NT.h("button", { type: "button", class: "icon-btn player-next", "aria-label": "Next track", title: "Next", onclick: () => nav && nav.next && nav.next() }, NT.icon("next"))),
          NT.h("button", { type: "button", class: "icon-btn player-close", "aria-label": "Close player", onclick: close }, "\u00d7")));
      document.body.append(dock);
    }

    let nav = null;

    function updateNav() {
      const row = dock && dock.querySelector(".player-nav");
      if (!row) return;
      row.hidden = !nav;
      if (!nav) return;
      dock.querySelector(".player-prev").disabled = !nav.hasPrev;
      dock.querySelector(".player-next").disabled = !nav.hasNext;
    }

    function open(id, title, artist, onEnded, queueNav) {
      if (!dock) build();
      endedCallback = typeof onEnded === "function" ? onEnded : null;
      nav = queueNav || null;
      updateNav();
      const frame = document.createElement("iframe");
      frame.src = "https://www.youtube-nocookie.com/embed/" + encodeURIComponent(id) +
        "?autoplay=1&rel=0&playsinline=1&enablejsapi=1&origin=" + encodeURIComponent(location.origin);
      frame.title = "YouTube player: " + title + " by " + artist;
      frame.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen";
      frame.referrerPolicy = "strict-origin-when-cross-origin";
      dock.querySelector(".player-frame").replaceChildren(frame);
      dock.querySelector(".player-title").textContent = title;
      dock.querySelector(".player-artist").textContent = artist;
      dock.querySelector(".player-link").href = "https://www.youtube.com/watch?v=" + encodeURIComponent(id);
      dock.hidden = false;
    }

    function close() {
      if (!dock) return;
      endedCallback = null;
      nav = null;
      dock.querySelector(".player-frame").replaceChildren();
      dock.hidden = true;
    }

    function pause() {
      const frame = dock && dock.querySelector(".player-frame iframe");
      if (frame && frame.contentWindow) {
        frame.contentWindow.postMessage(JSON.stringify({ event: "command", func: "pauseVideo", args: [] }), "*");
      }
    }

    document.addEventListener("click", (e) => {
      const link = e.target.closest ? e.target.closest("a[data-yt]") : null;
      if (!link || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      e.preventDefault();
      open(link.dataset.yt, link.dataset.title || "", link.dataset.artist || "");
    });

    window.addEventListener("message", (e) => {
      if (!/^https:\/\/(www\.)?youtube(-nocookie)?\.com$/.test(e.origin)) return;
      let data;
      try { data = JSON.parse(e.data); } catch (err) { return; }
      if (data.event === "infoDelivery" && data.info && data.info.playerState === 0 && endedCallback) {
        const cb = endedCallback;
        endedCallback = null;
        cb();
      }
    });

    return { open, close };
  })();

  NT.trackFacts = function (t) {
    const facts = [];
    if (t.year) facts.push(String(t.year));
    if (t.tempo) facts.push(Math.round(t.tempo) + " BPM");
    if (t.mood) facts.push(t.mood);
    return facts;
  };
  NT.number = (n) => new Intl.NumberFormat("en-GB").format(n);
})();
