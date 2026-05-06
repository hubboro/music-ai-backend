from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import re
from dotenv import load_dotenv
from spotify_utils import get_spotify_auth_url, get_token, get_app_access_token, create_playlist_from_prompt, refresh_access_token
from openai_utils import generate_playlist_data, generate_prompt_placeholders

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


@app.post("/generate_playlist")
async def generate_playlist(request: Request):
    try:
        body = await request.json()
        prompt = body.get("prompt")
        access_token = body.get("access_token")
        refresh_token = body.get("refresh_token")
        guest_mode = not access_token

        print("🎯 Received prompt:", prompt)
        print("🔑 Guest mode:", guest_mode)

        if not prompt:
            return JSONResponse({"error": "Missing prompt"}, status_code=400)

        if guest_mode:
            access_token = get_app_access_token()

        result = generate_playlist_data(prompt)
        playlist_name = result.get("name", "Butterfly Playlist")
        song_list = result.get("songs", [])

        clean_prompt = re.sub(r"[^\w\s.,!?'\-]", "", prompt or "").replace("\n", " ").strip()
        playlist_description = f"Butterfly generated: {clean_prompt[:120]}" or "Butterfly generated: a musical vibe"

        try:
            playlist_url, added_songs = await create_playlist_from_prompt(
                song_list, access_token, playlist_name,
                refresh_token if not guest_mode else None,
                playlist_description
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
                playlist_url, added_songs = await create_playlist_from_prompt(
                    song_list, access_token, playlist_name,
                    refresh_token if not guest_mode else None,
                    playlist_description
                )
            else:
                raise e

        print("✅ Playlist created:", playlist_url)
        return {
            "playlist_url": playlist_url,
            "playlist_name": playlist_name,
            "songs_added": added_songs,
            "guest_mode": guest_mode,
        }

    except Exception as e:
        print("🔥 Exception during playlist generation:", str(e))
        if "429" in str(e) or "insufficient_quota" in str(e) or "rate_limit" in str(e).lower():
            return JSONResponse({"error": "rate_limited"}, status_code=503)
        return JSONResponse({"error": "Internal server error"}, status_code=500)

@app.get("/")
def root():
    return {"message": "FastAPI backend for AI + Spotify is running 🎵"}

@app.get("/prompt_placeholders")
async def get_prompt_placeholders():
    try:
        placeholders = generate_prompt_placeholders()
        return {"placeholders": placeholders}
    except Exception as e:
        print("🔥 Exception while fetching placeholders:", str(e))
        return JSONResponse({"error": "Failed to generate placeholders"}, status_code=500)
