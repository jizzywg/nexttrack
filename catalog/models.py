from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .taxonomy import MOOD_CHOICES


class Artist(models.Model):
    name = models.CharField(max_length=255, unique=True)
    mbid = models.UUIDField("MusicBrainz ID", null=True, blank=True, unique=True)
    image_url = models.URLField(
        "Image URL", max_length=500, blank=True,
        help_text="Artist photo, e.g. from TheAudioDB. Last.fm no longer serves images over its API.",
    )
    bio = models.TextField(blank=True, help_text="Short biography from TheAudioDB (fetch_artist_images).")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Genre(models.Model):
    name = models.CharField(max_length=64, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Track(models.Model):
    title = models.CharField(max_length=255)
    artist = models.ForeignKey(Artist, on_delete=models.CASCADE, related_name="tracks")
    album = models.CharField(max_length=255, blank=True)
    year = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1900), MaxValueValidator(2100)]
    )
    tempo = models.FloatField(
        "tempo (BPM)", null=True, blank=True, validators=[MinValueValidator(30), MaxValueValidator(300)]
    )
    mood = models.CharField(max_length=16, choices=MOOD_CHOICES, blank=True)
    genres = models.ManyToManyField(Genre, through="TrackGenre", related_name="tracks", blank=True)
    mbid = models.UUIDField("MusicBrainz recording ID", null=True, blank=True, unique=True)
    lastfm_url = models.URLField(max_length=500, blank=True)
    youtube_id = models.CharField(
        "YouTube video ID", max_length=20, blank=True,
        help_text="Set by fetch_youtube_ids. With it the play button opens an embedded player; without it, a YouTube search.",
    )
    map_x = models.FloatField(null=True, blank=True, help_text="Taste map position (0 to 1), set by build_taste_map.")
    map_y = models.FloatField(null=True, blank=True, help_text="Taste map position (0 to 1), set by build_taste_map.")
    listeners = models.PositiveIntegerField(default=0, help_text="Popularity, e.g. Last.fm listeners.")
    source = models.CharField(max_length=20, default="manual", help_text="seed, lastfm, musicbrainz or manual")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["artist__name", "title"]
        constraints = [
            models.UniqueConstraint(fields=["artist", "title"], name="uniq_track_per_artist"),
        ]
        indexes = [models.Index(fields=["year"]), models.Index(fields=["mood"])]

    def __str__(self) -> str:
        return f"{self.title} - {self.artist.name}"

    @property
    def decade(self):
        return None if self.year is None else f"{(self.year // 10) * 10}s"


class TrackGenre(models.Model):
    track = models.ForeignKey(Track, on_delete=models.CASCADE)
    genre = models.ForeignKey(Genre, on_delete=models.CASCADE)
    weight = models.FloatField(
        default=1.0, validators=[MinValueValidator(0.0), MaxValueValidator(1.0)]
    )

    class Meta:
        ordering = ["-weight", "genre__name"]
        constraints = [
            models.UniqueConstraint(fields=["track", "genre"], name="uniq_genre_per_track"),
        ]

    def __str__(self) -> str:
        return f"{self.track_id}:{self.genre.name}={self.weight:.2f}"
