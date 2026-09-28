from django.db.models import Count, F, Q
from rest_framework import viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Artist, Genre, Track, TrackGenre
from .permissions import ReadOpenCreateAuthenticatedEditStaff
from .serializers import ArtistSerializer, GenreSerializer, TrackSerializer
from .taxonomy import MOODS


class FlexiblePagination(PageNumberPagination):
    page_size = 24
    page_size_query_param = "page_size"
    max_page_size = 100


ORDER_FIELDS = {
    "title": "title",
    "artist": "artist__name",
    "year": "year",
    "tempo": "tempo",
    "listeners": "listeners",
}


class TrackViewSet(viewsets.ModelViewSet):
    serializer_class = TrackSerializer
    permission_classes = [ReadOpenCreateAuthenticatedEditStaff]
    pagination_class = FlexiblePagination

    def get_queryset(self):
        qs = Track.objects.select_related("artist").prefetch_related("trackgenre_set__genre")
        params = self.request.query_params

        q = params.get("q", "").strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(artist__name__icontains=q) | Q(album__icontains=q))

        genre = params.get("genre", "").strip().lower()
        if genre:
            qs = qs.filter(id__in=TrackGenre.objects.filter(genre__name=genre).values("track_id"))

        mood = params.get("mood", "").strip().lower()
        if mood:
            qs = qs.filter(mood=mood)

        artist = params.get("artist", "").strip()
        if artist:
            qs = qs.filter(artist__name__icontains=artist)

        decade = params.get("decade", "").strip().rstrip("s")
        if decade.isdigit():
            start = int(decade)
            qs = qs.filter(year__gte=start, year__lte=start + 9)

        ordering = params.get("ordering", "").strip()
        if ordering == "random":
            return qs.order_by("?")
        field = ORDER_FIELDS.get(ordering.lstrip("-"))
        if field:
            expression = F(field)
            expression = expression.desc(nulls_last=True) if ordering.startswith("-") else expression.asc(nulls_last=True)
            qs = qs.order_by(expression, "title", "id")
        return qs


class ArtistViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ArtistSerializer
    pagination_class = FlexiblePagination
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = Artist.objects.annotate(track_count=Count("tracks")).order_by("name")
        q = self.request.query_params.get("q", "").strip()
        return qs.filter(name__icontains=q) if q else qs


class GenreListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        genres = Genre.objects.annotate(track_count=Count("tracks")).filter(track_count__gt=0)
        genres = genres.order_by("-track_count", "name")
        data = GenreSerializer(genres, many=True).data
        return Response({"count": len(data), "results": data})


class MoodListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        counts = dict(Track.objects.exclude(mood="").order_by().values_list("mood").annotate(n=Count("id")))
        results = [
            {"name": name, "valence": valence, "arousal": arousal, "tracks": counts.get(name, 0)}
            for name, (valence, arousal) in MOODS.items()
        ]
        return Response({"count": len(results), "results": results})
