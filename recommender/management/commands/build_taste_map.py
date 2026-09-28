import time

from django.core.management.base import BaseCommand, CommandError

from catalog.models import Track
from recommender.services import get_recommender


class Command(BaseCommand):
    help = (
        "Place every track on the taste map: score all pairs of tracks with the engine at the default "
        "weights, project them to 2D with t-SNE, and store each position. Run it again after importing "
        "tracks; a few hundred tracks take seconds."
    )

    def add_arguments(self, parser):
        parser.add_argument("--seed", type=int, default=7, help="Random seed; the same seed gives the same layout.")

    def handle(self, *args, **options):
        try:
            from recommender.tastemap import build_layout
            import sklearn  # noqa: F401
        except ImportError:
            raise CommandError("The taste map needs scikit-learn. Run: pip install -r requirements.txt")
        recommender = get_recommender()
        if not len(recommender):
            raise CommandError("The catalogue is empty. Run: python manage.py seed_demo")
        started = time.perf_counter()
        positions = build_layout(recommender, seed=options["seed"])
        tracks = list(Track.objects.filter(pk__in=positions))
        for track in tracks:
            track.map_x, track.map_y = positions[track.pk]
        Track.objects.bulk_update(tracks, ["map_x", "map_y"], batch_size=500)
        cleared = Track.objects.exclude(pk__in=positions).exclude(map_x__isnull=True).update(map_x=None, map_y=None)
        self.stdout.write(self.style.SUCCESS(
            f"Placed {len(tracks)} tracks on the taste map in {time.perf_counter() - started:.1f}s"
            + (f" (cleared {cleared} stale positions)." if cleared else ".")))
