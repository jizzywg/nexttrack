import unittest

from recommender.bridge import build_bridge
from recommender.engine import Recommender, TrackProfile, UnknownTrackError, Weights


def profile(i, genres, mood=None, tempo=None, year=None, artist_id=None):
    return TrackProfile(id=i, title=f"Track {i}", artist=f"Artist {artist_id or i}", artist_id=artist_id or i,
                        genres=genres, mood=mood, tempo=tempo, year=year)


class BridgeGuardTests(unittest.TestCase):
    def setUp(self):
        self.rec = Recommender([profile(1, {"rock": 1.0}), profile(2, {"jazz": 1.0}), profile(3, {"pop": 1.0})])

    def test_same_track_is_rejected(self):
        with self.assertRaises(ValueError):
            build_bridge(self.rec, 1, 1, 5)

    def test_too_short_a_length_is_rejected(self):
        with self.assertRaises(ValueError):
            build_bridge(self.rec, 1, 2, 1)

    def test_unknown_track_ids_are_rejected(self):
        with self.assertRaises(UnknownTrackError):
            build_bridge(self.rec, 999, 2, 5)
        with self.assertRaises(UnknownTrackError):
            build_bridge(self.rec, 1, 999, 5)

    def test_minimum_length_is_just_the_two_endpoints(self):
        path = build_bridge(self.rec, 1, 2, 2)
        self.assertEqual([h["track"].id for h in path], [1, 2])


class BridgeShapeTests(unittest.TestCase):
    def setUp(self):
        profiles = []
        for a in range(3):
            for n in range(6):
                profiles.append(profile(a * 6 + n + 1, {"rock": 1.0}, mood="energetic", tempo=100 + n, year=1970 + n, artist_id=a + 1))
        self.rec = Recommender(profiles)

    def test_path_has_the_requested_length_and_the_right_endpoints(self):
        path = build_bridge(self.rec, 1, 18, 7)
        self.assertEqual(len(path), 7)
        self.assertEqual(path[0]["track"].id, 1)
        self.assertEqual(path[-1]["track"].id, 18)

    def test_every_track_is_used_at_most_once(self):
        path = build_bridge(self.rec, 1, 18, 9)
        ids = [h["track"].id for h in path]
        self.assertEqual(len(set(ids)), len(ids))

    def test_first_hop_has_no_score_the_rest_do(self):
        path = build_bridge(self.rec, 1, 18, 5)
        self.assertIsNone(path[0]["score"])
        self.assertIsNone(path[0]["contributions"])
        self.assertEqual(path[0]["reasons"], [])
        for hop in path[1:]:
            self.assertIsInstance(hop["score"], float)
            self.assertIsInstance(hop["contributions"], dict)

    def test_no_two_consecutive_tracks_share_an_artist_including_the_final_hop(self):
        for _ in range(15):
            path = build_bridge(self.rec, 1, 18, 9)
            artists = [h["track"].artist_id for h in path]
            for i in range(len(artists) - 1):
                self.assertNotEqual(artists[i], artists[i + 1], [h["track"].id for h in path])

    def test_deterministic_for_the_same_inputs(self):
        self.assertEqual(
            [h["track"].id for h in build_bridge(self.rec, 1, 18, 7)],
            [h["track"].id for h in build_bridge(self.rec, 1, 18, 7)],
        )

    def test_custom_weights_are_accepted(self):
        path = build_bridge(self.rec, 1, 18, 5, Weights.from_mapping({"genre": 1.0}))
        self.assertEqual(len(path), 5)


if __name__ == "__main__":
    unittest.main()
