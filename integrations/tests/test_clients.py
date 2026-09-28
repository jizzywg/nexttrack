import tempfile
import unittest
from pathlib import Path
from unittest import mock

from integrations.http import CachedJsonClient, IntegrationError
from integrations.lastfm import LastFmClient
from integrations.musicbrainz import MusicBrainzClient
from integrations.theaudiodb import TheAudioDbClient
from integrations.youtube import YouTubeClient


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = str(payload)

    def json(self):
        return self._payload


def make_client(tmp, **kwargs):
    client = CachedJsonClient(user_agent="test", cache_dir=Path(tmp), min_interval=0, retries=2, **kwargs)
    return client


class CachedJsonClientTests(unittest.TestCase):
    def test_second_call_is_served_from_disk_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = make_client(tmp)
            client.session.get = mock.Mock(return_value=FakeResponse({"ok": 1}))
            self.assertEqual(client.get_json("http://x/api", {"a": 1}), {"ok": 1})
            self.assertEqual(client.get_json("http://x/api", {"a": 1}), {"ok": 1})
            self.assertEqual(client.session.get.call_count, 1)

    def test_secret_params_do_not_affect_cache_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = make_client(tmp, secret_params=("api_key",))
            client.session.get = mock.Mock(return_value=FakeResponse({"ok": 1}))
            client.get_json("http://x/api", {"a": 1, "api_key": "one"})
            client.get_json("http://x/api", {"a": 1, "api_key": "two"})
            self.assertEqual(client.session.get.call_count, 1)
            cached = "".join(p.read_text() for p in Path(tmp).glob("*.json"))
            self.assertNotIn("one", cached)

    def test_error_payloads_are_not_cached(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = make_client(tmp)
            client.session.get = mock.Mock(return_value=FakeResponse({"error": 6, "message": "Track not found"}))
            with self.assertRaisesRegex(IntegrationError, "Track not found"):
                client.get_json("http://x/api", {"a": 1}, error_key="error")
            self.assertEqual(list(Path(tmp).glob("*.json")), [])

    def test_client_errors_raise_immediately(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = make_client(tmp)
            client.session.get = mock.Mock(return_value=FakeResponse({}, status=404))
            with self.assertRaises(IntegrationError):
                client.get_json("http://x/api")
            self.assertEqual(client.session.get.call_count, 1)

    def test_server_errors_are_retried_then_give_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = make_client(tmp)
            client.session.get = mock.Mock(return_value=FakeResponse({}, status=503))
            with mock.patch("integrations.http.time.sleep"):
                with self.assertRaises(IntegrationError):
                    client.get_json("http://x/api")
            self.assertEqual(client.session.get.call_count, 2)


class LastFmClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.client = LastFmClient("KEY", Path(self.tmp.name))

    def test_requires_api_key(self):
        with self.assertRaises(IntegrationError):
            LastFmClient("", Path(self.tmp.name))

    def test_tag_top_tracks_and_single_item_dict(self):
        payload = {"tracks": {"track": {"name": "Song", "mbid": "", "url": "u", "artist": {"name": "Band", "mbid": "m"}}}}
        with mock.patch.object(self.client.http, "get_json", return_value=payload):
            tracks = self.client.tag_top_tracks("rock", 1)
        self.assertEqual([(t.title, t.artist) for t in tracks], [("Song", "Band")])

    def test_top_tags(self):
        payload = {"toptags": {"tag": [{"name": "rock", "count": 100}, {"name": "90s", "count": "40"}]}}
        with mock.patch.object(self.client.http, "get_json", return_value=payload):
            self.assertEqual(self.client.track_top_tags("Band", "Song"), [("rock", 100), ("90s", 40)])

    def test_track_info(self):
        payload = {"track": {"name": "Song", "listeners": "1234", "playcount": "9", "url": "u",
                             "artist": {"name": "Band", "mbid": "abc"}, "album": {"title": "LP"}}}
        with mock.patch.object(self.client.http, "get_json", return_value=payload):
            info = self.client.track_info("Band", "Song")
        self.assertEqual((info.listeners, info.album, info.artist_mbid), (1234, "LP", "abc"))

    def test_similar_tracks_match_scores(self):
        payload = {"similartracks": {"track": [
            {"name": "A", "match": 1, "artist": {"name": "X"}},
            {"name": "B", "match": "0.5", "artist": {"name": "Y"}},
        ]}}
        with mock.patch.object(self.client.http, "get_json", return_value=payload):
            similar = self.client.similar_tracks("Band", "Song")
        self.assertEqual([(s.title, s.match) for s in similar], [("A", 1.0), ("B", 0.5)])

    def test_missing_sections_give_empty_lists(self):
        with mock.patch.object(self.client.http, "get_json", return_value={}):
            self.assertEqual(self.client.similar_tracks("a", "b"), [])
            self.assertEqual(self.client.track_top_tags("a", "b"), [])
            self.assertIsNone(self.client.track_info("a", "b"))


class MusicBrainzClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.client = MusicBrainzClient("test-agent", Path(self.tmp.name))

    def payload(self):
        return {"recordings": [
            {"id": "low", "score": 60, "title": "Song", "artist-credit": [{"name": "Band", "artist": {"id": "a", "name": "Band"}}]},
            {"id": "other-artist", "score": 100, "title": "Song", "artist-credit": [{"name": "Cover", "artist": {"id": "c", "name": "Cover"}}]},
            {"id": "good", "score": 98, "title": "Song", "first-release-date": "1997-06-16",
             "artist-credit": [{"name": "Band", "artist": {"id": "a1", "name": "Band"}}],
             "releases": [{"title": "The LP"}]},
        ]}

    def test_picks_confident_match_with_the_right_artist(self):
        with mock.patch.object(self.client.http, "get_json", return_value=self.payload()):
            found = self.client.find_recording("Song", "Band")
        self.assertEqual((found.mbid, found.year, found.album, found.artist_mbid), ("good", 1997, "The LP", "a1"))

    def test_no_confident_match_returns_none(self):
        with mock.patch.object(self.client.http, "get_json", return_value=self.payload()):
            self.assertIsNone(self.client.find_recording("Song", "Someone Else"))

    def test_query_escapes_quotes(self):
        with mock.patch.object(self.client.http, "get_json", return_value={"recordings": []}) as get:
            self.client.find_recording('Say "Hi"', "Band")
        self.assertIn('\\"Hi\\"', get.call_args[0][1]["query"])


class TheAudioDbClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.client = TheAudioDbClient("test-key", Path(self.tmp.name))

    def test_falls_back_to_shared_test_key_when_unset(self):
        client = TheAudioDbClient("", Path(self.tmp.name))
        self.assertEqual(client.api_key, "123")

    def test_artist_by_name_returns_thumb(self):
        payload = {"artists": [{"strArtist": "Band", "strArtistThumb": "http://img/x.jpg", "strMusicBrainzID": "abc"}]}
        with mock.patch.object(self.client.http, "get_json", return_value=payload):
            found = self.client.artist_by_name("Band")
        self.assertEqual((found.name, found.thumb_url, found.mbid), ("Band", "http://img/x.jpg", "abc"))

    def test_artist_by_mbid_uses_the_mb_endpoint(self):
        payload = {"artists": [{"strArtist": "Band", "strArtistThumb": "http://img/x.jpg"}]}
        with mock.patch.object(self.client.http, "get_json", return_value=payload) as get:
            self.client.artist_by_mbid("some-mbid")
        self.assertIn("artist-mb.php", get.call_args[0][0])
        self.assertEqual(get.call_args[0][1], {"i": "some-mbid"})

    def test_no_match_returns_none(self):
        with mock.patch.object(self.client.http, "get_json", return_value={"artists": None}):
            self.assertIsNone(self.client.artist_by_name("Nobody"))

    def test_biography_comes_from_the_same_response(self):
        payload = {"artists": [{"strArtist": "Band", "strArtistThumb": "http://img/x.jpg", "strBiographyEN": "  A band.  "}]}
        with mock.patch.object(self.client.http, "get_json", return_value=payload):
            found = self.client.artist_by_name("Band")
        self.assertEqual((found.thumb_url, found.bio), ("http://img/x.jpg", "A band."))

    def test_biography_without_a_photo_is_still_returned(self):
        payload = {"artists": [{"strArtist": "Band", "strArtistThumb": "", "strBiographyEN": "A band."}]}
        with mock.patch.object(self.client.http, "get_json", return_value=payload):
            found = self.client.artist_by_name("Band")
        self.assertEqual((found.thumb_url, found.bio), ("", "A band."))

    def test_match_without_a_thumb_returns_none(self):
        payload = {"artists": [{"strArtist": "Band", "strArtistThumb": ""}]}
        with mock.patch.object(self.client.http, "get_json", return_value=payload):
            self.assertIsNone(self.client.artist_by_name("Band"))

    def test_blank_lookups_are_skipped_without_a_request(self):
        with mock.patch.object(self.client.http, "get_json") as get:
            self.assertIsNone(self.client.artist_by_mbid(""))
            self.assertIsNone(self.client.artist_by_name("  "))
        get.assert_not_called()


class YouTubeClientTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.client = YouTubeClient("test-key", Path(self.tmp.name))

    def test_requires_a_key(self):
        with self.assertRaises(IntegrationError):
            YouTubeClient("", Path(self.tmp.name))

    def test_returns_first_video(self):
        payload = {"items": [{"id": {"videoId": "abc123"}, "snippet": {"title": "Song", "channelTitle": "ArtistVEVO"}}]}
        with mock.patch.object(self.client.http, "get_json", return_value=payload):
            video = self.client.find_video("Artist", "Song")
        self.assertEqual((video.video_id, video.title, video.channel), ("abc123", "Song", "ArtistVEVO"))

    def test_asks_only_for_embeddable_videos(self):
        with mock.patch.object(self.client.http, "get_json", return_value={"items": []}) as get:
            self.client.find_video("Artist", "Song")
        params = get.call_args[0][1]
        self.assertEqual((params["type"], params["videoEmbeddable"], params["q"]), ("video", "true", "Artist Song"))

    def test_no_results_returns_none(self):
        with mock.patch.object(self.client.http, "get_json", return_value={"items": []}):
            self.assertIsNone(self.client.find_video("Artist", "Song"))

    def test_api_key_is_kept_out_of_the_cache_file_name(self):
        self.assertIn("key", self.client.http.secret_params)


if __name__ == "__main__":
    unittest.main()
