from django.urls import path
from rest_framework.authtoken.views import obtain_auth_token

from . import views

urlpatterns = [
    path("", views.api_root, name="api-root"),
    path("recommendations/", views.RecommendationView.as_view(), name="recommendations"),
    path("tracks/<int:pk>/similar/", views.SimilarTracksView.as_view(), name="track-similar"),
    path("feedback/", views.FeedbackView.as_view(), name="feedback"),
    path("stats/", views.StatsView.as_view(), name="stats"),
    path("map/", views.TasteMapView.as_view(), name="taste-map"),
    path("bridge/", views.BridgeView.as_view(), name="bridge"),
    path("evaluation/", views.EvaluationView.as_view(), name="evaluation"),
    path("auth/register/", views.RegisterView.as_view(), name="register"),
    path("auth/token/", obtain_auth_token, name="token"),
]
