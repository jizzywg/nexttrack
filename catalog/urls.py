from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ArtistViewSet, GenreListView, MoodListView, TrackViewSet

router = DefaultRouter()
router.include_root_view = False
router.register("tracks", TrackViewSet, basename="track")
router.register("artists", ArtistViewSet, basename="artist")

urlpatterns = [
    path("genres/", GenreListView.as_view(), name="genre-list"),
    path("moods/", MoodListView.as_view(), name="mood-list"),
    path("", include(router.urls)),
]
