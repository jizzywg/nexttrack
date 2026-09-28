import math
import unittest

from recommender.engine import Recommender, TrackProfile
from recommender.tastemap import FAMILY_ORDER, build_layout, genre_family, genre_root, layout

try:
    import sklearn  # noqa: F401
    HAVE_SKLEARN = True
except ImportError:
    HAVE_SKLEARN = False


def profile(i, genres, mood=None, tempo=None, year=None):
    return TrackProfile(id=i, title=f"Track {i}", artist=f"Artist {i}", artist_id=i, genres=genres, mood=mood, tempo=tempo, year=year)


class FamilyTests(unittest.TestCase):
    def test_top_genre_decides_the_family(self):
        self.assertEqual(genre_family({"hard rock": 1.0, "pop": 0.4}), "rock")
        self.assertEqual(genre_family({"pop": 0.4, "hard rock": 1.0}), "rock")

    def test_subgenres_roll_up_to_their_root(self):
        self.assertEqual(genre_root("hard rock"), "rock")
        self.assertEqual(genre_family({"disco": 1.0}), genre_family({genre_root("disco"): 1.0}))

    def test_unknown_or_missing_genres_are_other(self):
        self.assertEqual(genre_family({}), "other")
        self.assertEqual(genre_family({"not a real genre": 1.0}), "other")
        self.assertIn("other", FAMILY_ORDER)


class SmallLayoutTests(unittest.TestCase):
    def test_tiny_catalogues_get_well_defined_positions(self):
        self.assertEqual(layout([]), [])
        self.assertEqual(layout([[0.0]]), [(0.5, 0.5)])
        four = layout([[0.0 if i == j else 1.0 for j in range(4)] for i in range(4)])
        self.assertEqual(len(set(four)), 4)
        self.assertTrue(all(0 <= v <= 1 for point in four for v in point))


@unittest.skipUnless(HAVE_SKLEARN, "scikit-learn is not installed")
class LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rock = [profile(i, {"rock": 1.0}, mood="energetic", tempo=120 + i, year=1975) for i in range(1, 21)]
        jazz = [profile(i, {"jazz": 1.0}, mood="chill", tempo=80 + i, year=1959) for i in range(21, 41)]
        cls.rec = Recommender(rock + jazz)
        cls.positions = build_layout(cls.rec)

    def test_every_track_is_placed_in_the_unit_square(self):
        self.assertEqual(set(self.positions), set(range(1, 41)))
        self.assertTrue(all(0 <= v <= 1 for point in self.positions.values() for v in point))

    def test_same_seed_gives_the_same_layout(self):
        self.assertEqual(build_layout(self.rec), self.positions)

    def test_similar_songs_are_placed_together(self):
        def centre(ids):
            pts = [self.positions[i] for i in ids]
            return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
        rock_c, jazz_c = centre(range(1, 21)), centre(range(21, 41))
        for i in range(1, 41):
            own, other = (rock_c, jazz_c) if i <= 20 else (jazz_c, rock_c)
            self.assertLess(math.dist(self.positions[i], own), math.dist(self.positions[i], other), f"track {i}")

    def test_dots_do_not_sit_on_top_of_each_other(self):
        pts = list(self.positions.values())
        gap = min(math.dist(a, b) for n, a in enumerate(pts) for b in pts[n + 1:])
        self.assertGreater(gap, 0.28 / math.sqrt(len(pts)) * 0.9)


if __name__ == "__main__":
    unittest.main()
