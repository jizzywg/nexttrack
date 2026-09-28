from __future__ import annotations

import re
from typing import Iterable, Mapping, Optional, Union

MOODS: dict[str, tuple[float, float]] = {
    "euphoric": (0.8, 0.8),
    "energetic": (0.4, 0.9),
    "happy": (0.9, 0.3),
    "romantic": (0.6, -0.2),
    "chill": (0.3, -0.7),
    "melancholic": (-0.6, -0.4),
    "dark": (-0.7, 0.3),
    "aggressive": (-0.6, 0.9),
}
MOOD_CHOICES = [(name, name.title()) for name in MOODS]

MOOD_LEXICON: dict[str, str] = {
    "chill": "chill", "chillout": "chill", "relax": "chill", "relaxing": "chill",
    "mellow": "chill", "laid back": "chill", "calm": "chill", "smooth": "chill",
    "sad": "melancholic", "melancholy": "melancholic", "melancholic": "melancholic",
    "depressing": "melancholic", "heartbreak": "melancholic", "bittersweet": "melancholic",
    "happy": "happy", "feel good": "happy", "feelgood": "happy", "upbeat": "happy",
    "fun": "happy", "cheerful": "happy", "summer": "happy",
    "party": "euphoric", "euphoric": "euphoric", "uplifting": "euphoric", "anthemic": "euphoric",
    "energetic": "energetic", "energy": "energetic", "driving": "energetic", "workout": "energetic",
    "aggressive": "aggressive", "angry": "aggressive", "intense": "aggressive", "brutal": "aggressive",
    "dark": "dark", "moody": "dark", "haunting": "dark", "sinister": "dark", "gothic": "dark",
    "romantic": "romantic", "love songs": "romantic", "love": "romantic", "sexy": "romantic",
    "sensual": "romantic",
}

GENRE_ALIASES: dict[str, str] = {
    "hip-hop": "hip hop", "hiphop": "hip hop", "rap": "hip hop",
    "rnb": "r&b", "r and b": "r&b", "rhythm and blues": "r&b", "r'n'b": "r&b",
    "electronica": "electronic", "electro": "electronic", "edm": "electronic",
    "dnb": "drum and bass", "drum & bass": "drum and bass", "d&b": "drum and bass",
    "synth-pop": "synthpop", "synth pop": "synthpop",
    "electro pop": "electropop", "electro-pop": "electropop",
    "alt rock": "alternative rock", "alt-rock": "alternative rock",
    "hard-rock": "hard rock", "heavy-metal": "heavy metal",
    "post punk": "post-punk", "new-wave": "new wave", "newwave": "new wave",
    "trip-hop": "trip hop", "triphop": "trip hop",
    "singer songwriter": "singer-songwriter",
    "folk-rock": "folk rock", "pop-rock": "pop rock", "punk-rock": "punk rock",
    "soul music": "soul", "jazz vocal": "vocal jazz",
    "indie-rock": "indie rock", "indie-pop": "indie pop", "indie-folk": "indie folk",
}

