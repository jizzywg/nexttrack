import csv
import sys

from django.core.management.base import BaseCommand

from recommender.models import Feedback


class Command(BaseCommand):
    help = "Export like/skip feedback as CSV (for the user-study part of the evaluation)."

    def add_arguments(self, parser):
        parser.add_argument("--out", help="Output file (defaults to stdout).")

    def handle(self, *args, **options):
        handle = open(options["out"], "w", newline="", encoding="utf-8") if options["out"] else sys.stdout
        try:
            writer = csv.writer(handle)
            writer.writerow(["participant", "track_id", "title", "artist", "value", "seeds", "timestamp"])
            for fb in Feedback.objects.select_related("track__artist", "user").order_by("created_at"):
                participant = f"user:{fb.user_id}" if fb.user_id else f"session:{fb.session_key[:8]}"
                writer.writerow(
                    [participant, fb.track_id, fb.track.title, fb.track.artist.name, fb.value,
                     ";".join(map(str, fb.seeds)), fb.updated_at.isoformat()]
                )
        finally:
            if options["out"]:
                handle.close()
        if options["out"]:
            self.stdout.write(self.style.SUCCESS(f"Wrote {options['out']}"))
