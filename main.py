import asyncio
import re
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ConfigDict, Field, field_validator
from dotenv import load_dotenv
from api_protection import enforce_rate_limit, positive_int_env
from spotify_utils import (
    get_spotify_auth_url,
    get_token,
    get_app_access_token,
    get_spotify_search_token,
    create_playlist_from_tracks,
    refresh_access_token,
)
from openai_utils import generate_prompt_placeholders
from playlist_engine import (
    generate_playlist as generate_playlist_from_engine,
    run_shadow_v2,
    should_run_shadow_v2,
)
from supabase_utils import get_soundtrack_by_slug, save_soundtrack, update_soundtrack_spotify_url

load_dotenv()

app = FastAPI()

FRONTEND_URL = "https://butterfly-music-app.vercel.app"
MAX_REQUEST_BYTES = positive_int_env("MAX_REQUEST_BYTES", 32768)
GENERATE_PER_HOUR = positive_int_env("GENERATE_PER_HOUR", 5)
GLOBAL_GENERATE_PER_DAY = positive_int_env("GLOBAL_GENERATE_PER_DAY", 50)
SPOTIFY_PLAYLISTS_PER_HOUR = positive_int_env("SPOTIFY_PLAYLISTS_PER_HOUR", 5)
GLOBAL_SPOTIFY_PLAYLISTS_PER_DAY = positive_int_env("GLOBAL_SPOTIFY_PLAYLISTS_PER_DAY", 100)
SOUNDTRACK_WRITES_PER_HOUR = positive_int_env("SOUNDTRACK_WRITES_PER_HOUR", 15)
GLOBAL_SOUNDTRACK_WRITES_PER_DAY = positive_int_env("GLOBAL_SOUNDTRACK_WRITES_PER_DAY", 300)
SOUNDTRACK_READS_PER_HOUR = positive_int_env("SOUNDTRACK_READS_PER_HOUR", 120)
GENERATION_CONCURRENCY = positive_int_env("GENERATION_CONCURRENCY", 2)
generation_slots = asyncio.Semaphore(GENERATION_CONCURRENCY)


class GeneratePlaylistRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=300)

    @field_validator("prompt")
    @classmethod
    def clean_prompt(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("prompt cannot be blank")
        return value


class SongRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(min_length=1, max_length=200)
    artist: str = Field(min_length=1, max_length=200)
    spotify_uri: Optional[str] = Field(default=None, max_length=100)
    uri: Optional[str] = Field(default=None, max_length=100)
    match_score: Optional[int] = Field(default=None, ge=0, le=100)

    @field_validator("title", "artist")
    @classmethod
    def clean_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("song fields cannot be blank")
        return value

    @field_validator("spotify_uri", "uri")
    @classmethod
    def validate_track_uri(cls, value):
        if value and not re.fullmatch(r"spotify:track:[A-Za-z0-9]+", value):
            raise ValueError("invalid Spotify track URI")
        return value


class SpotifyPlaylistRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(default="", max_length=300)
    playlist_name: str = Field(default="Butterfly Soundtrack", min_length=1, max_length=100)
    songs: list[SongRequest] = Field(default_factory=list, max_length=10)
    soundtrack_slug: str = Field(default="", max_length=80)
    access_token: Optional[str] = Field(default=None, max_length=4096)
    refresh_token: Optional[str] = Field(default=None, max_length=4096)

    @field_validator("soundtrack_slug")
    @classmethod
    def validate_slug(cls, value):
        value = value.strip()
        if value and not re.fullmatch(r"[a-z0-9-]+", value):
            raise ValueError("invalid soundtrack slug")
        return value


class CreateSoundtrackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=300)
    playlist_name: str = Field(min_length=1, max_length=100)
    songs: list[SongRequest] = Field(min_length=1, max_length=10)
    spotify_url: Optional[str] = Field(default=None, max_length=500)

    @field_validator("spotify_url")
    @classmethod
    def validate_spotify_url(cls, value):
        if value and not value.startswith("https://open.spotify.com/playlist/"):
            raise ValueError("invalid Spotify playlist URL")
        return value


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request, _exc):
    return JSONResponse({"error": "invalid_request"}, status_code=422)


