import unittest

from pydantic import ValidationError
from fastapi.testclient import TestClient

from main import CreateSoundtrackRequest, GeneratePlaylistRequest, SongRequest, app


class RequestValidationTests(unittest.TestCase):
    def test_rejects_blank_and_oversized_prompts(self):
        with self.assertRaises(ValidationError):
            GeneratePlaylistRequest(prompt="   ")
        with self.assertRaises(ValidationError):
            GeneratePlaylistRequest(prompt="x" * 301)

    def test_rejects_invalid_spotify_uri(self):
        with self.assertRaises(ValidationError):
            SongRequest(title="Song", artist="Artist", spotify_uri="https://example.com")

    def test_rejects_more_than_ten_songs(self):
        songs = [SongRequest(title=f"Song {index}", artist=f"Artist {index}") for index in range(11)]
        with self.assertRaises(ValidationError):
            CreateSoundtrackRequest(prompt="test", playlist_name="Test", songs=songs)


class ApiGuardTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_generation_rejects_oversized_prompt(self):
        response = self.client.post("/generate_playlist", json={"prompt": "x" * 301})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json(), {"error": "invalid_request"})

    def test_guest_spotify_creation_requires_saved_soundtrack(self):
        response = self.client.post(
            "/spotify_playlist",
            json={
                "playlist_name": "Test",
                "songs": [{"title": "Song", "artist": "Artist"}],
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Missing soundtrack"})

    def test_rejects_large_request_before_parsing(self):
        response = self.client.post(
            "/soundtracks",
            content=b"x" * 32769,
            headers={"content-type": "application/json"},
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json(), {"error": "request_too_large"})


if __name__ == "__main__":
    unittest.main()
