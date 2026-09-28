import io

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from catalog.models import Track
from catalog.services import upsert_track
from recommender.models import Feedback, ReferenceSimilarity
from recommender.services import invalidate_recommender

ROCK = {"punk rock": 1.0, "punk": 0.6}
JAZZ = {"jazz": 1.0, "vocal jazz": 0.6}


class ApiTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.t = {}
        specs = [
            ("Alpha", "Band A", ROCK, 1995, 170, "energetic"),
            ("Bravo", "Band B", ROCK, 1996, 172, "energetic"),
            ("Charlie", "Band C", ROCK, 1990, 165, "aggressive"),
            ("Delta", "Band D", {"punk rock": 1.0, "pop punk": 0.7}, 2004, 180, "energetic"),
            ("Echo", "Band E", JAZZ, 1959, 90, "chill"),
            ("Foxtrot", "Band F", JAZZ, 1962, 88, "chill"),
            ("Golf", "Band G", {"jazz": 1.0}, 1958, None, "chill"),
            ("Hotel", "Band H", {"ambient": 1.0, "electronic": 0.8}, None, None, "chill"),
            ("India", "Band I", {"house": 1.0, "electronic": 0.7}, 2001, 124, "euphoric"),
            ("Juliet", "Band J", {"house": 1.0}, 2003, 126, "euphoric"),
        ]
        for title, artist, genres, year, tempo, mood in specs:
            cls.t[title], _ = upsert_track(title, artist, genres, year=year, tempo=tempo, mood=mood, listeners=100)

    def setUp(self):
        cache.clear()
        invalidate_recommender()


