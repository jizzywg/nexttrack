from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.dataset import DEMO_CSV, read_track_rows
from catalog.models import Artist, Genre, Track
from catalog.services import upsert_track


class Command(BaseCommand):
    help = (
        "Load the bundled demo catalogue (157 well-known tracks) or your own CSV into the database. "
        "CSV columns: title,artist,album,year,tempo,mood,genres,listeners."
    )

    def add_arguments(self, parser):
        parser.add_argument("--file", help="Path to a catalogue CSV (defaults to the bundled demo data).")
        parser.add_argument("--clear", action="store_true", help="Delete all tracks, artists and genres first.")

    @transaction.atomic
    def handle(self, *args, **options):
        path = Path(options["file"]) if options["file"] else DEMO_CSV
        if not path.exists():
            raise CommandError(f"File not found: {path}")
        try:
            rows = read_track_rows(path)
        except ValueError as exc:
            raise CommandError(str(exc))

        if options["clear"]:
            Track.objects.all().delete()
            Artist.objects.all().delete()
            Genre.objects.all().delete()
            self.stdout.write("Cleared existing catalogue.")

        created = updated = 0
        for row in rows:
            _, was_created = upsert_track(
                row["title"],
                row["artist"],
                row["genres"],
                album=row["album"],
                year=row["year"],
                tempo=row["tempo"],
                mood=row["mood"],
                listeners=row["listeners"],
                source="seed" if path == DEMO_CSV else "csv",
            )
            created += was_created
            updated += not was_created
        self.stdout.write(self.style.SUCCESS(f"Loaded {path.name}: {created} created, {updated} updated."))
