import math
import unittest

from recommender.engine import Recommender, TrackProfile
from recommender.evaluation import (
    bootstrap_ci,
    build_strategies,
    catalogue_coverage,
    evaluate,
    hit_rate_at_k,
    intra_list_diversity,
    ndcg_at_k,
    novelty,
    precision_at_k,
    recall_at_k,
)


class MetricTests(unittest.TestCase):
    def test_precision_recall_hit(self):
        recs = [1, 2, 3, 4]
        relevant = {2, 4, 9}
        self.assertAlmostEqual(precision_at_k(recs, relevant, 4), 0.5)
        self.assertAlmostEqual(recall_at_k(recs, relevant, 4), 2 / 3)
        self.assertEqual(hit_rate_at_k(recs, relevant, 1), 0.0)
        self.assertEqual(hit_rate_at_k(recs, relevant, 2), 1.0)
        self.assertEqual(recall_at_k(recs, set(), 4), 0.0)

    def test_ndcg_perfect_and_worst(self):
        relevance = {1: 1.0, 2: 0.5}
        self.assertAlmostEqual(ndcg_at_k([1, 2, 3], relevance, 3), 1.0)
        self.assertLess(ndcg_at_k([2, 1, 3], relevance, 3), 1.0)
        self.assertEqual(ndcg_at_k([7, 8, 9], relevance, 3), 0.0)
        self.assertEqual(ndcg_at_k([1], {}, 3), 0.0)

    def test_coverage(self):
        self.assertAlmostEqual(catalogue_coverage([[1, 2], [2, 3]], 6), 0.5)
        self.assertEqual(catalogue_coverage([], 0), 0.0)

    def test_diversity(self):
        same = intra_list_diversity([1, 2, 3], lambda a, b: 1.0)
        different = intra_list_diversity([1, 2, 3], lambda a, b: 0.0)
        self.assertAlmostEqual(same, 0.0)
        self.assertAlmostEqual(different, 1.0)
        self.assertEqual(intra_list_diversity([1], lambda a, b: 0.5), 0.0)

    def test_novelty_prefers_rare_tracks(self):
        popularity = {1: 1000, 2: 1}
        self.assertGreater(novelty([2], popularity, 2), novelty([1], popularity, 2))
        self.assertEqual(novelty([1], {1: 0, 2: 0}, 2), 0.0)

    def test_bootstrap_ci_brackets_the_mean(self):
        mean, lo, hi = bootstrap_ci([0.1, 0.2, 0.3, 0.4, 0.5], rng_seed=1)
        self.assertAlmostEqual(mean, 0.3)
        self.assertLessEqual(lo, mean)
        self.assertGreaterEqual(hi, mean)
        self.assertEqual(bootstrap_ci([]), (0.0, 0.0, 0.0))


def make_catalogue():
    profiles = []
    for i in range(1, 13):
        genre = "rock" if i <= 6 else "jazz"
        profiles.append(
            TrackProfile(
                id=i,
                title=f"T{i}",
                artist=f"A{i}",
                artist_id=i,
                genres={genre: 1.0},
                mood="energetic" if i <= 6 else "chill",
                tempo=120.0 if i <= 6 else 80.0,
                year=1990 if i <= 6 else 1960,
                popularity=100 - i,
            )
        )
    return Recommender(profiles)


class EvaluateTests(unittest.TestCase):
    def test_strategies_and_rows(self):
        rec = make_catalogue()
        strategies = build_strategies(rec, 3, rng_seed=1, popularity_available=True)
        for expected in ("NextTrack (all features)", "Without genre", "Genre only", "Random", "Most popular"):
            self.assertIn(expected, strategies)
        reference = {1: {2: 1.0, 3: 0.8}, 7: {8: 1.0}}
        rows = evaluate(rec, strategies, [1, 7], 3, reference=reference, rng_seed=1)
        by_name = {r["name"]: r for r in rows}
        full = by_name["NextTrack (all features)"]
        rand = by_name["Random"]
        self.assertEqual(full["n_scored"], 2)
        self.assertGreater(full["ndcg"]["mean"], rand["ndcg"]["mean"])
        self.assertTrue(0.0 <= full["coverage"] <= 1.0)
        self.assertIsNotNone(full["novelty"])

    def test_no_reference_means_no_accuracy_metrics(self):
        rec = make_catalogue()
        rows = evaluate(rec, build_strategies(rec, 3), [1, 2], 3)
        self.assertTrue(all(r["precision"] is None for r in rows))
        self.assertTrue(all(r["novelty"] is not None for r in rows))
        self.assertTrue(all(math.isfinite(r["latency_ms"]) for r in rows))


if __name__ == "__main__":
    unittest.main()
