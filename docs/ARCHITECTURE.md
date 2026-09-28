# Architecture

## Layers

```
Browser (vanilla JS)  ->  Django views/DRF  ->  services.py  ->  engine.py (pure Python)
                                   |                 |
                              Django ORM  <----------+   builds an in-memory index from Track rows
                                   |
                         SQLite / PostgreSQL
```

- **`recommender/engine.py`** holds the algorithm and has no Django imports. It is unit-tested without a database and can be benchmarked or reused elsewhere.
- **`recommender/services.py`** turns database rows into `TrackProfile` objects and keeps one shared `Recommender` index in memory. The index is rebuilt when the catalogue changes (a fingerprint of row counts and the latest `updated_at`, plus signals on save and delete).
- **`recommender/presenters.py`** shapes engine output into the JSON returned by the API. It is pure Python too, so the web app, tests and tooling share one response format.
- **`catalog/taxonomy.py`** is the controlled vocabulary: moods with valence/arousal coordinates, genre aliases, the genre hierarchy, non-genre tag stoplist, and mood/year inference from free-text tags.
- **`integrations/`** wraps Last.fm, MusicBrainz and TheAudioDB behind a rate-limited client with retries and an on-disk JSON cache. Last.fm error payloads (HTTP 200 with an `error` key) are never cached.

## Data model

- `Artist(name, mbid, image_url, bio)`, `Genre(name)`
- `Track(title, artist, album, year, tempo, mood, mbid, lastfm_url, listeners, source)` with a unique artist + title constraint
- `TrackGenre(track, genre, weight)` links tracks to weighted genre tags
- `Feedback(user or session_key, track, value, seeds)` stores likes (+1) and skips (-1)
- `ReferenceSimilarity(track, similar, match, source)` stores Last.fm similar-track lists used as evaluation ground truth

## Request flow: `POST /api/recommendations/`

1. `RecommendationRequestSerializer` validates seeds, weights and options.
2. `get_recommender()` returns the shared index (rebuilding it if needed).
3. If `personalise` is set, the current user's or session's likes and skips are loaded.
4. `run_recommendation()` scores all candidates against the seeds, applies the dislike penalty, re-ranks with MMR and the artist cap, and builds explanations.
5. The response contains the normalised weights, per-result score, per-feature contributions, reasons and timing.

## Design decisions worth explaining in the report

- **Missing features are dropped, not zero-filled.** Sparse imported data is the normal case, so the score renormalises over available features and applies a small penalty.
- **IDF-weighted, hierarchical genre vectors** stop generic tags such as "rock" and "pop" dominating, and let related sub-genres overlap.
- **Mood as coordinates** avoids treating "euphoric" and "happy" as unrelated labels.
- **Tempo compared as a ratio** with a half/double-time allowance.
- **Explanations come from the same numbers as the score**, so the reasons cannot drift from the ranking.
- **Ground truth from a different signal.** Last.fm's similar tracks come from listening behaviour, so evaluating against them is not circular.
- **Bridge is a beam search over the engine's own pairwise scores, not a new scoring model.** `recommender/bridge.py` finds the fixed-length path between two chosen songs that maximises its weakest step (so no single jump feels abrupt), using a backward "best worst-step still reachable" table to prune a forward beam search, with the same "no two consecutive tracks by one artist" rule as everywhere else in the app. It shares `explain()` with the rest of the app, so a hop's reasons are generated the same way a recommendation's are. It is not used by `recommend()` and does not affect ordinary recommendations.
- **The taste map is built from the engine's own scores.** `build_taste_map` scores every pair of tracks at the default weights, treats `1 - score` as distance, and places the tracks in 2D with t-SNE (scikit-learn), storing `map_x`/`map_y` on each track. On the demo catalogue, 53% of each song's 10 closest matches by engine score are among its 10 closest dots (5% for random placement). The layout is deterministic for a given seed. Positions are saved with `bulk_update`, which leaves `updated_at` alone, so rebuilding the map does not rebuild the recommendation index.
- **Radio follows a sequence, not a set.** The brief asks for a next track that follows from a sequence of tracks. `history` sends the listening order; the server turns the last three into seeds weighted 1, 0.6 and 0.35 (`RECENCY_WEIGHTS` in `presenters.py`) and excludes everything already played. It reuses the engine's weighted-seed blending, so no new scoring code was needed, and Blend behaves exactly as before when no history is sent.
- **Anonymous sessions can give feedback** without an account, which makes a small user study easy to run.
- **Playback through YouTube embeds, not hosted audio.** NextTrack holds no licensed audio. `fetch_youtube_ids` stores one embeddable video ID per chosen track and the play button opens it in a docked player; tracks without one open a YouTube search. The Data API's search quota (100 units per lookup, 10,000 a day) is why IDs are fetched for selected tracks rather than the whole catalogue.
- **The embed only works when the app is served from a real origin, not `localhost`.** During development the embed consistently failed with YouTube's own "Video unavailable" screen when accessed as `localhost`/`127.0.0.1`, even with a correct `Referrer-Policy` (`config/settings.py`'s `SECURE_REFERRER_POLICY`). The same build worked without issue for an independent tester, and directly when tunnelled through ngrok from the same machine - so this is specific to the local-development origin, not the referrer policy, the videos, or any one machine. Anyone grading or demoing this needs to access it through a real address (an ngrok tunnel or a deployment), not bare `localhost`, for the embed to work.
- **Generated sleeve art, with a real photo layered on top when one is available.** Every track gets a deterministic SVG "sleeve" from its own genre/mood/title, so the catalogue never depends on hosting or licensing images (Last.fm stopped serving artist photos over its API in 2018). `fetch_artist_images` optionally fills in a real photo from TheAudioDB; the frontend prefers it but falls back to the generated art on any failure, so a flaky third-party API degrades gracefully instead of breaking the page.

## Known limitations

- The in-memory index scales linearly with catalogue size; thousands of tracks are fine, hundreds of thousands would need an approximate nearest-neighbour index.
- Mood is a single label per track and comes from tag words, which is coarse.
- Tempo is not available from Last.fm or MusicBrainz, so imported tracks have none unless added.
- Last.fm reference lists favour popular tracks, which biases accuracy metrics.
- The taste map flattens four features into two dimensions, so neighbourhoods are reliable but distances between far-apart clusters are only approximate; a recommendation can look far from its seed, especially after variety re-ranking. Tracks imported after the last `build_taste_map` run are left off the map until it is rebuilt.
