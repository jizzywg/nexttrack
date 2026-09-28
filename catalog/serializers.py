from django.db import transaction
from rest_framework import serializers

from .models import Artist, Genre, Track, TrackGenre
from .services import set_track_genres


class ArtistSerializer(serializers.ModelSerializer):
    tracks = serializers.IntegerField(source="track_count", read_only=True)

    class Meta:
        model = Artist
        fields = ["id", "name", "mbid", "image_url", "bio", "tracks"]


class GenreTagSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="genre.name", max_length=64)
    weight = serializers.FloatField(min_value=0.0, max_value=1.0, default=1.0)

    class Meta:
        model = TrackGenre
        fields = ["name", "weight"]


class TrackSerializer(serializers.ModelSerializer):
    artist = serializers.CharField(max_length=255)
    artist_id = serializers.IntegerField(source="artist.id", read_only=True)
    artist_image = serializers.URLField(source="artist.image_url", read_only=True, default="")
    genres = GenreTagSerializer(source="trackgenre_set", many=True, required=False)
    decade = serializers.CharField(read_only=True)

    class Meta:
        model = Track
        fields = [
            "id", "title", "artist", "artist_id", "artist_image", "album", "year", "decade", "tempo", "mood",
            "genres", "mbid", "lastfm_url", "youtube_id", "listeners", "source",
        ]
        read_only_fields = ["source"]
        validators = []

    def to_internal_value(self, data):
        if hasattr(data, "get") and isinstance(data.get("genres"), list):
            data = data.copy()
            data["genres"] = [{"name": g} if isinstance(g, str) else g for g in data["genres"]]
        return super().to_internal_value(data)

    def validate(self, attrs):
        artist = attrs.get("artist", getattr(self.instance, "artist", None))
        title = attrs.get("title", getattr(self.instance, "title", None))
        artist_name = artist if isinstance(artist, str) else getattr(artist, "name", None)
        if artist_name and title:
            clash = Track.objects.filter(artist__name=artist_name.strip(), title=title.strip())
            if self.instance is not None:
                clash = clash.exclude(pk=self.instance.pk)
            if clash.exists():
                raise serializers.ValidationError("This artist already has a track with that title.")
        return attrs

    @staticmethod
    def _genre_dict(items):
        return {item["genre"]["name"]: item.get("weight", 1.0) for item in items}

    @transaction.atomic
    def create(self, validated_data):
        genres = self._genre_dict(validated_data.pop("trackgenre_set", []))
        artist, _ = Artist.objects.get_or_create(name=validated_data.pop("artist").strip())
        track = Track.objects.create(artist=artist, source="api", **validated_data)
        if genres:
            set_track_genres(track, genres)
        return track

    @transaction.atomic
    def update(self, instance, validated_data):
        genres = validated_data.pop("trackgenre_set", None)
        artist_name = validated_data.pop("artist", None)
        if artist_name is not None:
            instance.artist, _ = Artist.objects.get_or_create(name=artist_name.strip())
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        if genres is not None:
            set_track_genres(instance, self._genre_dict(genres))
        return instance


class GenreSerializer(serializers.ModelSerializer):
    tracks = serializers.IntegerField(source="track_count", read_only=True)

    class Meta:
        model = Genre
        fields = ["id", "name", "tracks"]
