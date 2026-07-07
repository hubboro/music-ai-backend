import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError
from fastapi.testclient import TestClient

import main
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

    def test_generation_schedules_shadow_without_waiting(self):
        class BackgroundTaskCollector:
            def __init__(self):
                self.tasks = []

            def add_task(self, task, *args, **kwargs):
                self.tasks.append((task, args, kwargs))

        background_tasks = BackgroundTaskCollector()
        payload = GeneratePlaylistRequest(prompt="late train home")

        async def shadow_task(prompt, search_token):
            return None

        engine_result = {
            "name": "Late Train Home",
            "songs": [{"title": "Song", "artist": "Artist"}],
            "matched_songs": [{"title": "Song", "artist": "Artist", "spotify_uri": "spotify:track:abc"}],
            "engine_version": "v1",
        }

        with (
            patch.object(main, "enforce_rate_limit", return_value=None),
            patch.object(main, "get_spotify_search_token", return_value="search-token"),
            patch.object(main, "generate_playlist_from_engine", new=AsyncMock(return_value=engine_result)),
            patch.object(main, "should_run_shadow_v2", return_value=True),
            patch.object(main, "shadow_v2_config_label", return_value="enabled=True engine=v1 raw_shadow='true'"),
            patch.object(main, "run_shadow_v2", new=shadow_task),
            patch.object(main, "save_soundtrack", return_value={"slug": "late-train-home"}),
        ):
            response = asyncio.run(
                main.generate_playlist(
                    payload=payload,
                    request=object(),
                    background_tasks=background_tasks,
                )
            )

        self.assertEqual(response["playlist_name"], "Late Train Home")
        self.assertEqual(len(background_tasks.tasks), 1)
        task, args, kwargs = background_tasks.tasks[0]
        self.assertIs(task, shadow_task)
        self.assertEqual(args, ("late train home", "search-token"))
        self.assertEqual(kwargs, {})


if __name__ == "__main__":
    unittest.main()
