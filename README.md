# NextTrack

NextTrack is a music recommendation web app and REST API. Pick up to five songs and it lines up what to play next, scoring every candidate on **genre tags, mood, tempo and release decade**. Each result shows how its score was made up and why it was chosen, and you can change how much each feature matters.

- **Backend:** Python 3.9+ (built and tested on 3.12), Django 4.2 LTS, Django REST Framework, SQLite (PostgreSQL optional)
- **Data:** a bundled demo catalogue, plus importers for the Last.fm, MusicBrainz and TheAudioDB APIs
- **Frontend:** server-rendered pages with vanilla JavaScript talking to the JSON API (no build step)
- **Evaluation:** offline metrics, feature ablations and baselines built into the app and the command line

## Quick start

Needs Python 3.9 or newer. Check with `python3 --version`; if it's older than 3.9, install a newer Python first (`pyenv`, python.org, or your OS package manager) — `pip install django` will otherwise silently offer only very old Django versions, which is a common source of confusing install errors.

```bash
# 1. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create the database tables (migrations are generated on first setup; commit them afterwards)
python manage.py makemigrations catalog recommender
python manage.py migrate

# 4. Load the demo catalogue (157 tracks)
python manage.py seed_demo

# 5. Run
python manage.py runserver
```

Open <http://127.0.0.1:8000/>. Optional: `python manage.py createsuperuser` to use the catalogue admin at `/admin/`.

Check the install with `python manage.py test`.

## The web app

| Page | What it does |
| --- | --- |
| **Landing** (`/`) | Entry page built from live data: a wall of the catalogue's artist photos, one recommendation scored live on each visit, and a chart of the most-listened tracks (each row opens Discover with that song as the seed). |
| **Discover** (`/discover/`) | Two modes. **Blend** builds a set of seeds; **Radio** builds an ordered listening path, where each *Play next* plays the song and refills the queue from the latest songs (kept in the URL as `?radio=`). A **List | Map | Bridge** switch shows the recommendations as the explained list, on the taste map (lines from your songs to each recommendation), or as a Bridge: choose a start and an end song and get a fixed-length playlist that travels between them, so no step feels abrupt; the route also draws on the shared map. In both modes, search for songs, tune the mix (feature weights, variety, songs per artist, blend or closest-to-any) and read explained recommendations. Like or skip results to personalise. Seeds are kept in the URL, so a link shares a starting point. |
| **Library** (`/library/`) | Browse and filter the catalogue by genre, mood and decade. Click a track's genre chip to apply the Genre filter, or choose Add to take it into the current Blend or Radio selection in Discover. |
| **Evaluation** (`/evaluation/`) | Catalogue statistics and a live comparison of the full model against ablations and baselines. |
| **API** (`/api-docs/`) | Endpoint reference with a console to send requests. |
| **Method** (`/method/`) | Plain-language explanation of the algorithm, data sources and limits. |

## How recommendations are made

Each pair of tracks is compared on four features, each giving a similarity in [0, 1]:

| Feature | Similarity |
| --- | --- |
| Genre | Cosine similarity of tag vectors. Tags are expanded up a small genre hierarchy (`indie rock` also counts towards `rock`) and weighted by inverse document frequency so rare tags matter more. |
| Mood | Gaussian of the distance between moods placed on Russell's valence/arousal plane. |
| Tempo | Gaussian on `abs(log2(bpm_a / bpm_b))`, with half/double time allowed at a fixed penalty. |
| Decade | Gaussian on the difference in release years (sigma 12). |

The pair score is the weighted mean of the features available for both tracks, so tracks with no tempo or year can still be recommended (a small penalty applies). Weights default to 0.45 / 0.25 / 0.15 / 0.15 and are always normalised.

For several seeds the score is the mean across seeds (`aggregate=mean`) or the best single match (`aggregate=max`). Results are re-ranked with Maximal Marginal Relevance and a per-artist cap. Skipped tracks are excluded and lookalikes are pushed down; liked tracks join the seeds at half weight.

