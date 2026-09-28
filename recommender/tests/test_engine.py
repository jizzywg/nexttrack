import math
import unittest

from catalog.dataset import DEMO_CSV, read_track_rows
from recommender.engine import (
    Recommender,
    TrackProfile,
    UnknownTrackError,
    Weights,
    cosine,
    decade_similarity,
    expand_genres,
    explain,
    mood_similarity,
    profiles_from_rows,
    tempo_similarity,
)
from recommender.presenters import RECENCY_WEIGHTS, history_seeds, run_recommendation


def profile(i, artist_id=None, genres=None, mood=None, tempo=None, year=None, title=None, popularity=0):
    return TrackProfile(
        id=i,
        title=title or f"Track {i}",
        artist=f"Artist {artist_id or i}",
        artist_id=artist_id or i,
        genres=genres or {},
        mood=mood,
        tempo=tempo,
        year=year,
        popularity=popularity,
    )


class FeatureSimilarityTests(unittest.TestCase):
    def test_tempo_identical_is_one(self):
        self.assertAlmostEqual(tempo_similarity(120, 120), 1.0)

    def test_tempo_decreases_with_distance(self):
        self.assertGreater(tempo_similarity(120, 124), tempo_similarity(120, 140))

    def test_tempo_allows_half_time_but_below_exact_match(self):
        half = tempo_similarity(170, 85)
        self.assertGreater(half, tempo_similarity(170, 120))
        self.assertLess(half, 1.0)

    def test_tempo_missing_is_none(self):
        self.assertIsNone(tempo_similarity(None, 120))
        self.assertIsNone(tempo_similarity(0, 120))

    def test_decade_symmetry_and_decay(self):
        self.assertAlmostEqual(decade_similarity(1994, 1994), 1.0)
        self.assertAlmostEqual(decade_similarity(1980, 2000), decade_similarity(2000, 1980))
        self.assertGreater(decade_similarity(1994, 1998), decade_similarity(1994, 2020))
        self.assertIsNone(decade_similarity(None, 2000))

    def test_close_mood_reason_uses_the_right_indefinite_article(self):
        seed = profile(1, mood="chill")
        vowel = profile(2, mood="energetic")
        consonant = profile(3, mood="romantic")
        sims = {"mood": 0.6}
        reasons_v = explain(seed, vowel, sims, {"mood": 0.5})
        reasons_c = explain(seed, consonant, sims, {"mood": 0.5})
        self.assertIn("An energetic mood close to chill", reasons_v)
        self.assertIn("A romantic mood close to chill", reasons_c)

    def test_mood_close_moods_beat_distant_moods(self):
        self.assertAlmostEqual(mood_similarity("chill", "chill"), 1.0)
        self.assertGreater(mood_similarity("euphoric", "happy"), mood_similarity("euphoric", "melancholic"))
        self.assertIsNone(mood_similarity(None, "chill"))
        self.assertIsNone(mood_similarity("nonsense", "chill"))

    def test_genre_expansion_adds_decaying_parents(self):
        expanded = expand_genres({"indie rock": 1.0})
        self.assertEqual(expanded["indie rock"], 1.0)
        self.assertAlmostEqual(expanded["rock"], 0.5)
        self.assertNotIn("jazz", expanded)

    def test_cosine_handles_empty_vectors(self):
        self.assertIsNone(cosine({}, 0.0, {"a": 1.0}, 1.0))
        self.assertAlmostEqual(cosine({"a": 1.0}, 1.0, {"a": 2.0}, 2.0), 1.0)


class WeightsTests(unittest.TestCase):
    def test_normalised_sums_to_one(self):
        w = Weights(2, 1, 1, 0).normalised()
        self.assertAlmostEqual(sum(w.as_dict().values()), 1.0)
        self.assertAlmostEqual(w.genre, 0.5)

    def test_all_zero_rejected(self):
        with self.assertRaises(ValueError):
            Weights(0, 0, 0, 0).normalised()

    def test_negative_rejected(self):
        with self.assertRaises(ValueError):
            Weights(-1, 1, 1, 1)

    def test_from_mapping_missing_features_are_zero_and_unknown_rejected(self):
        w = Weights.from_mapping({"genre": 1})
        self.assertEqual((w.mood, w.tempo, w.decade), (0.0, 0.0, 0.0))
        with self.assertRaises(ValueError):
            Weights.from_mapping({"loudness": 1})


