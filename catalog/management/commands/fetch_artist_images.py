from django.conf import settings
from django.core.management.base import BaseCommand
from django.db.models import Q

from catalog.models import Artist
from integrations.http import IntegrationError
from integrations.theaudiodb import TheAudioDbClient


class Command(BaseCommand):
    help = (
        "Fill in missing artist photos and biographies from TheAudioDB (looked up by MusicBrainz id where an "
        "artist has one, otherwise by name; cached on disk). Only blank fields are filled. Artists with no "
        "photo keep the generated sleeve art."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100, help="Maximum artists to look up (default 100).")

    def handle(self, *args, **options):
        client = TheAudioDbClient(settings.THEAUDIODB_API_KEY, settings.HTTP_CACHE_DIR)
        todo = list(Artist.objects.filter(Q(image_url="") | Q(bio=""))[: options["limit"]])
        photos = bios = 0
        for artist in todo:
            try:
                info = client.artist_by_mbid(str(artist.mbid)) if artist.mbid else None
                if info is None:
                    info = client.artist_by_name(artist.name)
            except IntegrationError as exc:
                self.stderr.write(f"! {artist.name}: {exc}")
                continue
            if info is None:
                self.stdout.write(f"- nothing found for {artist.name}")
                continue
            fields = []
            if not artist.image_url and info.thumb_url:
                artist.image_url = info.thumb_url
                fields.append("image_url")
                photos += 1
            if not artist.bio and info.bio:
                artist.bio = info.bio
                fields.append("bio")
                bios += 1
            if fields:
                artist.save(update_fields=fields)
                self.stdout.write(f"+ {artist.name}: {', '.join('photo' if f == 'image_url' else f for f in fields)}")
        self.stdout.write(self.style.SUCCESS(
            f"Checked {len(todo)} artists: {photos} new photos, {bios} new biographies."))
