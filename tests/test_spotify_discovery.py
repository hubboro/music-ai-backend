import unittest

from spotify_utils import _interleave_candidate_groups, _is_avoided_track, _strategy_search_specs


def discovered(title, artist, uri_suffix):
    return {
        "title": title,
        "artist": artist,
        "primary_artist": artist,
        "spotify_uri": f"spotify:track:{uri_suffix}",
    }


class SpotifyDiscoveryStrategyTests(unittest.TestCase):
    def test_strategy_search_specs_expand_and_dedupe_queries(self):
        strategy = {
            "seed_artists": ["Broadcast", "Broadcast", "Stereolab"],
            "search_queries": ["library music psych pop", "library music psych pop"],
            "genres": ["krautrock"],
            "moods": ["rainy", "warm"],
        }

        specs = _strategy_search_specs(strategy)

        self.assertEqual(
            specs,
            [
                ("Broadcast", "seed_artist"),
                ("Stereolab", "seed_artist"),
                ("library music psych pop", "scene"),
                ("krautrock rainy", "genre_mood"),
                ("krautrock warm", "genre_mood"),
            ],
        )

    def test_avoid_lists_filter_exact_artist_or_track_matches(self):
        strategy = {
            "avoid_artists": ["MGMT"],
            "avoid_tracks": ["Electric Feel"],
        }

        self.assertTrue(
            _is_avoided_track(
                {"title": "Fresh Track", "artist": "MGMT", "primary_artist": "MGMT"},
                strategy,
            )
        )
        self.assertTrue(
            _is_avoided_track(
                {"title": "Electric Feel", "artist": "Different Artist", "primary_artist": "Different Artist"},
                strategy,
            )
        )
        self.assertFalse(
            _is_avoided_track(
                {"title": "Fresh Track", "artist": "Different Artist", "primary_artist": "Different Artist"},
                strategy,
            )
        )

    def test_interleaves_candidate_groups_before_capping(self):
        groups = [
            [discovered("A1", "Artist A", "a1"), discovered("A2", "Artist A", "a2")],
            [discovered("B1", "Artist B", "b1"), discovered("B2", "Artist B", "b2")],
            [discovered("C1", "Artist C", "c1"), discovered("C2", "Artist C", "c2")],
        ]

        candidates = _interleave_candidate_groups(groups, max_candidates=4)

        self.assertEqual([candidate["title"] for candidate in candidates], ["A1", "B1", "C1", "A2"])


if __name__ == "__main__":
    unittest.main()
