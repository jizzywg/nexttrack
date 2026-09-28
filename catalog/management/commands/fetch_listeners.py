from django.conf import settings
from django.core.management.base import BaseCommand

from catalog.models import Track
from integrations.http import IntegrationError
from integrations.lastfm import LastFmClient


class Command(BaseCommand):
    help = (
        "Fill in missing Last.fm listener counts (track.getInfo, cached on disk). Listener counts rank the "
        "landing page chart, break ties in the engine and feed the novelty metric on the Evaluation page. "
        "Tracks Last.fm can't match keep a count of 0."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=200, help="Maximum tracks to look up (default 200).")

    def handle(self, *args, **options):
        client = LastFmClient(settings.LASTFM_API_KEY, settings.HTTP_CACHE_DIR)
        todo = list(Track.objects.filter(listeners=0).select_related("artist")[: options["limit"]])
        found = 0
        for track in todo:
            try:
                info = client.track_info(track.artist.name, track.title)
            except IntegrationError as exc:
                self.stderr.write(f"! {track.artist.name} - {track.title}: {exc}")
                continue
            if info is None or not info.listeners:
                self.stdout.write(f"- no listener count for {track.artist.name} - {track.title}")
                continue
            track.listeners = info.listeners
            fields = ["listeners", "updated_at"]
            if not track.lastfm_url and info.url:
                track.lastfm_url = info.url
                fields.append("lastfm_url")
            track.save(update_fields=fields)
            found += 1
            self.stdout.write(f"+ {track.artist.name} - {track.title}: {info.listeners:,}")
        self.stdout.write(self.style.SUCCESS(f"Found listener counts for {found} of {len(todo)} tracks checked."))
