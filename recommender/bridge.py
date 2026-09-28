from __future__ import annotations

from typing import Optional

from .engine import Recommender, TrackProfile, UnknownTrackError, Weights, explain

BEAM_WIDTH = 80


def _similarity_matrix(recommender: Recommender, ids: list[int], weights: Optional[Weights]):
    import numpy as np

    n = len(ids)
    matrix = np.full((n, n), -1.0)
    for i in range(n):
        for j in range(i + 1, n):
            score = recommender.similarity(ids[i], ids[j], weights).score
            matrix[i, j] = matrix[j, i] = score
    return matrix


def _reach_table(matrix, to_index: int, hops: int):
    import numpy as np

    n = matrix.shape[0]
    reach = [np.full(n, -1.0)]
    reach[0][to_index] = 1.0
    for _ in range(1, hops):
        prev = reach[-1]
        cur = np.minimum(matrix, prev[None, :]).max(axis=1)
        reach.append(cur)
    return reach


def build_bridge(
    recommender: Recommender,
    from_id: int,
    to_id: int,
    length: int,
    weights: Optional[Weights] = None,
) -> list[dict]:
    if length < 2:
        raise ValueError("length must be at least 2 (the two endpoints).")
    if from_id == to_id:
        raise ValueError("from_id and to_id must be different tracks.")
    if not recommender.has_track(from_id):
        raise UnknownTrackError(from_id)
    if not recommender.has_track(to_id):
        raise UnknownTrackError(to_id)

    w = (weights or Weights()).normalised()
    profiles = recommender.profiles
    ids = [p.id for p in profiles]
    artist_of = {p.id: p.artist_id for p in profiles}
    index_of = {track_id: i for i, track_id in enumerate(ids)}
    from_i, to_i = index_of[from_id], index_of[to_id]

    matrix = _similarity_matrix(recommender, ids, w)
    hops = length - 1
    reach = _reach_table(matrix, to_i, hops)

    beam = [{"path": [from_i], "min": 1.0, "sum": 0.0}]
    for step in range(1, hops):
        remaining = hops - step
        used_artists_by_path = [{artist_of[ids[i]] for i in b["path"]} for b in beam]
        next_beam = []
        for b, used_artists in zip(beam, used_artists_by_path):
            last = b["path"][-1]
            last_artist = artist_of[ids[last]]
            for x in range(len(ids)):
                if x == to_i or x in b["path"] or artist_of[ids[x]] == last_artist or reach[remaining][x] < 0:
                    continue
                hop = matrix[last, x]
                worst = min(b["min"], hop)
                next_beam.append({
                    "path": b["path"] + [x], "min": worst, "sum": b["sum"] + hop,
                    "key": min(worst, reach[remaining][x]),
                })
        if not next_beam:
            break
        next_beam.sort(key=lambda c: (-c["key"], -c["sum"]))
        beam = next_beam[:BEAM_WIDTH]

    to_artist = artist_of[to_id]
    without_clash = [b for b in beam if artist_of[ids[b["path"][-1]]] != to_artist]
    best = None
    for b in without_clash or beam:
        hop = matrix[b["path"][-1], to_i]
        candidate = {"path": b["path"] + [to_i], "min": min(b["min"], hop), "sum": b["sum"] + hop}
        if best is None or candidate["min"] > best["min"] or (candidate["min"] == best["min"] and candidate["sum"] > best["sum"]):
            best = candidate
    path_indices = best["path"] if best else [from_i, to_i]

    result = []
    for k, idx in enumerate(path_indices):
        track = profiles[idx]
        if k == 0:
            result.append({"track": track, "score": None, "contributions": None, "reasons": []})
            continue
        prev = profiles[path_indices[k - 1]]
        pair = recommender.similarity(prev.id, track.id, w)
        result.append({
            "track": track, "score": pair.score, "contributions": pair.contributions,
            "reasons": explain(prev, track, pair.similarities, pair.contributions),
        })
    return result