class RecommenderTests(unittest.TestCase):
    def setUp(self):
        self.profiles = [
            profile(1, genres={"punk rock": 1.0}, mood="energetic", tempo=170, year=1995),
            profile(2, artist_id=2, genres={"punk rock": 1.0}, mood="energetic", tempo=172, year=1996),
            profile(3, artist_id=3, genres={"punk": 1.0}, mood="aggressive", tempo=165, year=1990),
            profile(4, artist_id=4, genres={"jazz": 1.0}, mood="chill", tempo=90, year=1959),
            profile(5, artist_id=5, genres={"ambient": 1.0}, mood="chill", tempo=None, year=None),
            profile(6, artist_id=6, genres={}, mood=None, tempo=None, year=None),
        ]
        self.rec = Recommender(self.profiles)

    def ids(self, results):
        return [r.profile.id for r in results]

    def test_nearest_neighbour_is_the_most_similar_track(self):
        results = self.rec.recommend([1], k=3, diversity=0.0)
        self.assertEqual(results[0].profile.id, 2)
        self.assertEqual(self.ids(results)[:2], [2, 3])

    def test_seed_is_never_recommended(self):
        self.assertNotIn(1, self.ids(self.rec.recommend([1], k=10)))

    def test_scores_are_between_zero_and_one_and_contributions_sum_to_score(self):
        for r in self.rec.recommend([1], k=5, diversity=0.0):
            self.assertGreaterEqual(r.score, 0.0)
            self.assertLessEqual(r.score, 1.0)
            self.assertAlmostEqual(sum(r.contributions.values()), r.score, places=6)

    def test_unknown_seed_raises(self):
        with self.assertRaises(UnknownTrackError):
            self.rec.recommend([999])

    def test_empty_seeds_rejected(self):
        with self.assertRaises(ValueError):
            self.rec.recommend([])

    def test_invalid_options_rejected(self):
        with self.assertRaises(ValueError):
            self.rec.recommend([1], k=0)
        with self.assertRaises(ValueError):
            self.rec.recommend([1], aggregate="median")
        with self.assertRaises(ValueError):
            self.rec.recommend([1], diversity=1.5)

    def test_missing_metadata_tracks_can_still_be_recommended(self):
        results = self.rec.recommend([4], k=5, diversity=0.0)
        self.assertIn(5, self.ids(results))
        self.assertEqual(self.rec.similarity(6, 1).score, 0.0)

    def test_missing_features_are_penalised_relative_to_complete_matches(self):
        full = profile(10, artist_id=10, genres={"jazz": 1.0}, mood="chill", tempo=90, year=1959)
        sparse = profile(11, artist_id=11, genres={"jazz": 1.0}, mood="chill", tempo=None, year=None)
        seed = profile(12, artist_id=12, genres={"jazz": 1.0}, mood="chill", tempo=90, year=1959)
        rec = Recommender([full, sparse, seed])
        self.assertGreater(rec.similarity(12, 10).score, rec.similarity(12, 11).score)

    def test_weights_change_the_ranking(self):
        genre_only = self.rec.recommend([1], k=2, weights=Weights.from_mapping({"genre": 1}), diversity=0.0)
        mood_only = self.rec.recommend([1], k=2, weights=Weights.from_mapping({"mood": 1}), diversity=0.0)
        self.assertEqual(genre_only[0].profile.id, 2)
        self.assertEqual(mood_only[0].profile.id, 2)
        self.assertLess(mood_only[1].score, mood_only[0].score)

    def test_per_artist_cap_is_enforced(self):
        profiles = [profile(1, artist_id=1, genres={"pop": 1.0})]
        profiles += [profile(i, artist_id=99, genres={"pop": 1.0}) for i in range(2, 8)]
        profiles += [profile(i, artist_id=i, genres={"pop": 0.5}) for i in range(8, 12)]
        rec = Recommender(profiles)
        results = rec.recommend([1], k=6, max_per_artist=2, diversity=0.0)
        artists = [r.profile.artist_id for r in results]
        self.assertLessEqual(artists.count(99), 2)

    def test_dislikes_are_excluded_and_penalise_lookalikes(self):
        baseline = {r.profile.id: r.score for r in self.rec.recommend([4], k=5, diversity=0.0)}
        penalised = self.rec.recommend([4], k=5, diversity=0.0, disliked=[5])
        self.assertNotIn(5, self.ids(penalised))
        self.assertTrue(all(r.score <= baseline.get(r.profile.id, 1.0) + 1e-9 for r in penalised))

    def test_multiple_seeds_blend_and_max_picks_closest_to_any(self):
        blend = self.rec.recommend([1, 4], k=3, aggregate="mean", diversity=0.0)
        nearest = self.rec.recommend([1, 4], k=3, aggregate="max", diversity=0.0)
        self.assertEqual(len(blend), 3)
        self.assertGreaterEqual(nearest[0].score, blend[0].score)

    def test_diversity_zero_gives_descending_scores(self):
        scores = [r.score for r in self.rec.recommend([1], k=5, diversity=0.0)]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_reasons_mention_shared_genre(self):
        top = self.rec.recommend([1], k=1, diversity=0.0)[0]
        self.assertTrue(any("punk rock" in reason for reason in top.reasons))

    def test_duplicate_ids_rejected(self):
        with self.assertRaises(ValueError):
            Recommender([profile(1), profile(1)])

    def test_empty_catalogue_is_supported(self):
        rec = Recommender([])
        self.assertEqual(len(rec), 0)


