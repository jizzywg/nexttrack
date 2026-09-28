from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Count
from django.urls import reverse as django_reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.reverse import reverse
from rest_framework.views import APIView

from catalog.models import Artist, Genre, Track, TrackGenre

from .models import Feedback, ReferenceSimilarity
from .presenters import run_recommendation
from .serializers import (
    FeedbackReadSerializer,
    FeedbackSerializer,
    RecommendationRequestSerializer,
    RegisterSerializer,
)
from .presenters import bridge_payload
from .serializers import BridgeRequestSerializer
from .services import build_evaluation, feedback_identity, feedback_sets, get_recommender
from .tastemap import FAMILY_ORDER, genre_family


@api_view(["GET"])
@permission_classes([AllowAny])
def api_root(request):
    def link(name, **kwargs):
        return reverse(name, request=request, kwargs=kwargs or None)

    return Response(
        {
            "name": "NextTrack API",
            "version": "1.0",
            "docs": request.build_absolute_uri(django_reverse("web:docs")),
            "endpoints": {
                "tracks": link("track-list"),
                "artists": link("artist-list"),
                "genres": link("genre-list"),
                "moods": link("mood-list"),
                "recommendations": link("recommendations"),
                "feedback": link("feedback"),
                "stats": link("stats"),
                "taste_map": link("taste-map"),
                "bridge": link("bridge"),
                "evaluation": link("evaluation"),
                "register": link("register"),
                "token": link("token"),
            },
        }
    )


def _recommendation_input(query_params) -> dict:
    data: dict = {"seeds": [s for s in query_params.get("seeds", "").split(",") if s.strip()]}
    for key in ("k", "aggregate", "diversity", "max_per_artist", "personalise"):
        if key in query_params:
            data[key] = query_params[key]
    for key in ("exclude", "history"):
        if query_params.get(key):
            data[key] = [s for s in query_params[key].split(",") if s.strip()]
    weights = {
        name: query_params[f"w_{name}"]
        for name in ("genre", "mood", "tempo", "decade")
        if f"w_{name}" in query_params
    }
    if weights:
        data["weights"] = weights
    return data


def _recommend(request, data) -> Response:
    serializer = RecommendationRequestSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    params = serializer.validated_data

    recommender = get_recommender()
    for field in ("seeds", "history"):
        unknown = [i for i in params[field] if not recommender.has_track(i)]
        if unknown:
            raise ValidationError({field: [f"Unknown track id(s): {', '.join(map(str, unknown))}"]})

    liked, skipped = feedback_sets(request) if params["personalise"] else ([], [])
    weights = params.get("weights") or None
    payload = run_recommendation(
        recommender,
        seeds=params["seeds"],
        k=params["k"],
        weights=dict(weights) if weights else None,
        aggregate=params["aggregate"],
        diversity=params["diversity"],
        max_per_artist=params["max_per_artist"],
        exclude=params["exclude"],
        liked=liked,
        disliked=skipped,
        history=params["history"],
    )
    return Response(payload)


class RecommendationView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return _recommend(request, _recommendation_input(request.query_params))

    def post(self, request):
        return _recommend(request, request.data)


class SimilarTracksView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        if not Track.objects.filter(pk=pk).exists():
            raise NotFound("Track not found.")
        data = _recommendation_input(request.query_params)
        data["seeds"] = [pk]
        return _recommend(request, data)


class FeedbackView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        identity = feedback_identity(request)
        rows = Feedback.objects.filter(**identity) if identity else Feedback.objects.none()
        return Response({"results": FeedbackReadSerializer(rows, many=True).data})

    def post(self, request):
        serializer = FeedbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if not request.user.is_authenticated and not request.session.session_key:
            request.session.create()
        identity = feedback_identity(request)

        if data["value"] == 0:
            Feedback.objects.filter(track=data["track"], **identity).delete()
            return Response({"track": data["track"].pk, "value": 0})

        obj, created = Feedback.objects.update_or_create(
            track=data["track"], **identity, defaults={"value": data["value"], "seeds": data["seeds"]}
        )
        return Response(
            {"track": obj.track_id, "value": obj.value},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class BridgeView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "recommendations"

    def post(self, request):
        serializer = BridgeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.validated_data
        recommender = get_recommender()
        key = f"bridge:{len(recommender):d}:{params['from_id']}:{params['to_id']}:{params['length']}:{sorted((params.get('weights') or {}).items())}"
        cached = cache.get(key)
        if cached is not None:
            return Response(cached)
        for field in ("from_id", "to_id"):
            if not recommender.has_track(params[field]):
                raise ValidationError({field: [f"Unknown track id: {params[field]}"]})
        try:
            payload = bridge_payload(recommender, params["from_id"], params["to_id"], params["length"], params.get("weights"))
        except ValueError as exc:
            raise ValidationError({"length": [str(exc)]})
        cache.set(key, payload, 300)
        return Response(payload)


class TasteMapView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        recommender = get_recommender()
        placed = Track.objects.filter(map_x__isnull=False, map_y__isnull=False).select_related("artist").order_by("id")
        tracks = []
        for t in placed:
            profile = recommender.get(t.id) if t.id in recommender else None
            tracks.append({
                "id": t.id, "title": t.title, "artist": t.artist.name, "artist_id": t.artist_id,
                "x": t.map_x, "y": t.map_y, "family": genre_family(profile.genres) if profile else "other",
            })
        return Response({
            "tracks": tracks,
            "unplaced": Track.objects.filter(map_x__isnull=True).count(),
            "families": FAMILY_ORDER,
        })


class StatsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        moods = dict(Track.objects.exclude(mood="").order_by().values_list("mood").annotate(n=Count("id")))
        decades: dict[str, int] = {}
        for year in Track.objects.exclude(year__isnull=True).values_list("year", flat=True):
            label = f"{(year // 10) * 10}s"
            decades[label] = decades.get(label, 0) + 1
        top_genres = (
            TrackGenre.objects.order_by().values("genre__name").annotate(n=Count("id")).order_by("-n", "genre__name")[:15]
        )
        return Response(
            {
                "tracks": Track.objects.count(),
                "artists": Artist.objects.count(),
                "genres": Genre.objects.count(),
                "missing_tempo": Track.objects.filter(tempo__isnull=True).count(),
                "missing_year": Track.objects.filter(year__isnull=True).count(),
                "missing_mood": Track.objects.filter(mood="").count(),
                "moods": moods,
                "decades": dict(sorted(decades.items())),
                "top_genres": [{"name": g["genre__name"], "tracks": g["n"]} for g in top_genres],
                "feedback": Feedback.objects.count(),
                "reference_pairs": ReferenceSimilarity.objects.count(),
            }
        )


class EvaluationView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            k = max(1, min(30, int(request.query_params.get("k", 10))))
            sample = max(5, min(300, int(request.query_params.get("sample", 60))))
        except ValueError:
            raise ValidationError({"detail": "k and sample must be integers."})
        recommender = get_recommender()
        key = f"evaluation:{len(recommender)}:{Track.objects.count()}:{k}:{sample}:{ReferenceSimilarity.objects.count()}"
        report = cache.get(key)
        if report is None:
            report = build_evaluation(k=k, sample=sample)
            cache.set(key, report, 300)
        return Response(report)


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = get_user_model().objects.create_user(
            username=data["username"], password=data["password"], email=data.get("email", "")
        )
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"username": user.username, "token": token.key}, status=status.HTTP_201_CREATED)
