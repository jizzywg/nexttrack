from __future__ import annotations

import random
import threading
from typing import Optional

from django.db.models import Count, Max

from catalog.models import Track, TrackGenre

from .engine import Recommender, TrackProfile
from .evaluation import build_strategies, evaluate
from .models import Feedback, ReferenceSimilarity

_lock = threading.Lock()
_state: dict = {"signature": None, "recommender": None}


def _load_profiles() -> list[TrackProfile]:
    tracks = Track.objects.select_related("artist").prefetch_related("trackgenre_set__genre")
    profiles = []
    for track in tracks:
        genres = {tg.genre.name: tg.weight for tg in track.trackgenre_set.all()}
        profiles.append(
            TrackProfile(
                id=track.id,
                title=track.title,
                artist=track.artist.name,
                artist_id=track.artist_id,
                genres=genres,
                mood=track.mood or None,
                tempo=track.tempo,
                year=track.year,
                popularity=track.listeners,
                artist_image=track.artist.image_url or "",
                youtube_id=track.youtube_id or "",
            )
        )
    return profiles


def _signature() -> tuple:
    agg = Track.objects.aggregate(n=Count("id"), latest=Max("updated_at"))
    return (agg["n"], agg["latest"], TrackGenre.objects.count())


def invalidate_recommender() -> None:
    with _lock:
        _state["signature"] = None


def get_recommender() -> Recommender:
    signature = _signature()
    with _lock:
        if _state["recommender"] is None or _state["signature"] != signature:
            _state["recommender"] = Recommender(_load_profiles())
            _state["signature"] = signature
        return _state["recommender"]


def feedback_identity(request) -> Optional[dict]:
    if getattr(request, "user", None) is not None and request.user.is_authenticated:
        return {"user": request.user}
    session_key = request.session.session_key if hasattr(request, "session") else None
    return {"user": None, "session_key": session_key} if session_key else None


def feedback_sets(request, limit: int = 300) -> tuple[list[int], list[int]]:
    identity = feedback_identity(request)
    if identity is None:
        return [], []
    rows = Feedback.objects.filter(**identity).order_by("-updated_at")[:limit]
    liked = [f.track_id for f in rows if f.value == Feedback.LIKE]
    skipped = [f.track_id for f in rows if f.value == Feedback.SKIP]
    return liked, skipped


def load_reference(source: str = "lastfm") -> dict[int, dict[int, float]]:
    reference: dict[int, dict[int, float]] = {}
    rows = ReferenceSimilarity.objects.filter(source=source).values_list("track_id", "similar_id", "match")
    for track_id, similar_id, match in rows:
        reference.setdefault(track_id, {})[similar_id] = match
    return reference


def build_evaluation(k: int = 10, sample: int = 60, rng_seed: int = 42) -> dict:
    rec = get_recommender()
    reference = {t: r for t, r in load_reference().items() if t in rec}
    popularity_available = any(p.popularity > 0 for p in rec.profiles)

    rng = random.Random(rng_seed)
    ids = [p.id for p in rec.profiles]
    if reference:
        candidates = [t for t in reference if any(r in rec for r in reference[t])]
    else:
        candidates = ids
    seeds = rng.sample(candidates, min(sample, len(candidates))) if candidates else []

    rows = []
    if seeds and len(rec) > k:
        strategies = build_strategies(rec, k, rng_seed=rng_seed, popularity_available=popularity_available)
        rows = evaluate(rec, strategies, seeds, k, reference=reference, rng_seed=rng_seed)

    notes = []
    if not reference:
        notes.append(
            "No reference data loaded, so accuracy metrics are unavailable. Run "
            "`python manage.py import_lastfm --tag rock --similar` (needs a Last.fm API key) to load "
            "Last.fm similar-track lists as ground truth."
        )
    if not popularity_available:
        notes.append("No popularity data (Last.fm listeners) yet, so novelty and the popularity baseline are skipped.")
    if len(rec) <= k:
        notes.append("The catalogue is smaller than k; add more tracks to evaluate.")

    return {
        "k": k,
        "sample": len(seeds),
        "catalogue_size": len(rec),
        "ground_truth": {
            "available": bool(reference),
            "seeds_with_reference": len(reference),
            "pairs": sum(len(v) for v in reference.values()),
            "source": "Last.fm track.getSimilar" if reference else None,
        },
        "popularity_available": popularity_available,
        "strategies": rows,
        "notes": notes,
    }
