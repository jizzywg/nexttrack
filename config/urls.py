from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("recommender.urls")),
    path("api/", include("catalog.urls")),
    path("", include("web.urls")),
]
