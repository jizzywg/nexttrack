from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .http import CachedJsonClient

API_URL = "https://musicbrainz.org/ws/2/"


@dataclass
class Recording:
    mbid: str
    title: str
    artist: str
    artist_mbid: str
    year: Optional[int]
    album: str
    score: int


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')


class MusicBrainzClient:
    def __init__(self, user_agent: str, cache_dir: Path) -> None:
        self.http = CachedJsonClient(user_agent=user_agent, cache_dir=cache_dir, min_interval=1.1)

    def find_recording(self, title: str, artist: str, min_score: int = 90) -> Optional[Recording]:
        query = f'recording:"{_escape(title)}" AND artist:"{_escape(artist)}"'
        data = self.http.get_json(API_URL + "recording", {"query": query, "fmt": "json", "limit": 5})
        wanted = artist.strip().lower()
        for raw in data.get("recordings", []):
            score = int(raw.get("score", 0))
            if score < min_score:
                continue
            credits = raw.get("artist-credit") or []
            names = {(c.get("artist") or {}).get("name", "").lower() for c in credits} | {
                c.get("name", "").lower() for c in credits
            }
            if wanted not in names:
                continue
            first = credits[0].get("artist", {}) if credits else {}
            date = raw.get("first-release-date") or ""
            year = int(date[:4]) if date[:4].isdigit() else None
            releases = raw.get("releases") or []
            return Recording(
                mbid=raw.get("id", ""),
                title=raw.get("title", title),
                artist=first.get("name", artist),
                artist_mbid=first.get("id", ""),
                year=year,
                album=releases[0].get("title", "") if releases else "",
                score=score,
            )
        return None