@app.middleware("http")
async def reject_large_requests(request, call_next):
    if request.method in {"POST", "PUT", "PATCH"}:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_REQUEST_BYTES:
                    return JSONResponse({"error": "request_too_large"}, status_code=413)
            except ValueError:
                return JSONResponse({"error": "invalid_request"}, status_code=400)
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        FRONTEND_URL,
        "http://localhost:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/login")
def login():
    return RedirectResponse(get_spotify_auth_url())

@app.get("/callback")
def callback(code: str):
    token_data = get_token(code)
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    return RedirectResponse(f"{FRONTEND_URL}?token={access_token}&refresh_token={refresh_token}")


def _clean_prompt_for_description(prompt):
    return re.sub(r"[^\w\s.,!?'\-]", "", prompt or "").replace("\n", " ").strip()


def _playlist_description(prompt):
    clean_prompt = _clean_prompt_for_description(prompt)
    return (
        f"Made with Butterfly: {clean_prompt[:120]}"
        if clean_prompt
        else "Made with Butterfly from a feeling."
    )


@app.post("/generate_playlist")
async def generate_playlist(
    payload: GeneratePlaylistRequest,
    request: Request,
    background_tasks: BackgroundTasks,
):
    try:
        limited = enforce_rate_limit(
            request,
            scope="generate",
            per_ip_limit=GENERATE_PER_HOUR,
            global_limit=GLOBAL_GENERATE_PER_DAY,
        )
        if limited:
            return limited

        prompt = payload.prompt

        search_token = get_spotify_search_token()
        async with generation_slots:
            result = await generate_playlist_from_engine(prompt, search_token)
        if result.get("engine_version") == "v1" and should_run_shadow_v2():
            background_tasks.add_task(run_shadow_v2, prompt, search_token)
        playlist_name = result.get("name", "Butterfly Playlist")
        song_list = result.get("songs", [])
        matched_songs = result.get("matched_songs", [])
        if not matched_songs:
            print("⚠️ Spotify matched 0 tracks for generated playlist:", playlist_name)
            return JSONResponse({"error": "no_spotify_matches"}, status_code=502)

        print("✅ Soundtrack matched:", playlist_name, "via", result.get("engine_version", "v1"))
        soundtrack = None
        try:
            soundtrack = save_soundtrack(
                prompt=prompt,
                playlist_name=playlist_name,
                songs=matched_songs,
                spotify_url=None,
                generated_songs=song_list,
                guest_mode=True,
            )
        except Exception as e:
            print("⚠️ Failed to save soundtrack:", str(e))

        soundtrack_slug = soundtrack.get("slug") if soundtrack else None
        return {
            "playlist_url": None,
            "playlist_name": playlist_name,
            "songs_added": matched_songs,
            "guest_mode": True,
            "soundtrack_slug": soundtrack_slug,
            "soundtrack_url": f"{FRONTEND_URL}/s/{soundtrack_slug}" if soundtrack_slug else None,
        }

    except Exception as e:
        print("🔥 Exception during playlist generation:", str(e))
        if isinstance(e, HTTPException):
            return JSONResponse({"error": e.detail}, status_code=e.status_code)
        if "429" in str(e) or "insufficient_quota" in str(e) or "rate_limit" in str(e).lower():
            return JSONResponse({"error": "rate_limited"}, status_code=503)
        return JSONResponse({"error": "Internal server error"}, status_code=500)