GENRE_PARENTS: dict[str, tuple[str, ...]] = {
    "indie rock": ("rock", "indie"),
    "alternative rock": ("alternative", "rock"),
    "alternative": ("rock",),
    "grunge": ("alternative rock",),
    "britpop": ("alternative rock",),
    "post-grunge": ("alternative rock",),
    "punk rock": ("punk",),
    "pop punk": ("punk rock", "pop"),
    "punk": ("rock",),
    "post-punk": ("punk", "new wave"),
    "new wave": ("rock",),
    "hard rock": ("rock",),
    "classic rock": ("rock",),
    "soft rock": ("rock", "pop"),
    "pop rock": ("pop", "rock"),
    "progressive rock": ("rock",),
    "psychedelic rock": ("rock",),
    "blues rock": ("blues", "rock"),
    "southern rock": ("rock",),
    "heartland rock": ("rock",),
    "art rock": ("rock",),
    "garage rock": ("rock",),
    "folk rock": ("folk", "rock"),
    "heavy metal": ("metal",),
    "metal": ("hard rock",),
    "alternative metal": ("metal", "alternative rock"),
    "nu metal": ("alternative metal",),
    "rap metal": ("metal", "hip hop"),
    "rap rock": ("rock", "hip hop"),
    "synthpop": ("pop", "electronic"),
    "electropop": ("pop", "electronic"),
    "dance pop": ("pop", "dance"),
    "indie pop": ("pop", "indie"),
    "psychedelic pop": ("pop", "psychedelic rock"),
    "art pop": ("pop",),
    "pop rap": ("pop", "hip hop"),
    "latin pop": ("pop", "latin"),
    "house": ("electronic", "dance"),
    "progressive house": ("house",),
    "techno": ("electronic",),
    "trance": ("electronic", "dance"),
    "drum and bass": ("electronic",),
    "breakbeat": ("electronic",),
    "big beat": ("breakbeat",),
    "trip hop": ("electronic", "hip hop"),
    "downtempo": ("electronic",),
    "ambient": ("electronic",),
    "synthwave": ("electronic", "synthpop"),
    "dubstep": ("electronic",),
    "electronic hip hop": ("electronic", "hip hop"),
    "disco": ("dance", "funk"),
    "funk": ("soul",),
    "soul": ("r&b",),
    "neo soul": ("soul", "r&b"),
    "alt r&b": ("r&b",),
    "trap": ("hip hop",),
    "jazz rap": ("jazz", "hip hop"),
    "reggaeton": ("latin",),
    "latin trap": ("trap", "latin"),
    "cool jazz": ("jazz",),
    "modal jazz": ("jazz",),
    "bebop": ("jazz",),
    "vocal jazz": ("jazz",),
    "indie folk": ("folk", "indie"),
    "singer-songwriter": ("folk",),
}

NON_GENRE_TAGS = frozenset({
    "seen live", "favorites", "favourites", "favorite", "favourite", "female vocalists",
    "male vocalists", "female vocalist", "male vocalist", "american", "british", "english",
    "usa", "uk", "canadian", "australian", "swedish", "german", "french", "irish",
    "love", "awesome", "classic", "oldies", "cover", "covers", "legend", "legends", "beautiful",
    "amazing", "best", "good", "great", "epic", "cool", "fav", "my favorites", "albums i own",
    "singles", "all", "under 2000 listeners", "spotify", "soundtrack", "movie", "film",
    "male", "female", "vocalist", "vocal", "instrumental", "check out",
})

_DECADE_SHORT = re.compile(r"^(\d0)s$")
_DECADE_LONG = re.compile(r"^((?:19|20)\d0)s$")


def normalise_tag(tag: str) -> str:
    cleaned = " ".join(str(tag).strip().lower().replace("_", " ").split())
    return GENRE_ALIASES.get(cleaned, cleaned)


def is_decade_tag(tag: str) -> bool:
    return bool(_DECADE_SHORT.match(tag) or _DECADE_LONG.match(tag))


def is_genre_tag(tag: str) -> bool:
    if not tag or len(tag) > 40:
        return False
    if tag in NON_GENRE_TAGS or tag in MOOD_LEXICON or is_decade_tag(tag):
        return False
    return True


TagInput = Union[Mapping[str, float], Iterable[tuple]]


def _pairs(tags: TagInput):
    return tags.items() if isinstance(tags, Mapping) else tags


def clean_genre_tags(
    tags: TagInput, *, scale: float = 100.0, min_weight: float = 0.1, limit: int = 8
) -> dict[str, float]:
    merged: dict[str, float] = {}
    for name, count in _pairs(tags):
        tag = normalise_tag(name)
        if not is_genre_tag(tag):
            continue
        weight = max(0.0, min(1.0, float(count) / scale))
        if weight < min_weight:
            continue
        merged[tag] = max(merged.get(tag, 0.0), weight)
    top = sorted(merged.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    return dict(top)


def infer_mood(tags: TagInput) -> Optional[str]:
    scores: dict[str, float] = {}
    for name, weight in _pairs(tags):
        mood = MOOD_LEXICON.get(normalise_tag(name))
        if mood:
            scores[mood] = scores.get(mood, 0.0) + float(weight)
    if not scores:
        return None
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def infer_year(tags: TagInput) -> Optional[int]:
    for name, _ in sorted(_pairs(tags), key=lambda kv: -float(kv[1])):
        tag = normalise_tag(name)
        long = _DECADE_LONG.match(tag)
        if long:
            return int(long.group(1)) + 5
        short = _DECADE_SHORT.match(tag)
        if short:
            n = int(short.group(1))
            return (1900 + n if n >= 30 else 2000 + n) + 5
    return None
