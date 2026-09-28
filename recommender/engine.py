from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Sequence, Union

from catalog.taxonomy import GENRE_PARENTS, MOODS, normalise_tag

FEATURES = ("genre", "mood", "tempo", "decade")
DEFAULT_WEIGHTS = {"genre": 0.45, "mood": 0.25, "tempo": 0.15, "decade": 0.15}


class UnknownTrackError(KeyError):
    pass


@dataclass(frozen=True, eq=False)
class TrackProfile:
    id: int
    title: str
    artist: str
    artist_id: int
    genres: Mapping[str, float]
    mood: Optional[str] = None
    tempo: Optional[float] = None
    year: Optional[int] = None
    popularity: int = 0
    artist_image: str = ""
    youtube_id: str = ""

    @property
    def decade(self) -> Optional[int]:
        return None if self.year is None else (self.year // 10) * 10


@dataclass(frozen=True)
class Weights:
    genre: float = DEFAULT_WEIGHTS["genre"]
    mood: float = DEFAULT_WEIGHTS["mood"]
    tempo: float = DEFAULT_WEIGHTS["tempo"]
    decade: float = DEFAULT_WEIGHTS["decade"]

    def __post_init__(self) -> None:
        for name in FEATURES:
            value = getattr(self, name)
            if math.isnan(value) or value < 0:
                raise ValueError(f"Weight '{name}' must be a number >= 0.")

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, float]) -> "Weights":
        unknown = set(mapping) - set(FEATURES)
        if unknown:
            raise ValueError(f"Unknown feature(s): {', '.join(sorted(unknown))}")
        return cls(**{name: float(mapping.get(name, 0.0)) for name in FEATURES})

    def total(self) -> float:
        return sum(getattr(self, name) for name in FEATURES)

    def normalised(self) -> "Weights":
        total = self.total()
        if total <= 0:
            raise ValueError("At least one weight must be greater than zero.")
        return Weights(*(getattr(self, name) / total for name in FEATURES))

    def as_dict(self) -> dict[str, float]:
        return {name: getattr(self, name) for name in FEATURES}


@dataclass(frozen=True)
class PairScore:
    score: float
    similarities: dict
    contributions: dict


@dataclass(frozen=True, eq=False)
class Recommendation:
    profile: TrackProfile
    score: float
    similarities: dict
    contributions: dict
    because_id: int
    reasons: list
    penalty: float = 0.0


def expand_genres(
    genres: Mapping[str, float], parent_factor: float = 0.5, max_depth: int = 3
) -> dict[str, float]:
    out: dict[str, float] = {}
    for tag, weight in genres.items():
        frontier = [(normalise_tag(tag), float(weight))]
        for _ in range(max_depth + 1):
            following = []
            for name, w in frontier:
                if w <= 0:
                    continue
                if w > out.get(name, 0.0):
                    out[name] = w
                for parent in GENRE_PARENTS.get(name, ()):
                    following.append((parent, w * parent_factor))
            frontier = following
            if not frontier:
                break
    return out