@app.post("/spotify_playlist")
async def create_spotify_playlist(payload: SpotifyPlaylistRequest, request: Request):
    try:
        limited = enforce_rate_limit(
            request,
            scope="spotify-playlist",
            per_ip_limit=SPOTIFY_PLAYLISTS_PER_HOUR,
            global_limit=GLOBAL_SPOTIFY_PLAYLISTS_PER_DAY,
        )
        if limited:
            return limited

        prompt = payload.prompt.strip()
        playlist_name = payload.playlist_name.strip()
        songs = [song.model_dump(exclude_none=True) for song in payload.songs]
        soundtrack_slug = payload.soundtrack_slug
        access_token = payload.access_token
        refresh_token = payload.refresh_token
        guest_mode = not access_token

        if guest_mode:
            if not soundtrack_slug:
                return JSONResponse({"error": "Missing soundtrack"}, status_code=400)
            soundtrack = get_soundtrack_by_slug(soundtrack_slug)
            if not soundtrack:
                return JSONResponse({"error": "Soundtrack not found"}, status_code=404)
            prompt = (soundtrack.get("prompt") or "").strip()
            playlist_name = (soundtrack.get("playlist_name") or "Butterfly Soundtrack").strip()
            songs = soundtrack.get("songs") if isinstance(soundtrack.get("songs"), list) else []
            access_token = get_app_access_token()

        if not songs:
            return JSONResponse({"error": "Missing songs"}, status_code=400)

        try:
            playlist_url, added_songs = await create_playlist_from_tracks(
                songs,
                access_token,
                playlist_name,
                playlist_description=_playlist_description(prompt),
                public=guest_mode,
            )
        except Exception as e:
            if ("access token expired" in str(e).lower() or "401" in str(e)):
                print("🔁 Token expired. Attempting refresh...")
                if guest_mode:
                    access_token = get_app_access_token()
                elif refresh_token:
                    refreshed = refresh_access_token(refresh_token)
                    access_token = refreshed.get("access_token")
                else:
                    raise e
                playlist_url, added_songs = await create_playlist_from_tracks(
                    songs,
                    access_token,
                    playlist_name,
                    playlist_description=_playlist_description(prompt),
                    public=guest_mode,
                )
            else:
                raise e

        if soundtrack_slug:
            try:
                update_soundtrack_spotify_url(soundtrack_slug, playlist_url, added_songs)
            except Exception as e:
                print("⚠️ Failed to update soundtrack Spotify URL:", str(e))

        return {
            "playlist_url": playlist_url,
            "songs_added": added_songs,
            "guest_mode": guest_mode,
        }
    except Exception as e:
        print("🔥 Exception during Spotify playlist creation:", str(e))
        if isinstance(e, HTTPException):
            return JSONResponse({"error": e.detail}, status_code=e.status_code)
        if "429" in str(e) or "rate_limit" in str(e).lower():
            return JSONResponse({"error": "rate_limited"}, status_code=503)
        return JSONResponse({"error": "Internal server error"}, status_code=500)

@app.get("/")
def root():
    return {"message": "FastAPI backend for AI + Spotify is running 🎵"}

@app.get("/soundtracks/{slug}")
def get_soundtrack(slug: str, request: Request):
    try:
        limited = enforce_rate_limit(
            request,
            scope="soundtrack-read",
            per_ip_limit=SOUNDTRACK_READS_PER_HOUR,
        )
        if limited:
            return limited
        soundtrack = get_soundtrack_by_slug(slug)
        if not soundtrack:
            return JSONResponse({"error": "Soundtrack not found"}, status_code=404)
        return soundtrack
    except Exception as e:
        print("🔥 Exception while fetching soundtrack:", str(e))
        return JSONResponse({"error": "Failed to fetch soundtrack"}, status_code=500)

@app.post("/soundtracks")
async def create_soundtrack(payload: CreateSoundtrackRequest, request: Request):
    try:
        limited = enforce_rate_limit(
            request,
            scope="soundtrack-write",
            per_ip_limit=SOUNDTRACK_WRITES_PER_HOUR,
            global_limit=GLOBAL_SOUNDTRACK_WRITES_PER_DAY,
        )
        if limited:
            return limited

        prompt = payload.prompt.strip()
        playlist_name = payload.playlist_name.strip()
        songs = [song.model_dump(exclude_none=True) for song in payload.songs]
        spotify_url = payload.spotify_url

        soundtrack = save_soundtrack(
            prompt=prompt,
            playlist_name=playlist_name,
            songs=songs,
            spotify_url=spotify_url,
            generated_songs=songs,
            guest_mode=True,
        )
        if not soundtrack:
            return JSONResponse({"error": "Could not save soundtrack"}, status_code=503)

        soundtrack_slug = soundtrack.get("slug")
        return {
            "soundtrack_slug": soundtrack_slug,
            "soundtrack_url": f"{FRONTEND_URL}/s/{soundtrack_slug}",
        }
    except Exception as e:
        print("🔥 Exception while creating soundtrack:", str(e))
        return JSONResponse({"error": "Failed to create soundtrack"}, status_code=500)

@app.get("/prompt_placeholders")
async def get_prompt_placeholders():
    try:
        placeholders = generate_prompt_placeholders()
        return {"placeholders": placeholders}
    except Exception as e:
        print("🔥 Exception while fetching placeholders:", str(e))
        return JSONResponse({"error": "Failed to generate placeholders"}, status_code=500)
