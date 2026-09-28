# Report and video checklist

Use this to check that the project gives you something concrete to say in each chapter. The writing, results and reflections must be your own.

## Word limits (from the brief)

Introduction 1,000 - Literature review 2,500 - Design 2,000 - Implementation 2,500 - Evaluation 2,500 - Conclusion 1,000. Total no more than 10,500.

## Where the project gives you material

| Chapter | Things in the repository you can point to |
| --- | --- |
| Introduction | The problem (finding the next track without listening history), the four features, target users |
| Literature review | Content-based vs collaborative recommendation, tag-based similarity and IDF, the circumplex model of affect, diversity re-ranking (MMR), explanation in recommender systems, offline evaluation metrics. Read and cite the sources yourself. |
| Design | `docs/ARCHITECTURE.md`, data model, API design, the engine's separation from Django, UI decisions (colour encodes the four features, score breakdown, explanations) |
| Implementation | `recommender/engine.py`, `recommender/services.py`, serializers and views, importers with caching and rate limiting, tests |
| Evaluation | Output of `evaluate`, ablations, baselines, user-study data, limitations from `docs/EVALUATION_GUIDE.md` |
| Conclusion | What worked, what the ablations showed, limitations, future work |

## Before you submit

- [ ] Repository is public (or shared as instructed) and the link works
- [ ] Migrations are committed; `python manage.py test` passes on a fresh clone
- [ ] README setup steps work from scratch on your machine
- [ ] `LICENSE` has your name
- [ ] Evaluation numbers in the report match a saved `results.json` you can show
- [ ] Any AI assistance is declared if your university requires it

## Video (3 to 5 minutes, your own voice, not sped up)

A structure that fits the time:

1. **Purpose and demo (about 1 minute):** pick two songs, show results, open the score breakdown, change a weight, like and skip.
2. **How it works (about 1 minute):** the four similarities and the weighted blend, then variety.
3. **Code tour (about 1 minute):** `engine.py`, the recommendation view, one test.
4. **Evaluation (about 1 minute):** the comparison table, what the ablations showed, one limitation.
5. **Close (about 15 seconds):** what you would do next.

Rehearse with the app already loaded and the tests already run, so the recording is smooth.