The engine is pure Python in `recommender/engine.py` and has no Django dependency.

## API

Base path `/api/`. Reading is open; adding a track needs a token (`Authorization: Token <key>`), and editing or deleting tracks is limited to staff accounts. Full reference with a request console at `/api-docs/`.

| Method and path | Purpose |
| --- | --- |
| `POST /api/bridge/` | A fixed-length playlist between `from_id` and `to_id`, with optional `weights` |
| `GET /api/map/` | Every placed track's taste map position (0 to 1) and genre family, plus how many tracks aren't placed yet |
| `POST /api/recommendations/` | Recommend for `seeds` and/or a Radio `history` (tracks played, oldest first), with optional `k`, `weights`, `aggregate`, `diversity`, `max_per_artist`, `exclude`, `personalise` |
| `GET /api/recommendations/?seeds=1,2&w_genre=0.5` | Same, using query parameters |
| `GET /api/tracks/{id}/similar/` | Recommendations for a single track |
| `GET /api/tracks/` | Search and filter (`q`, `genre`, `mood`, `decade`, `artist`, `ordering`, `page`, `page_size`) |
| `POST /api/tracks/` | Add a track (token) |
| `PATCH /api/tracks/{id}/`, `DELETE /api/tracks/{id}/` | Edit or delete a track (staff only) |
| `GET /api/artists/`, `/api/genres/`, `/api/moods/` | Lookups |
| `POST /api/feedback/` | Like (1), skip (-1) or clear (0) |
| `GET /api/stats/`, `GET /api/evaluation/` | Catalogue statistics and offline evaluation |
| `POST /api/auth/register/`, `POST /api/auth/token/` | Get an API token |

```bash
curl -X POST http://127.0.0.1:8000/api/recommendations/ \
  -H 'Content-Type: application/json' \
  -d '{"seeds": [1, 2], "k": 5, "weights": {"genre": 3, "mood": 1}}'
```

## Using real data

