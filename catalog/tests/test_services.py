import uuid

from django.core.management import call_command
from django.test import TestCase

from catalog.models import Artist, Genre, Track, TrackGenre
from catalog.services import set_track_genres, upsert_track


class UpsertTrackTests(TestCase):
    def test_creates_track_artist_and_normalised_genres(self):
        track, created = upsert_track("Song", "Band", {"Hip-Hop": 0.9, "Indie Rock": 0.5}, year=1999, tempo=100, mood="happy")
        self.assertTrue(created)
        self.assertEqual(track.artist.name, "Band")
        self.assertEqual(set(track.genres.values_list("name", flat=True)), {"hip hop", "indie rock"})
        self.assertEqual(track.decade, "1990s")

    def test_update_does_not_wipe_existing_values(self):
        upsert_track("Song", "Band", {"rock": 1.0}, year=1999, tempo=100, mood="happy", listeners=50)
        track, created = upsert_track("Song", "Band", None, lastfm_url="http://example.com/x")
        self.assertFalse(created)
        self.assertEqual((track.year, track.tempo, track.mood, track.listeners), (1999, 100, "happy", 50))
        self.assertEqual(track.lastfm_url, "http://example.com/x")
        self.assertEqual(track.genres.count(), 1)
        self.assertEqual(Track.objects.count(), 1)

    def test_genres_are_replaced_when_given(self):
        track, _ = upsert_track("Song", "Band", {"rock": 1.0, "punk": 0.5})
        set_track_genres(track, {"jazz": 1.0})
        self.assertEqual(list(track.genres.values_list("name", flat=True)), ["jazz"])
        self.assertEqual(TrackGenre.objects.filter(track=track).count(), 1)

    def test_weights_are_clamped(self):
        track, _ = upsert_track("Song", "Band", {"rock": 7, "jazz": -1})
        weights = dict(TrackGenre.objects.filter(track=track).values_list("genre__name", "weight"))
        self.assertEqual(weights, {"rock": 1.0, "jazz": 0.0})

    def test_duplicate_musicbrainz_id_is_ignored_instead_of_crashing(self):
        mbid = uuid.uuid4()
        first, _ = upsert_track("One", "Band", None, mbid=mbid)
        second, _ = upsert_track("Two", "Band", None, mbid=str(mbid))
        self.assertEqual(first.mbid, mbid)
        self.assertIsNone(second.mbid)

    def test_invalid_mbid_is_ignored(self):
        track, _ = upsert_track("One", "Band", None, mbid="not-a-uuid")
        self.assertIsNone(track.mbid)


class SeedDemoCommandTests(TestCase):
    def test_seed_demo_loads_catalogue_and_is_idempotent(self):
        call_command("seed_demo", verbosity=0)
        count = Track.objects.count()
        self.assertGreater(count, 100)
        self.assertGreater(Genre.objects.count(), 30)
        self.assertGreater(Artist.objects.count(), 50)
        call_command("seed_demo", verbosity=0)
        self.assertEqual(Track.objects.count(), count)

    def test_clear_option_resets_the_catalogue(self):
        upsert_track("Leftover", "Nobody", {"rock": 1.0})
        call_command("seed_demo", "--clear", verbosity=0)
        self.assertFalse(Track.objects.filter(title="Leftover").exists())
