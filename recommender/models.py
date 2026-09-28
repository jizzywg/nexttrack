from django.conf import settings
from django.db import models

from catalog.models import Track


class Feedback(models.Model):
    LIKE = 1
    SKIP = -1
    VALUE_CHOICES = [(LIKE, "like"), (SKIP, "skip")]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="feedback"
    )
    session_key = models.CharField(max_length=40, blank=True, db_index=True)
    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name="feedback")
    value = models.SmallIntegerField(choices=VALUE_CHOICES)
    seeds = models.JSONField(default=list, blank=True, help_text="Seed track ids shown when the feedback was given.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name_plural = "feedback"

    def __str__(self) -> str:
        who = self.user_id or self.session_key[:8] or "anon"
        return f"{who}: {self.get_value_display()} {self.track_id}"


class ReferenceSimilarity(models.Model):
    track = models.ForeignKey(Track, on_delete=models.CASCADE, related_name="reference_from")
    similar = models.ForeignKey(Track, on_delete=models.CASCADE, related_name="reference_to")
    match = models.FloatField(help_text="Similarity in [0, 1] reported by the source.")
    source = models.CharField(max_length=20, default="lastfm")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["track", "similar", "source"], name="uniq_reference_pair"),
        ]
        verbose_name_plural = "reference similarities"

    def __str__(self) -> str:
        return f"{self.track_id} ~ {self.similar_id} ({self.match:.2f}, {self.source})"
