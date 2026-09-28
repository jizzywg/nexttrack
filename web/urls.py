from django.urls import path

from .views import PageView

app_name = "web"

urlpatterns = [
    path("", PageView.as_view(template_name="web/landing.html", active="landing"), name="landing"),
    path("discover/", PageView.as_view(template_name="web/discover.html", active="discover"), name="discover"),
    path("library/", PageView.as_view(template_name="web/library.html", active="library"), name="library"),
    path("evaluation/", PageView.as_view(template_name="web/evaluation.html", active="evaluation"), name="evaluation"),
    path("api-docs/", PageView.as_view(template_name="web/docs.html", active="docs"), name="docs"),
    path("method/", PageView.as_view(template_name="web/method.html", active="method"), name="method"),
]
