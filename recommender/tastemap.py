from __future__ import annotations

import math
from typing import Mapping, Sequence

from catalog.taxonomy import GENRE_PARENTS

from .engine import Recommender

FAMILY_OF_ROOT = {
    "rock": "rock", "pop": "pop", "hip hop": "hip hop", "r&b": "r&b and soul",
    "electronic": "electronic and dance", "dance": "electronic and dance",
    "jazz": "jazz and blues", "blues": "jazz and blues", "folk": "folk and country", "latin": "latin",
}
FAMILY_ORDER = [
    "rock", "pop", "electronic and dance", "r&b and soul", "hip hop",
    "jazz and blues", "folk and country", "latin", "other",
]


def genre_root(tag: str) -> str:
    seen: set[str] = set()
    while tag not in seen and GENRE_PARENTS.get(tag):
        seen.add(tag)
        tag = GENRE_PARENTS[tag][0]
    return tag


def genre_family(genres: Mapping[str, float]) -> str:
    if not genres:
        return "other"
    top = max(genres, key=genres.get)
    return FAMILY_OF_ROOT.get(genre_root(top), "other")


def distance_matrix(recommender: Recommender, ids: Sequence[int]):
    import numpy as np

    n = len(ids)
    distances = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            d = 1.0 - recommender.similarity(ids[i], ids[j]).score
            distances[i, j] = distances[j, i] = d
    return distances


def _normalise(xy):
    span = xy.max(axis=0) - xy.min(axis=0)
    span[span == 0] = 1.0
    return (xy - xy.min(axis=0)) / span


def _spread_overlaps(xy, min_gap: float, rounds: int = 80):
    import numpy as np

    for _ in range(rounds):
        diff = xy[:, None, :] - xy[None, :, :]
        dist = np.sqrt((diff ** 2).sum(axis=2))
        np.fill_diagonal(dist, np.inf)
        overlap = np.clip(min_gap - dist, 0.0, None)
        if not overlap.any():
            break
        direction = diff / np.maximum(dist, 1e-9)[..., None]
        # Keep the repulsion in final display coordinates. Renormalising after
        # this step can compress the smallest gaps below the intended minimum.
        xy = np.clip(xy + (direction * (overlap / 2)[..., None]).sum(axis=1), 0.0, 1.0)
    return xy


def layout(distances, seed: int = 7) -> list[tuple[float, float]]:
    import numpy as np

    n = len(distances)
    if n == 0:
        return []
    if n < 5:
        return [(0.5 + 0.4 * math.cos(2 * math.pi * k / n), 0.5 + 0.4 * math.sin(2 * math.pi * k / n)) if n > 1 else (0.5, 0.5)
                for k in range(n)]
    from sklearn.manifold import TSNE

    perplexity = max(2.0, min(30.0, (n - 1) / 3.0))
    xy = TSNE(n_components=2, metric="precomputed", init="random", perplexity=perplexity, random_state=seed).fit_transform(
        np.asarray(distances, dtype=float)
    )
    # Leave room at the boundary for points pushed apart by collision removal.
    xy = 0.03 + 0.94 * _normalise(xy)
    rng = np.random.default_rng(seed)
    xy = xy + rng.normal(0.0, 1e-6, xy.shape)
    # A small margin absorbs rounding and TSNE variation across sklearn builds.
    xy = _spread_overlaps(xy, min_gap=0.28 / math.sqrt(n) * 1.12, rounds=180)
    return [(round(float(x), 5), round(float(y), 5)) for x, y in xy]


def build_layout(recommender: Recommender, seed: int = 7) -> dict[int, tuple[float, float]]:
    ids = [p.id for p in recommender.profiles]
    return dict(zip(ids, layout(distance_matrix(recommender, ids), seed=seed)))
