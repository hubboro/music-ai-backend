import unittest

from playlist_engine import rerank_candidates, score_candidate


def candidate(title, artist, bucket="discovery", familiarity="medium", energy=0.5, score=90):
    return {
        "title": title,
        "artist": artist,
        "spotify_uri": f"spotify:track:{title.replace(' ', '')[:8]}",
        "match_score": score,
        "bucket": bucket,
        "familiarity": familiarity,
        "energy": energy,
    }


class PlaylistEngineRerankerTests(unittest.TestCase):
    def test_score_penalizes_duplicate_artist(self):
        selected = [candidate("First", "Same Artist")]
        duplicate = candidate("Second", "Same Artist")

        self.assertLess(score_candidate(duplicate, selected=selected), 0)

    def test_reranker_prefers_discovery_mix_and_dedupes_artists(self):
        candidates = [
            candidate("Known 1", "Anchor One", "anchor", "known", 0.4),
            candidate("Known 2", "Anchor Two", "anchor", "known", 0.6),
            candidate("Known 3", "Anchor Three", "anchor", "known", 0.5),
            candidate("Discovery 1", "Discovery One", "discovery", "medium", 0.5),
            candidate("Discovery 2", "Discovery Two", "discovery", "medium", 0.55),
            candidate("Discovery 3", "Discovery Three", "discovery", "medium", 0.45),
            candidate("Discovery 4", "Discovery Four", "discovery", "medium", 0.65),
            candidate("Deep 1", "Deep One", "deep_cut", "obscure", 0.35),
            candidate("Deep 2", "Deep Two", "deep_cut", "obscure", 0.4),
            candidate("Wildcard", "Wildcard One", "wildcard", "medium", 0.7),
            candidate("Closer", "Closer One", "closer", "medium", 0.25),
            candidate("Duplicate", "Discovery One", "deep_cut", "obscure", 0.5),
        ]

        selected = rerank_candidates(candidates)
        artists = [track["artist"] for track in selected]
        discovery_count = sum(1 for track in selected if track["bucket"] in {"discovery", "deep_cut"})

        self.assertEqual(len(selected), 10)
        self.assertEqual(len(artists), len(set(artists)))
        self.assertGreaterEqual(discovery_count, 4)
        self.assertEqual(selected[-1]["bucket"], "closer")


if __name__ == "__main__":
    unittest.main()
