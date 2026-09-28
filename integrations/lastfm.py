from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .http import CachedJsonClient, IntegrationError

API_URL = "https://ws.audioscrobbler.com/2.0/"


def _as_list(value: Any) -> list:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


@dataclass
class LastFmTrack:
    title: str
    artist: str
    mbid: str = ""
    url: str = ""
    listeners: int = 0
    playcount: int = 0
    album: str = ""
    artist_mbid: str = ""
    match: float = 0.0
    tags: list = field(default_factory=list)


class LastFmClient:
    def __init__(self, api_key: str, cache_dir: Path, user_agent: str = "NextTrack/1.0") -> None:
        if not api_key:
            raise IntegrationError("LASTFM_API_KEY is not set. Get a free key at https://www.last.fm/api/account/create")
        self.api_key = api_key
        self.http = CachedJsonClient(
            user_agent=user_agent,
            cache_dir=cache_dir,
            min_interval=0.25,
            secret_params=("api_key",),
        )

    def _call(self, method: str, **params: Any) -> dict:
        query = {"method": method, "api_key": self.api_key, "format": "json", **params}
        return self.http.get_json(API_URL, query, error_key="error")

    @staticmethod
    def _track_from(raw: dict) -> LastFmTrack:
        artist = raw.get("artist") or {}
        if isinstance(artist, str):
            artist = {"name": artist}
        return LastFmTrack(
            title=raw.get("name", ""),
            artist=artist.get("name", ""),
            mbid=raw.get("mbid", "") or "",
            url=raw.get("url", "") or "",
            listeners=_int(raw.get("listeners")),
            playcount=_int(raw.get("playcount")),
            artist_mbid=artist.get("mbid", "") or "",
            match=float(raw.get("match") or 0.0),
        )

    def tag_top_tracks(self, tag: str, limit: int = 50) -> list[LastFmTrack]:
        data = self._call("tag.getTopTracks", tag=tag, limit=limit)
        return [self._track_from(t) for t in _as_list((data.get("tracks") or {}).get("track"))]

    def track_top_tags(self, artist: str, title: str) -> list[tuple[str, int]]:
        data = self._call("track.getTopTags", artist=artist, track=title, autocorrect=1)
        return [(t.get("name", ""), _int(t.get("count"))) for t in _as_list((data.get("toptags") or {}).get("tag"))]

    def track_info(self, artist: str, title: str) -> Optional[LastFmTrack]:
        data = self._call("track.getInfo", artist=artist, track=title, autocorrect=1)
        raw = data.get("track")
        if not raw:
            return None
        track = self._track_from(raw)
        track.album = (raw.get("album") or {}).get("title", "") or ""
        return track

    def similar_tracks(self, artist: str, title: str, limit: int = 20) -> list[LastFmTrack]:
        data = self._call("track.getSimilar", artist=artist, track=title, limit=limit, autocorrect=1)
        return [self._track_from(t) for t in _as_list((data.get("similartracks") or {}).get("track"))]
