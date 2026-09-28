from django.contrib import admin

from .models import Feedback, ReferenceSimilarity


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ["track", "value", "user", "session_key", "updated_at"]
    list_filter = ["value"]
    raw_id_fields = ["track", "user"]


@admin.register(ReferenceSimilarity)
class ReferenceSimilarityAdmin(admin.ModelAdmin):
    list_display = ["track", "similar", "match", "source"]
    list_filter = ["source"]
    raw_id_fields = ["track", "similar"]
