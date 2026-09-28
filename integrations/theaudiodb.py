from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .http import CachedJsonClient

API_URL = "https://www.theaudiodb.com/api/v1/json/"
SHARED_TEST_KEY = "123"


@dataclass
class ArtistImage:
    name: str
    thumb_url: str
    mbid: str = ""
    bio: str = ""


def _first_artist(data: dict) -> Optional[dict]:
    artists = data.get("artists")
    return artists[0] if artists else None


class TheAudioDbClient:
    def __init__(self, api_key: str, cache_dir: Path, user_agent: str = "NextTrack/1.0") -> None:
        self.api_key = api_key or SHARED_TEST_KEY
        self.http = CachedJsonClient(user_agent=user_agent, cache_dir=cache_dir, min_interval=2.1)

    def _base(self) -> str:
        return f"{API_URL}{self.api_key}/"

    def artist_by_mbid(self, mbid: str) -> Optional[ArtistImage]:
        if not mbid:
            return None
        data = self.http.get_json(self._base() + "artist-mb.php", {"i": mbid})
        raw = _first_artist(data)
        return self._image_from(raw) if raw else None

    def artist_by_name(self, name: str) -> Optional[ArtistImage]:
        if not name.strip():
            return None
        data = self.http.get_json(self._base() + "search.php", {"s": name})
        raw = _first_artist(data)
        return self._image_from(raw) if raw else None

    @staticmethod
    def _image_from(raw: dict) -> Optional[ArtistImage]:
        thumb = raw.get("strArtistThumb") or ""
        bio = (raw.get("strBiographyEN") or "").strip()
        if not thumb and not bio:
            return None
        return ArtistImage(
            name=raw.get("strArtist", ""), thumb_url=thumb, mbid=raw.get("strMusicBrainzID", "") or "", bio=bio
        )
