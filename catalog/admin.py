from django.contrib import admin

from .models import Artist, Genre, Track, TrackGenre


class TrackGenreInline(admin.TabularInline):
    model = TrackGenre
    extra = 1
    autocomplete_fields = ["genre"]


@admin.register(Artist)
class ArtistAdmin(admin.ModelAdmin):
    list_display = ["name", "mbid", "image_url"]
    search_fields = ["name"]


@admin.register(Genre)
class GenreAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]


@admin.register(Track)
class TrackAdmin(admin.ModelAdmin):
    list_display = ["title", "artist", "year", "tempo", "mood", "listeners", "source"]
    list_filter = ["mood", "source"]
    search_fields = ["title", "artist__name", "album"]
    autocomplete_fields = ["artist"]
    inlines = [TrackGenreInline]
    readonly_fields = ["created_at", "updated_at"]