Copy `.env.example` to `.env` and set `LASTFM_API_KEY` (free at <https://www.last.fm/api/account/create>) and `MUSICBRAINZ_USER_AGENT` (include a contact email).

```bash
# Top tracks for tags: genres from Last.fm tags, mood from a tag lexicon, popularity from listeners
python manage.py import_lastfm --tag rock --tag jazz --limit 50

# Also store Last.fm's similar-track lists as ground truth for evaluation
python manage.py import_lastfm --tag rock --limit 25 --similar

# Add release years and MusicBrainz IDs (1 request per second)
python manage.py enrich_musicbrainz --limit 100

# Add real artist photos and short biographies from TheAudioDB, where a match exists (cached;
# falls back to generated sleeve art for artists with no photo, so the UI never breaks). Selecting
# an artist's picture opens a card with the larger photo and the biography
python manage.py fetch_artist_images --limit 100

# Add Last.fm listener counts to tracks that have none (e.g. the demo catalogue). These rank the
# landing page chart, break ties in the engine and feed the novelty metric on the Evaluation page
python manage.py fetch_listeners --limit 200

# Build the taste map: scores every pair of tracks with the engine and lays them out in 2D
# (a few seconds for a few hundred tracks). Run it again after importing tracks
python manage.py build_taste_map

# Optional: embedded playback (see docs/ARCHITECTURE.md - needs a real origin, not localhost).
# Needs YOUTUBE_API_KEY; each lookup uses 100 of the 10,000 free daily
# quota units, so target the tracks you need, e.g. your demo seeds (IDs from a Discover URL) plus
# their top 10 recommendations. Tracks without a video keep the YouTube search link.
python manage.py fetch_youtube_ids --ids 12,40,77 --with-recs 10

# Load your own CSV (columns: title,artist,album,year,tempo,mood,genres,listeners)
python manage.py seed_demo --file my_tracks.csv
```

Responses are cached in `.cache/http/`, so repeated imports do not hit the services again. Neither service provides tempo, so imported tracks have none unless you add it (admin, CSV or API). Missing values are handled by the engine.

## Artist images

Every track gets a unique, deterministic "sleeve" - an SVG generated from its genre, mood and title,
so the same track always looks the same and no image needs hosting or licensing. Last.fm removed
artist photos from its API in 2018, so where a real photo is wanted, `fetch_artist_images` fills in
`Artist.image_url` from TheAudioDB; the UI uses it when present and falls back to the generated
sleeve on any load failure (missing photo, dead link, offline API), so a flaky third-party service
can never break the page.

## Evaluation

```bash
python manage.py evaluate --k 10 --sample 100 --json results.json
python manage.py export_feedback --out feedback.csv    # likes and skips, for a user study
```

`evaluate` runs the full model, four one-feature-removed ablations, genre-only, random and (with listener counts) most-popular baselines over the same seed tracks. It reports nDCG, precision and hit rate against the Last.fm reference lists (95% bootstrap intervals), plus coverage, diversity, novelty and latency. See `docs/EVALUATION_GUIDE.md`.

## Tests

```bash
python manage.py test
```

- `recommender/tests/test_engine.py`, `test_evaluation.py` and `catalog/tests/test_taxonomy.py` cover the engine, metrics and data cleaning. They need no database.
- `recommender/tests/test_api.py` and `catalog/tests/test_services.py` cover the API, feedback flow, importers' write path and management commands.
- `integrations/tests/test_clients.py` covers the Last.fm and MusicBrainz clients using mocked responses.

## Configuration

Environment variables (or a `.env` file). See `.env.example`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DJANGO_DEBUG` | `1` | Set `0` in production (also needs a secret key and static file serving) |
| `DJANGO_SECRET_KEY` | dev key when debugging | Required when `DJANGO_DEBUG=0` |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated |
| `POSTGRES_DB` (+ `_USER`, `_PASSWORD`, `_HOST`, `_PORT`) | unset | Use PostgreSQL instead of SQLite. Install `requirements-postgres.txt` |
| `LASTFM_API_KEY` | unset | Needed by `import_lastfm` |
| `MUSICBRAINZ_USER_AGENT` | placeholder | Sent to MusicBrainz |
| `YOUTUBE_API_KEY` | unset | Needed by `fetch_youtube_ids` (optional embedded playback) |
| `THEAUDIODB_API_KEY` | shared test key | Needed by `fetch_artist_images`; get a personal key to move off the shared one |
| `NEXTTRACK_THROTTLE_ANON` / `_USER` | `600/min` / `1200/min` | API rate limits |

## Project layout

```
config/          settings, URLs
catalog/         Artist, Genre, Track models; track/artist/genre API; taxonomy; CSV dataset; import commands
recommender/     engine (pure Python), evaluation, presenters, recommendation/feedback/stats/evaluation API
integrations/    Last.fm, MusicBrainz, TheAudioDB and YouTube clients with rate limiting, retries and disk cache
web/             templates, CSS and JavaScript for the six pages
docs/            architecture notes, evaluation guide, report and video checklists
```

## Pushing to GitHub

```bash
git init
git add .
git commit -m "NextTrack: music recommendation API and web app"
git branch -M main
git remote add origin https://github.com/<your-username>/nexttrack.git
git push -u origin main
```

Commit the generated `catalog/migrations/` and `recommender/migrations/` folders too. The included GitHub Actions workflow runs the tests on every push. Make the repository public (or shared as your submission instructions require) before submitting the link.

## Data notes

The demo catalogue (`catalog/data/demo_tracks.csv`) is hand-curated. BPM, year, mood and genre tags are approximate and meant for demonstration, not as authoritative metadata.

## Licence

MIT. Replace the name in `LICENSE`.