class TrackEndpointTests(ApiTestCase):
    def test_api_root_lists_endpoints(self):
        response = self.client.get(reverse("api-root"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("recommendations", response.data["endpoints"])

    def test_list_is_paginated_and_filterable(self):
        response = self.client.get(reverse("track-list"), {"page_size": 3})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 10)
        self.assertEqual(len(response.data["results"]), 3)

        by_q = self.client.get(reverse("track-list"), {"q": "alp"})
        self.assertEqual([t["title"] for t in by_q.data["results"]], ["Alpha"])
        by_genre = self.client.get(reverse("track-list"), {"genre": "jazz"})
        self.assertEqual(by_genre.data["count"], 3)
        by_mood = self.client.get(reverse("track-list"), {"mood": "euphoric"})
        self.assertEqual(by_mood.data["count"], 2)
        by_decade = self.client.get(reverse("track-list"), {"decade": "1990s"})
        self.assertEqual(by_decade.data["count"], 3)

    def test_ordering_puts_missing_values_last(self):
        response = self.client.get(reverse("track-list"), {"ordering": "tempo", "page_size": 20})
        tempos = [t["tempo"] for t in response.data["results"]]
        self.assertEqual(tempos[:2], [88.0, 90.0])
        self.assertIsNone(tempos[-1])

    def test_random_ordering_works(self):
        response = self.client.get(reverse("track-list"), {"ordering": "random", "page_size": 4})
        self.assertEqual(len(response.data["results"]), 4)

    def test_detail_includes_genre_tags_and_decade(self):
        response = self.client.get(reverse("track-detail", args=[self.t["Alpha"].id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["artist"], "Band A")
        self.assertEqual(response.data["decade"], "1990s")
        self.assertEqual(response.data["genres"][0]["name"], "punk rock")

    def test_writes_require_authentication(self):
        response = self.client.post(reverse("track-list"), {"title": "X", "artist": "Y"}, format="json")
        self.assertIn(response.status_code, (401, 403))

    def test_create_update_and_duplicate_with_token(self):
        user = get_user_model().objects.create_user("writer", password="a-long-test-password")
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        payload = {
            "title": "New Song", "artist": "New Artist", "year": 2020, "tempo": 118, "mood": "happy",
            "genres": ["indie pop", {"name": "synthpop", "weight": 0.6}],
        }
        created = self.client.post(reverse("track-list"), payload, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        self.assertEqual({g["name"] for g in created.data["genres"]}, {"indie pop", "synthpop"})

        duplicate = self.client.post(reverse("track-list"), payload, format="json")
        self.assertEqual(duplicate.status_code, 400)

        url = reverse("track-detail", args=[created.data["id"]])
        self.assertEqual(self.client.patch(url, {"tempo": 99}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(url).status_code, 403)

        staff = get_user_model().objects.create_user("editor", password="a-long-test-password", is_staff=True)
        self.client.credentials()
        self.client.force_authenticate(staff)
        patched = self.client.patch(url, {"genres": ["disco"], "tempo": 121}, format="json")
        self.assertEqual(patched.status_code, 200, patched.data)
        self.assertEqual([g["name"] for g in patched.data["genres"]], ["disco"])
        self.assertEqual(patched.data["tempo"], 121.0)

    def test_validation_errors(self):
        user = get_user_model().objects.create_user("writer2", password="a-long-test-password")
        self.client.force_authenticate(user)
        bad = self.client.post(reverse("track-list"), {"title": "X", "artist": "Y", "mood": "gloomy", "tempo": 999}, format="json")
        self.assertEqual(bad.status_code, 400)
        self.assertIn("mood", bad.data)
        self.assertIn("tempo", bad.data)

    def test_genres_and_moods(self):
        genres = self.client.get(reverse("genre-list"))
        self.assertEqual(genres.data["results"][0]["name"], "punk rock")
        moods = self.client.get(reverse("mood-list"))
        self.assertEqual(moods.data["count"], 8)
        self.assertEqual({m["name"]: m["tracks"] for m in moods.data["results"]}["chill"], 4)


class RecommendationEndpointTests(ApiTestCase):
    def test_post_returns_ranked_explained_results(self):
        seed = self.t["Alpha"].id
        response = self.client.post(
            reverse("recommendations"), {"seeds": [seed], "k": 3, "diversity": 0}, format="json"
        )
        self.assertEqual(response.status_code, 200, response.data)
        data = response.data
        self.assertEqual(data["count"], 3)
        self.assertNotIn(seed, [r["track"]["id"] for r in data["results"]])
        first = data["results"][0]
        self.assertEqual(first["track"]["title"], "Bravo")
        self.assertEqual(set(first["contributions"]), {"genre", "mood", "tempo", "decade"})
        self.assertTrue(first["reasons"])
        self.assertAlmostEqual(sum(data["weights"].values()), 1.0, places=3)

    def test_get_with_query_parameters_and_weights(self):
        seed = self.t["Alpha"].id
        response = self.client.get(reverse("recommendations"), {"seeds": str(seed), "k": 2, "w_genre": 1, "w_mood": 1})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["weights"]["genre"], 0.5)
        self.assertEqual(response.data["weights"]["tempo"], 0.0)

    def test_multiple_seeds(self):
        seeds = [self.t["Alpha"].id, self.t["Echo"].id]
        response = self.client.post(reverse("recommendations"), {"seeds": seeds, "k": 4}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["seeds"]), 2)

    def test_similar_shortcut(self):
        response = self.client.get(reverse("track-similar", args=[self.t["Echo"].id]), {"k": 2})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["track"]["title"], "Foxtrot")
        self.assertEqual(self.client.get(reverse("track-similar", args=[999999])).status_code, 404)

    def test_validation(self):
        url = reverse("recommendations")
        self.assertEqual(self.client.post(url, {"seeds": []}, format="json").status_code, 400)
        self.assertEqual(self.client.post(url, {}, format="json").status_code, 400)
        unknown = self.client.post(url, {"seeds": [999999]}, format="json")
        self.assertEqual(unknown.status_code, 400)
        self.assertIn("seeds", unknown.data)
        seed = self.t["Alpha"].id
        self.assertEqual(self.client.post(url, {"seeds": [seed], "k": 500}, format="json").status_code, 400)
        zero = self.client.post(url, {"seeds": [seed], "weights": {"genre": 0, "mood": 0}}, format="json")
        self.assertEqual(zero.status_code, 400)
        self.assertEqual(self.client.post(url, {"seeds": [seed], "aggregate": "median"}, format="json").status_code, 400)

    def test_radio_history(self):
        url = reverse("recommendations")
        played = [self.t["Alpha"].id, self.t["Bravo"].id]
        response = self.client.post(url, {"history": played, "k": 3}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(set(played).isdisjoint(r["track"]["id"] for r in response.data["results"]))
        self.assertEqual([h["track"]["id"] for h in response.data["history_used"]], played[::-1])
        via_get = self.client.get(url, {"history": ",".join(map(str, played)), "k": 3})
        self.assertEqual(via_get.status_code, 200)
        self.assertEqual(via_get.data["options"]["history_length"], 2)
        unknown = self.client.post(url, {"history": [999999]}, format="json")
        self.assertEqual(unknown.status_code, 400)
        self.assertIn("history", unknown.data)

    def test_taste_map(self):
        from django.core.management import call_command

        url = reverse("taste-map")
        before = self.client.get(url)
        self.assertEqual(before.status_code, 200)
        self.assertEqual(before.data["tracks"], [])
        self.assertEqual(before.data["unplaced"], Track.objects.count())
        call_command("build_taste_map", stdout=io.StringIO())
        after = self.client.get(url).data
        self.assertEqual(after["unplaced"], 0)
        self.assertEqual(len(after["tracks"]), Track.objects.count())
        for point in after["tracks"]:
            self.assertTrue(0 <= point["x"] <= 1 and 0 <= point["y"] <= 1)
            self.assertIn(point["family"], after["families"])

    def test_bridge(self):
        url = reverse("bridge")
        a, b = self.t["Alpha"].id, self.t["Bravo"].id
        response = self.client.post(url, {"from_id": a, "to_id": b, "length": 3}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        path = response.data["path"]
        self.assertEqual(len(path), 3)
        self.assertEqual([p["track"]["id"] for p in path][0], a)
        self.assertEqual([p["track"]["id"] for p in path][-1], b)
        self.assertIsNone(path[0]["score"])
        self.assertIsInstance(path[1]["score"], float)

        same = self.client.post(url, {"from_id": a, "to_id": a, "length": 3}, format="json")
        self.assertEqual(same.status_code, 400)
        self.assertIn("to_id", same.data)

        unknown = self.client.post(url, {"from_id": 999999, "to_id": b, "length": 3}, format="json")
        self.assertEqual(unknown.status_code, 400)
        self.assertIn("from_id", unknown.data)

        too_short = self.client.post(url, {"from_id": a, "to_id": b, "length": 1}, format="json")
        self.assertEqual(too_short.status_code, 400)

    def test_exclude_and_artist_cap(self):
        seed = self.t["Alpha"].id
        excluded = self.t["Bravo"].id
        response = self.client.post(reverse("recommendations"), {"seeds": [seed], "exclude": [excluded], "k": 9}, format="json")
        self.assertNotIn(excluded, [r["track"]["id"] for r in response.data["results"]])

    def test_catalogue_changes_are_picked_up(self):
        seed = self.t["Alpha"].id
        before = self.client.post(reverse("recommendations"), {"seeds": [seed], "k": 30}, format="json").data["count"]
        upsert_track("Kilo", "Band K", ROCK, year=1995, tempo=170, mood="energetic")
        after = self.client.post(reverse("recommendations"), {"seeds": [seed], "k": 30}, format="json").data["count"]
        self.assertEqual(after, before + 1)


class FeedbackTests(ApiTestCase):
    def test_anonymous_feedback_round_trip_and_personalisation(self):
        url = reverse("feedback")
        liked, skipped, seed = self.t["Bravo"].id, self.t["Charlie"].id, self.t["Alpha"].id

        first = self.client.post(url, {"track": liked, "value": 1, "seeds": [seed]}, format="json")
        self.assertEqual(first.status_code, 201, first.data)
        again = self.client.post(url, {"track": liked, "value": 1}, format="json")
        self.assertEqual(again.status_code, 200)
        self.client.post(url, {"track": skipped, "value": -1}, format="json")
        self.assertEqual(Feedback.objects.count(), 2)
        self.assertEqual(len(self.client.get(url).data["results"]), 2)

        recs = self.client.post(reverse("recommendations"), {"seeds": [seed], "personalise": True, "k": 9}, format="json")
        self.assertEqual([t["id"] for t in recs.data["liked_used"]], [liked])
        self.assertNotIn(skipped, [r["track"]["id"] for r in recs.data["results"]])

        plain = self.client.post(reverse("recommendations"), {"seeds": [seed], "k": 9}, format="json")
        self.assertEqual(plain.data["liked_used"], [])

        cleared = self.client.post(url, {"track": skipped, "value": 0}, format="json")
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(Feedback.objects.count(), 1)

    def test_feedback_is_private_to_each_session(self):
        self.client.post(reverse("feedback"), {"track": self.t["Bravo"].id, "value": 1}, format="json")
        other = self.client_class()
        self.assertEqual(other.get(reverse("feedback")).data["results"], [])

    def test_signed_in_feedback_belongs_to_the_user(self):
        user = get_user_model().objects.create_user("fan", password="a-long-test-password")
        self.client.force_authenticate(user)
        self.client.post(reverse("feedback"), {"track": self.t["Bravo"].id, "value": -1}, format="json")
        self.assertEqual(Feedback.objects.get().user, user)

    def test_invalid_feedback(self):
        url = reverse("feedback")
        self.assertEqual(self.client.post(url, {"track": 999999, "value": 1}, format="json").status_code, 400)
        self.assertEqual(self.client.post(url, {"track": self.t["Alpha"].id, "value": 5}, format="json").status_code, 400)


class StatsEvaluationAndAuthTests(ApiTestCase):
    def test_stats(self):
        data = self.client.get(reverse("stats")).data
        self.assertEqual(data["tracks"], 10)
        self.assertEqual(data["missing_tempo"], 2)
        self.assertEqual(data["moods"]["chill"], 4)
        self.assertIn("1990s", data["decades"])

    def test_evaluation_without_reference_data(self):
        response = self.client.get(reverse("evaluation"), {"k": 3, "sample": 5})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["ground_truth"]["available"])
        names = [row["name"] for row in response.data["strategies"]]
        self.assertIn("NextTrack (all features)", names)
        self.assertIn("Random", names)
        self.assertTrue(all(row["ndcg"] is None for row in response.data["strategies"]))

    def test_evaluation_with_reference_data(self):
        a, b, c = self.t["Alpha"], self.t["Bravo"], self.t["Echo"]
        ReferenceSimilarity.objects.create(track=a, similar=b, match=1.0)
        ReferenceSimilarity.objects.create(track=c, similar=self.t["Foxtrot"], match=0.8)
        response = self.client.get(reverse("evaluation"), {"k": 3, "sample": 5})
        self.assertEqual(response.status_code, 200, response.data)
        gt = response.data["ground_truth"]
        self.assertTrue(gt["available"])
        self.assertEqual(gt["pairs"], 2)
        full = next(r for r in response.data["strategies"] if r["name"] == "NextTrack (all features)")
        self.assertEqual(full["n_scored"], 2)
        self.assertGreater(full["ndcg"]["mean"], 0)

    def test_evaluation_rejects_bad_parameters(self):
        self.assertEqual(self.client.get(reverse("evaluation"), {"k": "abc"}).status_code, 400)

    def test_register_then_use_token(self):
        response = self.client.post(
            reverse("register"), {"username": "newuser", "password": "a-long-test-password"}, format="json"
        )
        self.assertEqual(response.status_code, 201, response.data)
        token = response.data["token"]
        self.assertTrue(Token.objects.filter(key=token).exists())

        again = self.client.post(reverse("register"), {"username": "NewUser", "password": "a-long-test-password"}, format="json")
        self.assertEqual(again.status_code, 400)
        weak = self.client.post(reverse("register"), {"username": "other", "password": "123"}, format="json")
        self.assertEqual(weak.status_code, 400)

        login = self.client.post(reverse("token"), {"username": "newuser", "password": "a-long-test-password"}, format="json")
        self.assertEqual(login.data["token"], token)
