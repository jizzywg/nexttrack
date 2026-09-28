from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q

from catalog.models import Track
from integrations.http import IntegrationError
from integrations.musicbrainz import MusicBrainzClient


class Command(BaseCommand):
    help = "Fill in missing release years and MusicBrainz IDs for tracks (1 request/second, cached on disk)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50, help="Maximum tracks to look up (default 50).")

    def handle(self, *args, **options):
        client = MusicBrainzClient(settings.MUSICBRAINZ_USER_AGENT, settings.HTTP_CACHE_DIR)
        todo = Track.objects.filter(Q(year__isnull=True) | Q(mbid__isnull=True)).select_related("artist")[: options["limit"]]
        updated = 0
        for track in todo:
            try:
                found = client.find_recording(track.title, track.artist.name)
            except IntegrationError as exc:
                self.stderr.write(f"! {track}: {exc}")
                continue
            if not found:
                self.stdout.write(f"- no confident match for {track}")
                continue
            changed = []
            if track.year is None and found.year:
                track.year = found.year
                changed.append("year")
            if track.mbid is None and found.mbid and not Track.objects.filter(mbid=found.mbid).exists():
                track.mbid = found.mbid
                changed.append("mbid")
            if not track.album and found.album:
                track.album = found.album
                changed.append("album")
            if changed:
                track.save()
                updated += 1
                self.stdout.write(f"+ {track}: {', '.join(changed)}")
        self.stdout.write(self.style.SUCCESS(f"Updated {updated} tracks."))
