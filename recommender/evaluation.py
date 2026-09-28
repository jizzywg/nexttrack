from __future__ import annotations

import math
import random
import statistics
import time
from typing import Callable, Iterable, Mapping, Optional, Sequence

from .engine import FEATURES, Recommender, Weights


def precision_at_k(recs: Sequence[int], relevant: Iterable[int], k: int) -> float:
    relevant = set(relevant)
    return sum(1 for r in recs[:k] if r in relevant) / k


def recall_at_k(recs: Sequence[int], relevant: Iterable[int], k: int) -> float:
    relevant = set(relevant)
    if not relevant:
        return 0.0
    return sum(1 for r in recs[:k] if r in relevant) / len(relevant)


def hit_rate_at_k(recs: Sequence[int], relevant: Iterable[int], k: int) -> float:
    relevant = set(relevant)
    return 1.0 if any(r in relevant for r in recs[:k]) else 0.0


def ndcg_at_k(recs: Sequence[int], relevance: Mapping[int, float], k: int) -> float:
    dcg = sum(relevance.get(r, 0.0) / math.log2(i + 2) for i, r in enumerate(recs[:k]))
    ideal = sorted(relevance.values(), reverse=True)[:k]
    idcg = sum(v / math.log2(i + 2) for i, v in enumerate(ideal))
    return dcg / idcg if idcg > 0 else 0.0


def catalogue_coverage(rec_lists: Iterable[Sequence[int]], catalogue_size: int) -> float:
    if catalogue_size <= 0:
        return 0.0
    seen = set()
    for recs in rec_lists:
        seen.update(recs)
    return len(seen) / catalogue_size


def intra_list_diversity(ids: Sequence[int], similarity: Callable[[int, int], float]) -> float:
    if len(ids) < 2:
        return 0.0
    sims = [similarity(a, b) for i, a in enumerate(ids) for b in ids[i + 1:]]
    return 1.0 - sum(sims) / len(sims)


def novelty(ids: Sequence[int], popularity: Mapping[int, int], catalogue_size: int) -> float:
    total = sum(popularity.values())
    if not ids or total <= 0:
        return 0.0
    values = []
    for i in ids:
        p = (popularity.get(i, 0) + 1) / (total + catalogue_size)
        values.append(-math.log2(p))
    return sum(values) / len(values)


def bootstrap_ci(values: Sequence[float], *, n_boot: int = 1000, rng_seed: int = 0) -> tuple[float, float, float]:
    if not values:
        return (0.0, 0.0, 0.0)
    mean = statistics.fmean(values)
    if len(values) < 2:
        return (mean, mean, mean)
    rng = random.Random(rng_seed)
    n = len(values)
    means = sorted(statistics.fmean(rng.choices(values, k=n)) for _ in range(n_boot))
    return (mean, means[int(0.025 * n_boot)], means[int(0.975 * n_boot) - 1])


Strategy = Callable[[int], Sequence[int]]


def build_strategies(
    rec: Recommender,
    k: int,
    *,
    rng_seed: int = 0,
    popularity_available: bool = False,
) -> dict[str, Strategy]:
    def model(weights: Weights, diversity: float = 0.0, max_per_artist: Optional[int] = None) -> Strategy:
        cap = max_per_artist or k
        return lambda seed: [
            r.profile.id
            for r in rec.recommend([seed], k=k, weights=weights, diversity=diversity, max_per_artist=cap)
        ]

    default = Weights()
    strategies: dict[str, Strategy] = {
        "NextTrack (all features)": model(default),
        "NextTrack + variety (MMR 0.25, max 2 per artist)": model(default, 0.25, 2),
    }
    labels = {"genre": "genre", "mood": "mood", "tempo": "tempo", "decade": "decade"}
    for feature in FEATURES:
        weights = Weights.from_mapping({f: getattr(default, f) for f in FEATURES if f != feature})
        strategies[f"Without {labels[feature]}"] = model(weights)
    strategies["Genre only"] = model(Weights.from_mapping({"genre": 1.0}))

    ids = [p.id for p in rec.profiles]
    rng = random.Random(rng_seed)

    def random_baseline(seed: int) -> list[int]:
        pool = [i for i in ids if i != seed]
        return rng.sample(pool, min(k, len(pool)))

    strategies["Random"] = random_baseline

    if popularity_available:
        by_popularity = [p.id for p in sorted(rec.profiles, key=lambda p: (-p.popularity, p.id))]
        strategies["Most popular"] = lambda seed: [i for i in by_popularity if i != seed][:k]
    return strategies


def _stat(values: Sequence[float], rng_seed: int) -> dict:
    mean, lo, hi = bootstrap_ci(values, rng_seed=rng_seed)
    return {"mean": round(mean, 4), "ci": [round(lo, 4), round(hi, 4)]}


def evaluate(
    rec: Recommender,
    strategies: Mapping[str, Strategy],
    seeds: Sequence[int],
    k: int,
    *,
    reference: Optional[Mapping[int, Mapping[int, float]]] = None,
    rng_seed: int = 0,
) -> list[dict]:
    popularity = {p.id: p.popularity for p in rec.profiles}
    has_popularity = sum(popularity.values()) > 0
    reference = reference or {}
    rows = []
    for name, strategy in strategies.items():
        lists, latencies = [], []
        for seed in seeds:
            started = time.perf_counter()
            lists.append(list(strategy(seed))[:k])
            latencies.append((time.perf_counter() - started) * 1000.0)

        row: dict = {
            "name": name,
            "n_seeds": len(seeds),
            "n_scored": 0,
            "precision": None,
            "recall": None,
            "hit_rate": None,
            "ndcg": None,
        }
        p_vals, r_vals, h_vals, n_vals = [], [], [], []
        for seed, recs in zip(seeds, lists):
            relevance = {
                rid: m for rid, m in reference.get(seed, {}).items() if rid != seed and rid in rec
            }
            if not relevance:
                continue
            p_vals.append(precision_at_k(recs, relevance, k))
            r_vals.append(recall_at_k(recs, relevance, k))
            h_vals.append(hit_rate_at_k(recs, relevance, k))
            n_vals.append(ndcg_at_k(recs, relevance, k))
        if p_vals:
            row["n_scored"] = len(p_vals)
            row["precision"] = _stat(p_vals, rng_seed)
            row["recall"] = _stat(r_vals, rng_seed)
            row["hit_rate"] = _stat(h_vals, rng_seed)
            row["ndcg"] = _stat(n_vals, rng_seed)

        diversities = [
            intra_list_diversity(recs, lambda a, b: rec.similarity(a, b).score) for recs in lists if len(recs) > 1
        ]
        row["coverage"] = round(catalogue_coverage(lists, len(rec)), 4)
        row["diversity"] = _stat(diversities, rng_seed) if diversities else None
        row["novelty"] = (
            _stat([novelty(recs, popularity, len(rec)) for recs in lists if recs], rng_seed)
            if has_popularity
            else None
        )
        row["latency_ms"] = round(statistics.fmean(latencies), 2) if latencies else 0.0
        rows.append(row)
    return rows
