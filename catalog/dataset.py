from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional, Union

from .taxonomy import MOODS, normalise_tag

DEMO_CSV = Path(__file__).resolve().parent / "data" / "demo_tracks.csv"


def parse_genres(text: Optional[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for part in (text or "").split(";"):
        part = part.strip()
        if not part:
            continue
        name, _, weight = part.partition(":")
        tag = normalise_tag(name)
        if not tag:
            continue
        try:
            value = float(weight) if weight.strip() else 1.0
        except ValueError:
            raise ValueError(f"Bad genre weight in {part!r}") from None
        out[tag] = max(0.0, min(1.0, value))
    return out


def _number(text: Optional[str], cast, label: str, line: int):
    text = (text or "").strip()
    if not text:
        return None
    try:
        return cast(text)
    except ValueError:
        raise ValueError(f"Line {line}: {label} {text!r} is not a valid number") from None


def read_track_rows(path: Union[str, Path]) -> list[dict]:
    rows: list[dict] = []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = {"title", "artist"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV is missing required column(s): {', '.join(sorted(missing))}")
        for line, raw in enumerate(reader, start=2):
            title = (raw.get("title") or "").strip()
            artist = (raw.get("artist") or "").strip()
            if not title or not artist:
                continue
            mood = (raw.get("mood") or "").strip().lower()
            if mood and mood not in MOODS:
                raise ValueError(
                    f"Line {line}: unknown mood {mood!r}. Valid moods: {', '.join(MOODS)}"
                )
            year = _number(raw.get("year"), int, "year", line)
            tempo = _number(raw.get("tempo"), float, "tempo", line)
            if year is not None and not 1900 <= year <= 2100:
                raise ValueError(f"Line {line}: year {year} is outside 1900-2100")
            if tempo is not None and not 30 <= tempo <= 300:
                raise ValueError(f"Line {line}: tempo {tempo} is outside 30-300 BPM")
            rows.append(
                {
                    "title": title,
                    "artist": artist,
                    "album": (raw.get("album") or "").strip(),
                    "year": year,
                    "tempo": tempo,
                    "mood": mood,
                    "genres": parse_genres(raw.get("genres")),
                    "listeners": _number(raw.get("listeners"), int, "listeners", line) or 0,
                }
            )
    return rows
