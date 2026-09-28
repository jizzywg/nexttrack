from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from catalog.services import upsert_track
from catalog.taxonomy import clean_genre_tags, infer_mood, infer_year
from integrations.http import IntegrationError
from integrations.lastfm import LastFmClient
from integrations.musicbrainz import MusicBrainzClient
from recommender.models import ReferenceSimilarity


class Command(BaseCommand):
    help = (
        "Import top tracks for one or more Last.fm tags. Genres come from Last.fm tags, mood from a tag "
        "lexicon, popularity from listener counts. Use --similar to also store Last.fm's similar-track "
        "lists as ground truth for evaluation, and --musicbrainz to add release years."
    )

    def add_arguments(self, parser):
        parser.add_argument("--tag", action="append", required=True, help="Last.fm tag, repeatable (--tag rock --tag jazz).")
        parser.add_argument("--limit", type=int, default=25, help="Tracks per tag (default 25).")
        parser.add_argument("--similar", action="store_true", help="Also import Last.fm similar tracks as ground truth.")
        parser.add_argument("--similar-limit", type=int, default=10, help="Similar tracks per seed (default 10).")
        parser.add_argument("--musicbrainz", action="store_true", help="Look up year/MBID on MusicBrainz (1 request/second).")

    def handle(self, *args, **options):
        try:
            self.lastfm = LastFmClient(settings.LASTFM_API_KEY, settings.HTTP_CACHE_DIR, settings.MUSICBRAINZ_USER_AGENT)
        except IntegrationError as exc:
            raise CommandError(str(exc))
        self.musicbrainz = (
            MusicBrainzClient(settings.MUSICBRAINZ_USER_AGENT, settings.HTTP_CACHE_DIR)
            if options["musicbrainz"]
            else None
        )

        total = pairs = 0
        for tag in options["tag"]:
            self.stdout.write(f"Fetching top {options['limit']} '{tag}' tracks from Last.fm ...")
            try:
                tracks = self.lastfm.tag_top_tracks(tag, options["limit"])
            except IntegrationError as exc:
                raise CommandError(str(exc))
            for hint in tracks:
                track = self._ingest(hint.artist, hint.title)
                if track is None:
                    continue
                total += 1
                self.stdout.write(f"  + {track}")
                if options["similar"]:
                    pairs += self._import_similar(track, options["similar_limit"])
        self.stdout.write(self.style.SUCCESS(f"Imported {total} tracks and {pairs} similar-track pairs."))

    def _ingest(self, artist, title):
        try:
            info = self.lastfm.track_info(artist, title)
            tags = self.lastfm.track_top_tags(artist, title)
        except IntegrationError as exc:
            self.stderr.write(f"  ! skipped {artist} - {title}: {exc}")
            return None
        name = info.title if info and info.title else title
        by = info.artist if info and info.artist else artist
        year, mbid, artist_mbid, album = infer_year(tags), (info.mbid if info else ""), (info.artist_mbid if info else ""), (info.album if info else "")
        if self.musicbrainz:
            try:
                recording = self.musicbrainz.find_recording(name, by)
            except IntegrationError as exc:
                recording = None
                self.stderr.write(f"  ! MusicBrainz lookup failed for {by} - {name}: {exc}")
            if recording:
                year = recording.year or year
                mbid = recording.mbid or mbid
                artist_mbid = recording.artist_mbid or artist_mbid
                album = album or recording.album
        track, _ = upsert_track(
            name,
            by,
            clean_genre_tags(tags),
            album=album,
            year=year,
            mood=infer_mood(tags) or "",
            mbid=mbid,
            artist_mbid=artist_mbid,
            lastfm_url=info.url if info else "",
            listeners=info.listeners if info else 0,
            source="lastfm",
        )
        return track

    def _import_similar(self, track, limit):
        try:
            similar = self.lastfm.similar_tracks(track.artist.name, track.title, limit)
        except IntegrationError as exc:
            self.stderr.write(f"  ! no similar tracks for {track}: {exc}")
            return 0
        count = 0
        for item in similar:
            other = self._ingest(item.artist, item.title)
            if other is None or other.pk == track.pk:
                continue
            ReferenceSimilarity.objects.update_or_create(
                track=track, similar=other, source="lastfm", defaults={"match": min(1.0, max(0.0, item.match))}
            )
            count += 1
        return count
