from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import re
from dotenv import load_dotenv
from spotify_utils import (
    get_spotify_auth_url,
    get_token,
    get_app_access_token,
    get_spotify_search_token,
    create_playlist_from_tracks,
    match_spotify_tracks,
    refresh_access_token,
)
from openai_utils import generate_playlist_data, generate_prompt_placeholders
from supabase_utils import get_soundtrack_by_slug, get_supabase_status, save_soundtrack, update_soundtrack_spotify_url

load_dotenv()

app = FastAPI()

FRONTEND_URL = "https://butterfly-music-app.vercel.app"

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
async def generate_playlist(request: Request):
    try:
        body = await request.json()
        prompt = body.get("prompt")

        print("🎯 Received prompt:", prompt)

        if not prompt:
            return JSONResponse({"error": "Missing prompt"}, status_code=400)

        result = generate_playlist_data(prompt)
        playlist_name = result.get("name", "Butterfly Playlist")
        song_list = result.get("songs", [])
        search_token = get_spotify_search_token()
        matched_songs = await match_spotify_tracks(song_list, search_token)

        print("✅ Soundtrack matched:", playlist_name)
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
async def create_spotify_playlist(request: Request):
    try:
        body = await request.json()
        prompt = (body.get("prompt") or "").strip()
        playlist_name = (body.get("playlist_name") or "Butterfly Soundtrack").strip()
        songs = body.get("songs") if isinstance(body.get("songs"), list) else []
        soundtrack_slug = (body.get("soundtrack_slug") or "").strip()
        access_token = body.get("access_token")
        refresh_token = body.get("refresh_token")
        guest_mode = not access_token

        if not songs:
            return JSONResponse({"error": "Missing songs"}, status_code=400)

        if guest_mode:
            access_token = get_app_access_token()

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
def get_soundtrack(slug: str):
    try:
        soundtrack = get_soundtrack_by_slug(slug)
        if not soundtrack:
            return JSONResponse({"error": "Soundtrack not found"}, status_code=404)
        return soundtrack
    except Exception as e:
        print("🔥 Exception while fetching soundtrack:", str(e))
        return JSONResponse({"error": "Failed to fetch soundtrack"}, status_code=500)

@app.post("/soundtracks")
async def create_soundtrack(request: Request):
    try:
        body = await request.json()
        prompt = (body.get("prompt") or "").strip()
        playlist_name = (body.get("playlist_name") or "Butterfly Soundtrack").strip()
        songs = body.get("songs") if isinstance(body.get("songs"), list) else []
        spotify_url = body.get("spotify_url")

        if not prompt:
            return JSONResponse({"error": "Missing prompt"}, status_code=400)
        if not songs:
            return JSONResponse({"error": "Missing songs"}, status_code=400)

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

@app.get("/storage_status")
def storage_status():
    return get_supabase_status()

@app.get("/prompt_placeholders")
async def get_prompt_placeholders():
    try:
        placeholders = generate_prompt_placeholders()
        return {"placeholders": placeholders}
    except Exception as e:
        print("🔥 Exception while fetching placeholders:", str(e))
        return JSONResponse({"error": "Failed to generate placeholders"}, status_code=500)