def _dot(a: Mapping[str, float], b: Mapping[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b[k] for k, v in a.items() if k in b)


def cosine(a: Mapping[str, float], norm_a: float, b: Mapping[str, float], norm_b: float) -> Optional[float]:
    if norm_a <= 0 or norm_b <= 0:
        return None
    return max(0.0, min(1.0, _dot(a, b) / (norm_a * norm_b)))


def mood_similarity(a: Optional[str], b: Optional[str], sigma: float = 0.75) -> Optional[float]:
    if a not in MOODS or b not in MOODS:
        return None
    (v1, a1), (v2, a2) = MOODS[a], MOODS[b]
    d2 = (v1 - v2) ** 2 + (a1 - a2) ** 2
    return math.exp(-d2 / (2 * sigma * sigma))


def tempo_similarity(
    a: Optional[float], b: Optional[float], sigma: float = 0.12, octave_penalty: float = 0.2
) -> Optional[float]:
    if not a or not b or a <= 0 or b <= 0:
        return None
    base = abs(math.log2(a / b))
    distance = min(base, abs(base - 1.0) + octave_penalty)
    return math.exp(-(distance * distance) / (2 * sigma * sigma))


def decade_similarity(y1: Optional[int], y2: Optional[int], sigma: float = 12.0) -> Optional[float]:
    if y1 is None or y2 is None:
        return None
    d = y1 - y2
    return math.exp(-(d * d) / (2 * sigma * sigma))


@dataclass(eq=False)
class _Item:
    profile: TrackProfile
    vec: dict
    norm: float


@dataclass(eq=False)
class _Scored:
    item: _Item
    score: float
    similarities: dict
    contributions: dict
    because: _Item
    penalty: float


SeedInput = Union[int, tuple]


class Recommender:
    def __init__(
        self,
        profiles: Iterable[TrackProfile],
        *,
        parent_factor: float = 0.5,
        use_idf: bool = True,
        missing_penalty: float = 0.1,
    ) -> None:
        self.missing_penalty = missing_penalty
        profiles = list(profiles)
        ids = [p.id for p in profiles]
        if len(ids) != len(set(ids)):
            raise ValueError("Track ids must be unique.")

        expanded = [expand_genres(dict(p.genres), parent_factor) for p in profiles]
        n = len(profiles)
        document_frequency = Counter(tag for e in expanded for tag in e)
        idf = (
            {tag: math.log((1 + n) / (1 + df)) + 1.0 for tag, df in document_frequency.items()}
            if use_idf
            else {}
        )
        self._items: list[_Item] = []
        for profile, exp in zip(profiles, expanded):
            vec = {tag: w * idf.get(tag, 1.0) for tag, w in exp.items()}
            norm = math.sqrt(sum(v * v for v in vec.values()))
            self._items.append(_Item(profile, vec, norm))
        self._by_id = {item.profile.id: item for item in self._items}
        self.idf = idf

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, track_id: int) -> bool:
        return track_id in self._by_id

    def has_track(self, track_id: int) -> bool:
        return track_id in self._by_id

    def get(self, track_id: int) -> TrackProfile:
        try:
            return self._by_id[track_id].profile
        except KeyError:
            raise UnknownTrackError(track_id) from None

    @property
    def profiles(self) -> list[TrackProfile]:
        return [item.profile for item in self._items]

    def _pair(self, a: _Item, b: _Item, w: Weights) -> PairScore:
        pa, pb = a.profile, b.profile
        sims = {
            "genre": cosine(a.vec, a.norm, b.vec, b.norm),
            "mood": mood_similarity(pa.mood, pb.mood),
            "tempo": tempo_similarity(pa.tempo, pb.tempo),
            "decade": decade_similarity(pa.year, pb.year),
        }
        total_weight = w.total()
        available = 0.0
        numerator = 0.0
        for name in FEATURES:
            sim, weight = sims[name], getattr(w, name)
            if sim is None or weight <= 0:
                continue
            available += weight
            numerator += weight * sim
        if available <= 0 or total_weight <= 0:
            return PairScore(0.0, sims, {name: 0.0 for name in FEATURES})
        coverage = available / total_weight
        factor = 1.0 - self.missing_penalty * (1.0 - coverage)
        contributions = {}
        for name in FEATURES:
            sim, weight = sims[name], getattr(w, name)
            contributions[name] = (
                weight * sim / available * factor if sim is not None and weight > 0 else 0.0
            )
        return PairScore(sum(contributions.values()), sims, contributions)

    def similarity(self, id_a: int, id_b: int, weights: Optional[Weights] = None) -> PairScore:
        w = (weights or Weights()).normalised()
        return self._pair(self._item(id_a), self._item(id_b), w)

    def _item(self, track_id: int) -> _Item:
        try:
            return self._by_id[track_id]
        except KeyError:
            raise UnknownTrackError(track_id) from None

    def recommend(
        self,
        seeds: Sequence[SeedInput],
        *,
        k: int = 10,
        weights: Optional[Weights] = None,
        aggregate: str = "mean",
        diversity: float = 0.25,
        max_per_artist: int = 2,
        exclude: Iterable[int] = (),
        disliked: Iterable[int] = (),
        dislike_penalty: float = 0.25,
        pool_factor: int = 6,
    ) -> list[Recommendation]:
        if k < 1:
            raise ValueError("k must be at least 1.")
        if aggregate not in ("mean", "max"):
            raise ValueError("aggregate must be 'mean' or 'max'.")
        if not 0.0 <= diversity <= 1.0:
            raise ValueError("diversity must be between 0 and 1.")
        if max_per_artist < 1:
            raise ValueError("max_per_artist must be at least 1.")
        w = (weights or Weights()).normalised()

        seed_weights: dict[int, float] = {}
        for seed in seeds:
            sid, sweight = seed if isinstance(seed, tuple) else (seed, 1.0)
            if sweight <= 0:
                continue
            self._item(sid)
            seed_weights[sid] = max(seed_weights.get(sid, 0.0), float(sweight))
        if not seed_weights:
            raise ValueError("At least one seed track is required.")
        seed_items = [(self._by_id[sid], sw) for sid, sw in seed_weights.items()]
        seed_weight_sum = sum(sw for _, sw in seed_items)

        disliked_items = [self._by_id[d] for d in set(disliked) if d in self._by_id]
        blocked = set(seed_weights) | set(exclude) | {i.profile.id for i in disliked_items}

        scored: list[_Scored] = []
        for cand in self._items:
            if cand.profile.id in blocked:
                continue
            pairs = [(self._pair(seed, cand, w), sw, seed) for seed, sw in seed_items]
            best_pair, _, best_seed = max(pairs, key=lambda t: (t[0].score, -t[2].profile.id))
            if aggregate == "max":
                score = best_pair.score
                contributions = best_pair.contributions
                sims = best_pair.similarities
            else:
                score = sum(p.score * sw for p, sw, _ in pairs) / seed_weight_sum
                contributions = {
                    name: sum(p.contributions[name] * sw for p, sw, _ in pairs) / seed_weight_sum
                    for name in FEATURES
                }
                sims = {}
                for name in FEATURES:
                    vals = [(p.similarities[name], sw) for p, sw, _ in pairs if p.similarities[name] is not None]
                    total = sum(sw for _, sw in vals)
                    sims[name] = sum(v * sw for v, sw in vals) / total if total else None
            penalty = 0.0
            if disliked_items:
                penalty = dislike_penalty * max(self._pair(cand, d, w).score for d in disliked_items)
                score = max(0.0, score - penalty)
            scored.append(_Scored(cand, score, sims, contributions, best_seed, penalty))

        scored.sort(key=lambda s: (-s.score, s.item.profile.id))
        pool = scored[: max(k * pool_factor, 50)]
        chosen = self._rerank(pool, k, w, diversity, max_per_artist)

        results = []
        for s in chosen:
            reasons = explain(s.because.profile, s.item.profile, s.similarities, s.contributions)
            results.append(
                Recommendation(
                    profile=s.item.profile,
                    score=s.score,
                    similarities=s.similarities,
                    contributions=s.contributions,
                    because_id=s.because.profile.id,
                    reasons=reasons,
                    penalty=s.penalty,
                )
            )
        return results

    def _rerank(self, pool, k, w, diversity, max_per_artist):
        selected: list[_Scored] = []
        per_artist: Counter = Counter()
        remaining = list(pool)
        cache: dict = {}

        def pair_score(x: _Item, y: _Item) -> float:
            key = (x.profile.id, y.profile.id) if x.profile.id < y.profile.id else (y.profile.id, x.profile.id)
            if key not in cache:
                cache[key] = self._pair(x, y, w).score
            return cache[key]

        while remaining and len(selected) < k:
            best, best_value = None, -math.inf
            for cand in remaining:
                if per_artist[cand.item.profile.artist_id] >= max_per_artist:
                    continue
                redundancy = max((pair_score(cand.item, s.item) for s in selected), default=0.0)
                value = (1.0 - diversity) * cand.score - diversity * redundancy
                if value > best_value:
                    best, best_value = cand, value
            if best is None:
                break
            selected.append(best)
            per_artist[best.item.profile.artist_id] += 1
            remaining.remove(best)
        return selected


