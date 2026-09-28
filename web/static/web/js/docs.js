(function () {
  "use strict";
  const { h } = window.NT;
  const base = window.location.origin;

  const ENDPOINTS = [
    { method: "POST", path: "/api/recommendations/", what: "Recommend tracks for one or more seeds",
      params: [
        ["seeds", "1 to 10 track ids. Required unless you send a history."],
        ["history", "Radio: up to 50 track ids already played, oldest first. The last three become seeds weighted 1, 0.6 and 0.35, and every played track is left out of the results."],
        ["k", "Tracks to return, 1 to 50 (default 10)."],
        ["weights", "Object with genre, mood, tempo, decade (each 0 to 1). Normalised for you. Defaults to 0.45 / 0.25 / 0.15 / 0.15."],
        ["aggregate", "mean blends all seeds; max ranks by the closest single seed."],
        ["diversity", "0 to 1. Higher penalises near-duplicates (default 0.25)."],
        ["max_per_artist", "Cap per artist, 1 to 10 (default 2)."],
        ["exclude", "Track ids to leave out."],
        ["personalise", "true to use this session's or user's likes and skips."],
      ],
      body: { seeds: [1, 2], k: 5, weights: { genre: 0.5, mood: 0.3, tempo: 0.1, decade: 0.1 }, diversity: 0.25 } },
    { method: "POST", path: "/api/recommendations/", what: "Radio: recommend what should follow a listening history",
      params: [["history", "Tracks played so far, oldest first."], ["k, weights, diversity, max_per_artist, personalise", "As above."]],
      body: { history: [1, 11, 12], k: 5 } },
    { method: "POST", path: "/api/bridge/", what: "A fixed-length playlist that travels from one track to another",
      params: [["from_id, to_id", "Required track ids, must be different."], ["length", "Songs in the playlist, 2 to 12 (default 7)."], ["weights", "As above."]] },
    { method: "GET", path: "/api/map/", what: "Taste map positions for every placed track",
      params: [["(none)", "Returns tracks with x and y between 0 and 1 and a genre family, the families in legend order, and how many tracks aren't placed yet (run build_taste_map after imports)."]] },
    { method: "GET", path: "/api/recommendations/?seeds=1,2&k=5&w_genre=0.5&w_mood=0.5", what: "Same as POST, using query parameters",
      params: [["seeds, history", "Comma-separated ids."], ["w_genre, w_mood, w_tempo, w_decade", "Weights (0 to 1)."], ["k, aggregate, diversity, max_per_artist, exclude, personalise", "As above."]] },
    { method: "GET", path: "/api/tracks/1/similar/?k=5", what: "Tracks similar to a single track",
      params: [["k, w_*, diversity, max_per_artist", "As for recommendations."]] },
    { method: "GET", path: "/api/tracks/?q=daft&mood=euphoric&page_size=5", what: "Search and filter the catalogue",
      params: [
        ["q", "Matches title, artist or album."], ["genre", "Exact genre tag, e.g. post-punk."], ["mood", "One of the moods listed by /api/moods/."],
        ["decade", "e.g. 1990s."], ["artist", "Artist name contains."],
        ["ordering", "title, artist, year, tempo, listeners or random. Prefix - to reverse."], ["page, page_size", "Pagination (page_size up to 100)."],
      ] },
    { method: "GET", path: "/api/tracks/1/", what: "One track with its genre tags", params: [] },
    { method: "POST", path: "/api/tracks/", what: "Add a track (token required)", auth: true,
      params: [["title, artist", "Required. The artist is created if new."], ["year, tempo, mood, album", "Optional."], ["genres", "List of names, or objects with name and weight (0 to 1)."]],
      body: { title: "Example Song", artist: "Example Artist", year: 2021, tempo: 118, mood: "happy", genres: ["indie pop", { name: "synthpop", weight: 0.6 }] } },
    { method: "GET", path: "/api/artists/?q=bob", what: "Search artists", params: [["q", "Name contains."]] },
    { method: "GET", path: "/api/genres/", what: "Genre tags with track counts", params: [] },
    { method: "GET", path: "/api/moods/", what: "Mood vocabulary with valence and arousal", params: [] },
    { method: "POST", path: "/api/feedback/", what: "Like (1), skip (-1) or clear (0) a track",
      params: [["track", "Track id."], ["value", "1, -1 or 0."], ["seeds", "Optional. Seeds on screen at the time."]],
      body: { track: 1, value: 1, seeds: [2] } },
    { method: "GET", path: "/api/stats/", what: "Catalogue counts and distributions", params: [] },
    { method: "GET", path: "/api/evaluation/?k=10&sample=30", what: "Offline evaluation report", params: [["k", "1 to 30."], ["sample", "Seed tracks, 5 to 300."]] },
    { method: "POST", path: "/api/auth/register/", what: "Create an account and get a token",
      params: [["username, password", "Required."], ["email", "Optional."]], body: { username: "your-name", password: "choose-a-long-password" } },
    { method: "POST", path: "/api/auth/token/", what: "Get a token for an existing account", params: [["username, password", "Required."]], body: { username: "your-name", password: "your-password" } },
  ];

  document.getElementById("curl-example").textContent =
    "curl -X POST " + base + "/api/recommendations/ \\\n" +
    "  -H 'Content-Type: application/json' \\\n" +
    "  -d '{\"seeds\": [1, 2], \"k\": 5, \"weights\": {\"genre\": 3, \"mood\": 1}}'";
  document.getElementById("auth-example").textContent =
    "curl -X POST " + base + "/api/auth/register/ -H 'Content-Type: application/json' \\\n" +
    "  -d '{\"username\": \"you\", \"password\": \"a-long-password\"}'\n\n" +
    "curl -X POST " + base + "/api/tracks/ -H 'Authorization: Token <your token>' \\\n" +
    "  -H 'Content-Type: application/json' -d '{\"title\": \"Song\", \"artist\": \"Artist\"}'";

  function cookie(name) {
    const m = document.cookie.split("; ").find((c) => c.startsWith(name + "="));
    return m ? decodeURIComponent(m.split("=")[1]) : "";
  }

  function endpoint(e) {
    const pathInput = h("input", { class: "field", type: "text", value: e.path, "aria-label": "Request path" });
    const tokenInput = e.auth ? h("input", { class: "field", type: "text", placeholder: "Token (or leave empty if you are signed in via /admin/)", "aria-label": "API token" }) : null;
    const bodyInput = e.body ? h("textarea", { class: "field", spellcheck: "false", "aria-label": "JSON body" }) : null;
    if (bodyInput) bodyInput.value = JSON.stringify(e.body, null, 2);
    const out = h("pre", { class: "out", hidden: true });
    const send = h("button", { type: "button", class: "btn btn-primary" }, "Send request");
    send.addEventListener("click", async () => {
      out.hidden = false;
      out.textContent = "Sending...";
      const headers = { Accept: "application/json" };
      const options = { method: e.method, headers, credentials: "same-origin" };
      if (bodyInput) { headers["Content-Type"] = "application/json"; options.body = bodyInput.value; }
      if (tokenInput && tokenInput.value.trim()) headers.Authorization = "Token " + tokenInput.value.trim();
      if (e.method !== "GET" && cookie("csrftoken")) headers["X-CSRFToken"] = cookie("csrftoken");
      try {
        const res = await fetch(pathInput.value, options);
        const text = await res.text();
        let shown = text;
        try { shown = JSON.stringify(JSON.parse(text), null, 2); } catch (err) { }
        out.textContent = "HTTP " + res.status + "\n\n" + shown.slice(0, 20000);
      } catch (err) {
        out.textContent = "Request failed: " + err.message;
      }
    });

    const table = e.params.length
      ? h("table", { class: "params" }, h("tbody", null, e.params.map(([n, d]) => h("tr", null, h("td", null, n), h("td", null, d)))))
      : null;
    return h("details", { class: "endpoint" },
      h("summary", null,
        h("span", { class: "method " + e.method }, e.method),
        h("span", { class: "path" }, e.path.split("?")[0]),
        h("span", { class: "what" }, e.what)),
      h("div", { class: "endpoint-body" },
        table,
        h("div", { class: "tryit" }, pathInput, tokenInput, bodyInput, h("div", null, send), out)));
  }

  document.getElementById("endpoints").replaceChildren(...ENDPOINTS.map(endpoint));
})();
