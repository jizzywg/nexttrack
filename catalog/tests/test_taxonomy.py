import tempfile
import unittest
from pathlib import Path

from catalog.dataset import DEMO_CSV, parse_genres, read_track_rows
from catalog.taxonomy import (
    MOODS,
    clean_genre_tags,
    infer_mood,
    infer_year,
    is_genre_tag,
    normalise_tag,
)


class TaxonomyTests(unittest.TestCase):
    def test_normalise_resolves_aliases_and_case(self):
        self.assertEqual(normalise_tag("  Hip-Hop "), "hip hop")
        self.assertEqual(normalise_tag("RnB"), "r&b")
        self.assertEqual(normalise_tag("Indie_Rock"), "indie rock")

    def test_non_genre_tags_are_rejected(self):
        for tag in ("seen live", "90s", "1980s", "chill", "favorites", ""):
            self.assertFalse(is_genre_tag(tag), tag)
        self.assertTrue(is_genre_tag("post-punk"))

    def test_clean_genre_tags_filters_scales_and_limits(self):
        raw = [("rock", 100), ("Seen Live", 90), ("indie rock", 55), ("90s", 40), ("noise", 5), ("Hip-Hop", 30)]
        cleaned = clean_genre_tags(raw, limit=3)
        self.assertEqual(list(cleaned), ["rock", "indie rock", "hip hop"])
        self.assertAlmostEqual(cleaned["indie rock"], 0.55)
        self.assertNotIn("noise", cleaned)

    def test_clean_genre_tags_merges_aliases_with_max_weight(self):
        cleaned = clean_genre_tags({"hip-hop": 40, "hip hop": 70, "rap": 10})
        self.assertEqual(cleaned, {"hip hop": 0.7})

    def test_infer_mood(self):
        self.assertEqual(infer_mood({"chill": 80, "rock": 100, "relax": 30}), "chill")
        self.assertEqual(infer_mood({"sad": 10, "happy": 50}), "happy")
        self.assertIsNone(infer_mood({"rock": 100}))

    def test_infer_year_from_decade_tags(self):
        self.assertEqual(infer_year({"80s": 50, "rock": 100}), 1985)
        self.assertEqual(infer_year({"2010s": 20}), 2015)
        self.assertEqual(infer_year({"00s": 20}), 2005)
        self.assertIsNone(infer_year({"rock": 100}))


class DatasetTests(unittest.TestCase):
    def test_parse_genres(self):
        self.assertEqual(parse_genres("indie rock:0.9;Alternative;rock:2"), {"indie rock": 0.9, "alternative": 1.0, "rock": 1.0})
        self.assertEqual(parse_genres(""), {})
        with self.assertRaises(ValueError):
            parse_genres("rock:high")

    def test_demo_csv_is_valid(self):
        rows = read_track_rows(DEMO_CSV)
        self.assertGreater(len(rows), 100)
        for row in rows:
            self.assertTrue(row["genres"], row["title"])
            self.assertTrue(row["mood"] in MOODS or row["mood"] == "")
        pairs = [(r["title"], r["artist"]) for r in rows]
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_bad_rows_report_line_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.csv"
            path.write_text("title,artist,year,mood,genres\nA,B,abcd,happy,rock\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Line 2"):
                read_track_rows(path)
            path.write_text("title,artist,year,mood,genres\nA,B,1999,gloomy,rock\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unknown mood"):
                read_track_rows(path)
            path.write_text("name,artist\nA,B\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing required"):
                read_track_rows(path)


if __name__ == "__main__":
    unittest.main()
