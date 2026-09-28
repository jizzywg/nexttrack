from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from catalog.models import Track, TrackGenre

from .services import invalidate_recommender


@receiver([post_save, post_delete], sender=Track)
@receiver([post_save, post_delete], sender=TrackGenre)
def catalogue_changed(sender, **kwargs):
    invalidate_recommender()
