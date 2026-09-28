from __future__ import annotations

import time
from typing import Iterable, Mapping, Optional

from .engine import FEATURES, Recommendation, Recommender, TrackProfile, Weights

LIKED_SEED_WEIGHT = 0.5
MAX_LIKED_SEEDS = 5
RECENCY_WEIGHTS = (1.0, 0.6, 0.35)


def bridge_payload(recommender, from_id: int, to_id: int, length: int, weights=None) -> dict:
    from .bridge import build_bridge

    weight_obj = Weights.from_mapping(weights) if weights else Weights()
    started = time.perf_counter()
    hops = build_bridge(recommender, from_id, to_id, length, weight_obj.normalised())
    return {
        "path": [
            {
                "track": track_payload(hop["track"]),
                "score": hop["score"],
                "contributions": hop["contributions"],
                "reasons": hop["reasons"],
            }
            for hop in hops
        ],
        "took_ms": round((time.perf_counter() - started) * 1000, 1),
        "weights": weight_obj.as_dict(),
    }


def history_seeds(history: Iterable[int]) -> list[tuple[int, float]]:
    newest_first = list(dict.fromkeys(reversed(list(history))))
    return list(zip(newest_first, RECENCY_WEIGHTS))


def track_payload(profile: TrackProfile) -> dict:
    genres = sorted(profile.genres.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        "id": profile.id,
        "title": profile.title,
        "artist": profile.artist,
        "artist_id": profile.artist_id,
        "artist_image": profile.artist_image or None,
        "youtube_id": profile.youtube_id or None,
        "year": profile.year,
        "decade": f"{profile.decade}s" if profile.decade is not None else None,
        "tempo": round(profile.tempo, 1) if profile.tempo else None,
        "mood": profile.mood,
        "genres": [{"name": name, "weight": round(weight, 2)} for name, weight in genres],
        "listeners": profile.popularity,
    }


def _rounded(mapping: Mapping[str, Optional[float]]) -> dict:
    return {name: (None if mapping.get(name) is None else round(mapping[name], 4)) for name in FEATURES}


def recommendation_payload(rank: int, rec: Recommendation, seed_lookup: Mapping[int, TrackProfile]) -> dict:
    because = seed_lookup.get(rec.because_id)
    return {
        "rank": rank,
        "score": round(rec.score, 4),
        "match": round(rec.score * 100),
        "track": track_payload(rec.profile),
        "similarities": _rounded(rec.similarities),
        "contributions": _rounded(rec.contributions),
        "because": {"id": because.id, "title": because.title, "artist": because.artist} if because else None,
        "reasons": list(rec.reasons),
        "penalty": round(rec.penalty, 4),
    }


def run_recommendation(
    recommender: Recommender,
    *,
    seeds: Iterable[int],
    k: int = 10,
    weights: Optional[Mapping[str, float]] = None,
    aggregate: str = "mean",
    diversity: float = 0.25,
    max_per_artist: int = 2,
    exclude: Iterable[int] = (),
    liked: Iterable[int] = (),
    disliked: Iterable[int] = (),
    history: Iterable[int] = (),
) -> dict:
    seed_ids = list(dict.fromkeys(seeds))
    history_ids = [i for i in history if i in recommender]
    recent = history_seeds(history_ids)
    seed_weights = {i: 1.0 for i in seed_ids}
    for i, weight in recent:
        seed_weights[i] = max(seed_weights.get(i, 0.0), weight)
    liked_ids = [i for i in dict.fromkeys(liked) if i not in seed_weights and i in recommender][:MAX_LIKED_SEEDS]
    disliked_ids = [i for i in dict.fromkeys(disliked) if i in recommender and i not in seed_weights]

    weight_obj = Weights.from_mapping(weights) if weights else Weights()
    normalised = weight_obj.normalised()

    started = time.perf_counter()
    results = recommender.recommend(
        list(seed_weights.items()) + [(i, LIKED_SEED_WEIGHT) for i in liked_ids],
        k=k,
        weights=weight_obj,
        aggregate=aggregate,
        diversity=diversity,
        max_per_artist=max_per_artist,
        exclude=set(exclude) | set(history_ids),
        disliked=disliked_ids,
    )
    took_ms = (time.perf_counter() - started) * 1000.0

    lookup = {i: recommender.get(i) for i in list(seed_weights) + liked_ids}
    return {
        "seeds": [track_payload(recommender.get(i)) for i in seed_ids],
        "history_used": [{"track": track_payload(recommender.get(i)), "weight": weight} for i, weight in recent],
        "liked_used": [track_payload(recommender.get(i)) for i in liked_ids],
        "weights": {name: round(value, 4) for name, value in normalised.as_dict().items()},
        "options": {
            "k": k,
            "aggregate": aggregate,
            "diversity": diversity,
            "max_per_artist": max_per_artist,
            "history_length": len(history_ids),
        },
        "count": len(results),
        "took_ms": round(took_ms, 2),
        "results": [recommendation_payload(n, r, lookup) for n, r in enumerate(results, start=1)],
    }
