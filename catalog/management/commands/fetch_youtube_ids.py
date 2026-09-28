from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from catalog.models import Track
from integrations.http import IntegrationError
from integrations.youtube import YouTubeClient

QUOTA_PER_LOOKUP = 100
DAILY_QUOTA = 10_000


class Command(BaseCommand):
    help = (
        "Find a playable YouTube video for chosen tracks so the play button opens the embedded player. "
        "Each lookup costs 100 of the 10,000 free daily YouTube quota units (about 100 tracks a day), so "
        "pick the tracks you need: --ids 12,40,77 --with-recs 10 covers those seeds and what they recommend. "
        "Tracks without an ID keep the YouTube search link."
    )

    def add_arguments(self, parser):
        parser.add_argument("--ids", help="Comma-separated track IDs (copy them from a Discover URL: ?seeds=12,40,77).")
        parser.add_argument(
            "--with-recs", type=int, default=0, metavar="N",
            help="Also cover the top N recommendations for each --ids track, at the default weights.",
        )
        parser.add_argument("--limit", type=int, default=20, help="Maximum lookups this run (default 20 = 2,000 units).")

    def _targets(self, options):
        if not options["ids"]:
            return list(Track.objects.filter(youtube_id="").select_related("artist").order_by("-listeners")[: options["limit"]])
        try:
            ids = [int(x) for x in options["ids"].split(",") if x.strip()]
        except ValueError:
            raise CommandError("--ids must be comma-separated numbers, e.g. --ids 12,40,77")
        wanted = list(ids)
        if options["with_recs"]:
            from recommender.presenters import run_recommendation
            from recommender.services import get_recommender

            recommender = get_recommender()
            for seed in ids:
                try:
                    payload = run_recommendation(recommender, seeds=[seed], k=options["with_recs"])
                except KeyError:
                    raise CommandError(f"Track {seed} is not in the catalogue.")
                wanted += [r["track"]["id"] for r in payload["results"]]
        order = {pk: i for i, pk in enumerate(dict.fromkeys(wanted))}
        tracks = Track.objects.filter(pk__in=order, youtube_id="").select_related("artist")
        return sorted(tracks, key=lambda t: order[t.pk])[: options["limit"]]

    def handle(self, *args, **options):
        try:
            client = YouTubeClient(settings.YOUTUBE_API_KEY, settings.HTTP_CACHE_DIR)
        except IntegrationError as exc:
            raise CommandError(str(exc))
        todo = self._targets(options)
        if not todo:
            self.stdout.write("Nothing to look up: those tracks already have videos (or none matched).")
            return
        self.stdout.write(
            f"Looking up {len(todo)} tracks (up to {len(todo) * QUOTA_PER_LOOKUP:,} of {DAILY_QUOTA:,} "
            "daily quota units; cached lookups cost nothing)."
        )
        found = 0
        for track in todo:
            try:
                video = client.find_video(track.artist.name, track.title)
            except IntegrationError as exc:
                if "HTTP 403" in str(exc):
                    self.stderr.write(
                        "! YouTube refused the request (quota used up for today, or the key is invalid or "
                        "restricted). Stopping; the free quota resets at midnight Pacific time."
                    )
                    break
                self.stderr.write(f"! {track.artist.name} - {track.title}: {exc}")
                continue
            if video is None:
                self.stdout.write(f"- no embeddable video for {track.artist.name} - {track.title}")
                continue
            track.youtube_id = video.video_id
            track.save(update_fields=["youtube_id", "updated_at"])
            found += 1
            self.stdout.write(f"+ {track.artist.name} - {track.title}: {video.title} ({video.channel})")
        self.stdout.write(self.style.SUCCESS(f"Found videos for {found} of {len(todo)} tracks checked."))
