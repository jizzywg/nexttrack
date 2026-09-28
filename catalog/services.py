from __future__ import annotations

import uuid
from typing import Mapping, Optional

from django.db import transaction

from .models import Artist, Genre, Track, TrackGenre
from .taxonomy import normalise_tag


def set_track_genres(track: Track, genres: Mapping[str, float]) -> None:
    cleaned: dict[str, float] = {}
    for name, weight in genres.items():
        tag = normalise_tag(name)
        if tag:
            cleaned[tag] = max(0.0, min(1.0, float(weight)))
    with transaction.atomic():
        TrackGenre.objects.filter(track=track).delete()
        rows = []
        for tag, weight in cleaned.items():
            genre, _ = Genre.objects.get_or_create(name=tag)
            rows.append(TrackGenre(track=track, genre=genre, weight=weight))
        TrackGenre.objects.bulk_create(rows)
        track.save(update_fields=["updated_at"])


def _valid_uuid(value) -> Optional[uuid.UUID]:
    if not value:
        return None
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except ValueError:
        return None


def upsert_track(
    title: str,
    artist: str,
    genres: Optional[Mapping[str, float]] = None,
    *,
    album: str = "",
    year: Optional[int] = None,
    tempo: Optional[float] = None,
    mood: str = "",
    mbid=None,
    artist_mbid=None,
    lastfm_url: str = "",
    listeners: int = 0,
    source: str = "manual",
) -> tuple[Track, bool]:
    artist_obj, _ = Artist.objects.get_or_create(name=artist.strip())
    artist_uuid = _valid_uuid(artist_mbid)
    if artist_uuid and not artist_obj.mbid and not Artist.objects.filter(mbid=artist_uuid).exists():
        artist_obj.mbid = artist_uuid
        artist_obj.save(update_fields=["mbid"])

    track_uuid = _valid_uuid(mbid)
    existing = Track.objects.filter(artist=artist_obj, title=title.strip()).first()
    if track_uuid and Track.objects.filter(mbid=track_uuid).exclude(pk=getattr(existing, "pk", None)).exists():
        track_uuid = None

    values = {
        "album": album,
        "year": year,
        "tempo": tempo,
        "mood": mood,
        "mbid": track_uuid,
        "lastfm_url": lastfm_url,
        "source": source,
    }
    defaults = {key: value for key, value in values.items() if value not in (None, "")}
    if listeners:
        defaults["listeners"] = listeners

    if existing is None:
        track = Track.objects.create(artist=artist_obj, title=title.strip(), **defaults)
        created = True
    else:
        for key, value in defaults.items():
            setattr(existing, key, value)
        existing.save()
        track, created = existing, False

    if genres:
        set_track_genres(track, genres)
    return track, created
