from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .http import CachedJsonClient, IntegrationError

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"


@dataclass
class YouTubeVideo:
    video_id: str
    title: str = ""
    channel: str = ""


class YouTubeClient:
    def __init__(self, api_key: str, cache_dir: Path, user_agent: str = "NextTrack/1.0") -> None:
        if not api_key:
            raise IntegrationError(
                "YOUTUBE_API_KEY is not set. Create a YouTube Data API v3 key in the Google Cloud console."
            )
        self.api_key = api_key
        self.http = CachedJsonClient(
            user_agent=user_agent, cache_dir=cache_dir, min_interval=0.2, secret_params=("key",)
        )

    def find_video(self, artist: str, title: str) -> Optional[YouTubeVideo]:
        query = f"{artist} {title}".strip()
        if not query:
            return None
        data = self.http.get_json(
            SEARCH_URL,
            {
                "part": "snippet",
                "q": query,
                "type": "video",
                "videoEmbeddable": "true",
                "maxResults": 1,
                "key": self.api_key,
            },
        )
        for item in data.get("items") or []:
            video_id = (item.get("id") or {}).get("videoId")
            if video_id:
                snippet = item.get("snippet") or {}
                return YouTubeVideo(video_id, snippet.get("title", ""), snippet.get("channelTitle", ""))
        return None
