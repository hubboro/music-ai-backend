from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os
import re
from dotenv import load_dotenv
from spotify_utils import get_spotify_auth_url, get_token, create_playlist_from_prompt, refresh_access_token
from openai_utils import generate_playlist_data, generate_prompt_placeholders

load_dotenv()

limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://butterfly-music-app.vercel.app",
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
    return RedirectResponse(f"https://butterfly-music-app.vercel.app?token={access_token}&refresh_token={refresh_token}")

@app.post("/generate_playlist")
@limiter.limit("10/minute")
async def generate_playlist(request: Request):
    try:
        body = await request.json()
        prompt = body.get("prompt")
        access_token = body.get("access_token")
        refresh_token = body.get("refresh_token")

        print("🎯 Received prompt:", prompt)
        print("🔑 Access token present:", bool(access_token))

        if not prompt or not access_token:
            return JSONResponse({"error": "Missing prompt or access token"}, status_code=400)

        result = generate_playlist_data(prompt)
        playlist_name = result.get("name", "Butterfly Playlist")
        song_list = result.get("songs", [])

        clean_prompt = re.sub(r"[^\w\s.,!?'\-]", "", prompt or "").replace("\n", " ").strip()
        playlist_description = f"Butterfly generated: {clean_prompt[:120]}" or "Butterfly generated: a musical vibe"

        try:
            playlist_url, added_songs = await create_playlist_from_prompt(song_list, access_token, playlist_name, refresh_token, playlist_description)
        except Exception as e:
            if ("access token expired" in str(e).lower() or "401" in str(e)) and refresh_token:
                print("🔁 Token expired. Attempting refresh...")
                refreshed = refresh_access_token(refresh_token)
                access_token = refreshed.get("access_token")
                playlist_url, added_songs = await create_playlist_from_prompt(song_list, access_token, playlist_name, refresh_token, playlist_description)
            else:
                raise e

        print("✅ Playlist created:", playlist_url)
        return {
            "playlist_url": playlist_url,
            "playlist_name": playlist_name,
            "songs_added": added_songs
        }

    except Exception as e:
        print("🔥 Exception during playlist generation:", str(e))
        return JSONResponse({"error": "Internal server error"}, status_code=500)

@app.get("/")
def root():
    return {"message": "FastAPI backend for AI + Spotify is running 🎵"}

@app.get("/prompt_placeholders")
@limiter.limit("30/minute")
async def get_prompt_placeholders(request: Request):
    try:
        placeholders = generate_prompt_placeholders()
        return {"placeholders": placeholders}
    except Exception as e:
        print("🔥 Exception while fetching placeholders:", str(e))
        return JSONResponse({"error": "Failed to generate placeholders"}, status_code=500)