def _join(names: Sequence[str]) -> str:
    return " and ".join(names)


def explain(seed: TrackProfile, cand: TrackProfile, sims: Mapping, contributions: Mapping) -> list[str]:
    reasons: list[tuple[float, str]] = []

    seed_tags = {normalise_tag(t) for t in seed.genres}
    shared = [
        t for t, _ in sorted(cand.genres.items(), key=lambda kv: -kv[1]) if normalise_tag(t) in seed_tags
    ][:2]
    if shared:
        reasons.append((contributions.get("genre", 0.0), f"Both tagged {_join(shared)}"))
    elif (sims.get("genre") or 0.0) >= 0.25 and cand.genres and seed.genres:
        top_c = max(cand.genres, key=cand.genres.get)
        top_s = max(seed.genres, key=seed.genres.get)
        reasons.append((contributions.get("genre", 0.0), f"Related genres ({top_c} and {top_s})"))

    if sims.get("mood") is not None and cand.mood and seed.mood:
        if cand.mood == seed.mood:
            reasons.append((contributions.get("mood", 0.0), f"Same {cand.mood} mood"))
        elif sims["mood"] >= 0.5:
            article = "An" if cand.mood[0].lower() in "aeiou" else "A"
            reasons.append((contributions.get("mood", 0.0), f"{article} {cand.mood} mood close to {seed.mood}"))

    if sims.get("tempo") is not None and cand.tempo and seed.tempo:
        ratio = cand.tempo / seed.tempo
        if sims["tempo"] >= 0.6:
            reasons.append(
                (contributions.get("tempo", 0.0), f"Similar tempo ({cand.tempo:.0f} vs {seed.tempo:.0f} BPM)")
            )
        elif abs(math.log2(ratio)) > 0.85 and abs(abs(math.log2(ratio)) - 1.0) < 0.1:
            reasons.append(
                (contributions.get("tempo", 0.0), f"Half/double-time feel ({cand.tempo:.0f} vs {seed.tempo:.0f} BPM)")
            )

    if cand.year is not None and seed.year is not None:
        if cand.decade == seed.decade:
            reasons.append((contributions.get("decade", 0.0), f"Both from the {cand.decade}s"))
        elif abs(cand.year - seed.year) <= 10:
            reasons.append((contributions.get("decade", 0.0), f"Neighbouring era ({cand.year} vs {seed.year})"))

    reasons.sort(key=lambda r: -r[0])
    return [text for _, text in reasons[:3]]


def profiles_from_rows(rows: Iterable[Mapping], start_id: int = 1) -> list[TrackProfile]:
    artist_ids: dict[str, int] = {}
    profiles = []
    for offset, row in enumerate(rows):
        artist_id = artist_ids.setdefault(row["artist"], len(artist_ids) + 1)
        profiles.append(
            TrackProfile(
                id=start_id + offset,
                title=row["title"],
                artist=row["artist"],
                artist_id=artist_id,
                genres=dict(row.get("genres") or {}),
                mood=row.get("mood") or None,
                tempo=row.get("tempo"),
                year=row.get("year"),
                popularity=int(row.get("listeners") or 0),
            )
        )
    return profiles
