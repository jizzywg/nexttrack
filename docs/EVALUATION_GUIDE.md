# Evaluation guide

The app measures; you interpret. Run everything yourself and report what you actually get.

## 1. Load ground truth

```bash
# .env needs LASTFM_API_KEY
python manage.py import_lastfm --tag rock --tag pop --tag electronic --tag jazz --tag hip-hop --limit 20 --similar --similar-limit 10
python manage.py enrich_musicbrainz --limit 200       # release years
```

This stores Last.fm similar-track lists in `ReferenceSimilarity`. The imported catalogue also gets listener counts, which enables the popularity baseline and novelty.

Decide and write down: how many seed tracks, which tags, the date you imported (Last.fm data changes), and the `k` you evaluate at.

## 2. Offline metrics

```bash
python manage.py evaluate --k 10 --sample 100 --json results-k10.json
python manage.py evaluate --k 5  --sample 100 --json results-k5.json
```

For each strategy you get nDCG, precision, hit rate (mean and 95% bootstrap interval), coverage, diversity, novelty and latency. Strategies:

- full model, full model with variety (MMR and artist cap)
- four ablations: without genre, without mood, without tempo, without decade
- genre only, random, most popular

Questions to answer in the report: does each feature earn its place (compare ablations to the full model, using the intervals)? How far above random and most-popular is the model? What does the variety setting cost in accuracy and what does it gain in diversity and coverage?

## 3. Weight tuning (optional)

Try a few weight sets and compare nDCG on one set of seeds, then confirm on a different set (`--rng-seed`) so you are not tuning on your test data. State how you split them.

## 4. User study

Ask participants to use the Discover page on a few starting songs and like or skip results. Then:

```bash
python manage.py export_feedback --out feedback.csv
```

Each row has an anonymous participant id, the track, the value (1 or -1) and the seeds shown. Compute like rate per condition (for example, default weights against genre-only, using the presets), and keep participant numbers honest: a small study supports cautious claims only. Tell participants what is stored and get consent as your course requires.

## 5. Things to discuss critically

- Last.fm similarity reflects popularity and listening habits, not sound.
- Tags skew towards English-language, Western music.
- Demo-catalogue BPM and mood values are approximate.
- Sample size, and how seeds were chosen.
- Any result where the intervals overlap is not evidence of a difference.