class PresenterTests(unittest.TestCase):
    def test_payload_shape(self):
        rec = Recommender(
            [
                profile(1, genres={"rock": 1.0}, mood="happy", tempo=120, year=2000),
                profile(2, genres={"rock": 1.0}, mood="happy", tempo=121, year=2001),
                profile(3, genres={"rock": 0.5}, mood="dark", tempo=90, year=1980),
            ]
        )
        payload = run_recommendation(rec, seeds=[1], k=2, weights={"genre": 3, "mood": 1})
        self.assertEqual(payload["count"], 2)
        self.assertAlmostEqual(sum(payload["weights"].values()), 1.0, places=3)
        first = payload["results"][0]
        self.assertEqual(first["rank"], 1)
        self.assertEqual(first["track"]["id"], 2)
        self.assertEqual(first["because"]["id"], 1)
        self.assertEqual(set(first["contributions"]), {"genre", "mood", "tempo", "decade"})

    def test_liked_tracks_join_seeds_at_lower_weight(self):
        rec = Recommender([profile(i, genres={"rock": 1.0}) for i in range(1, 6)])
        payload = run_recommendation(rec, seeds=[1], liked=[2, 1, 999], disliked=[3])
        self.assertEqual([t["id"] for t in payload["liked_used"]], [2])
        returned = [r["track"]["id"] for r in payload["results"]]
        self.assertNotIn(3, returned)
        self.assertNotIn(2, returned)

    def test_history_seeds_weight_the_most_recent_songs_most(self):
        self.assertEqual(history_seeds([1, 2, 3, 4]), [(4, 1.0), (3, 0.6), (2, 0.35)])
        self.assertEqual(history_seeds([1, 2, 1]), [(1, 1.0), (2, 0.6)])
        self.assertEqual(history_seeds([]), [])
        self.assertEqual(len(RECENCY_WEIGHTS), 3)

    def test_radio_follows_the_latest_song_and_skips_what_was_played(self):
        rec = Recommender([
            profile(1, genres={"rock": 1.0}), profile(2, genres={"jazz": 1.0}),
            profile(3, genres={"rock": 1.0}), profile(4, genres={"jazz": 1.0}),
        ])
        payload = run_recommendation(rec, seeds=[], history=[1, 2], k=2, weights={"genre": 1}, diversity=0.0)
        returned = [r["track"]["id"] for r in payload["results"]]
        self.assertEqual(returned[0], 4)
        self.assertNotIn(1, returned)
        self.assertNotIn(2, returned)
        self.assertEqual([(h["track"]["id"], h["weight"]) for h in payload["history_used"]], [(2, 1.0), (1, 0.6)])
        self.assertEqual(payload["seeds"], [])
        self.assertEqual(payload["options"]["history_length"], 2)

    def test_history_and_explicit_seeds_combine(self):
        rec = Recommender([profile(i, genres={"rock": 1.0}) for i in range(1, 6)])
        payload = run_recommendation(rec, seeds=[1], history=[2, 3], k=5)
        returned = {r["track"]["id"] for r in payload["results"]}
        self.assertTrue(returned.isdisjoint({1, 2, 3}))
        self.assertEqual([t["id"] for t in payload["seeds"]], [1])

    def test_without_history_the_response_is_unchanged(self):
        rec = Recommender([profile(i, genres={"rock": 1.0}) for i in range(1, 6)])
        payload = run_recommendation(rec, seeds=[1], k=3)
        self.assertEqual(payload["history_used"], [])
        self.assertEqual(payload["options"]["history_length"], 0)


class DemoCatalogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = read_track_rows(DEMO_CSV)
        cls.profiles = profiles_from_rows(cls.rows)
        cls.rec = Recommender(cls.profiles)
        cls.by_title = {p.title: p for p in cls.profiles}

    def test_catalogue_loads(self):
        self.assertGreater(len(self.profiles), 100)
        self.assertEqual(len({p.id for p in self.profiles}), len(self.profiles))

    def test_house_seed_recommends_electronic_or_dance_tracks(self):
        seed = self.by_title["One More Time"]
        top = self.rec.recommend([seed.id], k=5, diversity=0.0)
        related = {"house", "electronic", "disco", "dance pop", "progressive house"}
        hits = sum(1 for r in top if related & set(r.profile.genres))
        self.assertGreaterEqual(hits, 4)

    def test_punk_seed_recommends_punk_family(self):
        seed = self.by_title["Blitzkrieg Bop"]
        top = self.rec.recommend([seed.id], k=3, diversity=0.0)
        self.assertTrue(all({"punk rock", "punk"} & set(r.profile.genres) for r in top))

    def test_scores_are_finite(self):
        seed = self.by_title["Creep"]
        for r in self.rec.recommend([seed.id], k=20):
            self.assertTrue(math.isfinite(r.score))


if __name__ == "__main__":
    unittest.main()
